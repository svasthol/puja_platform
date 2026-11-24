"""Launch customer service area polygon (in-memory point-in-polygon, §21.13)."""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from fastapi import HTTPException, status as http

log = structlog.get_logger()

OUT_OF_SERVICE_AREA = "OUT_OF_SERVICE_AREA"
_OUT_OF_SERVICE_MSG = (
    "We currently serve Hyderabad and Secunderabad only. "
    "We hope to be in your area soon."
)


@dataclass(frozen=True)
class BoundarySnapshot:
    rings: tuple[tuple[tuple[float, float], ...], ...]
    min_lat: float
    max_lat: float
    min_lng: float
    max_lng: float
    version: str | None
    vertex_count: int
    etag: str
    source_path: str


_lock = threading.Lock()
_snapshot: BoundarySnapshot | None = None
_load_error: str | None = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_geojson_path(configured: str) -> Path:
    raw = Path(configured)
    if raw.is_absolute():
        return raw
    return (_project_root() / raw).resolve()


def _parse_rings(geometry: dict[str, Any]) -> list[list[tuple[float, float]]]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        return [_ring_from_geojson(ring) for ring in coords]
    if gtype == "MultiPolygon":
        rings: list[list[tuple[float, float]]] = []
        for poly in coords:
            if poly:
                rings.append(_ring_from_geojson(poly[0]))
        return rings
    raise ValueError(f"Unsupported geometry type: {gtype!r}")


def _ring_from_geojson(ring: list[list[float]]) -> list[tuple[float, float]]:
    if len(ring) < 4:
        raise ValueError("Polygon ring must have at least 4 positions")
    out: list[tuple[float, float]] = []
    for pos in ring:
        if len(pos) < 2:
            raise ValueError("Position must be [lng, lat]")
        lng, lat = float(pos[0]), float(pos[1])
        out.append((lng, lat))
    return out


def _build_snapshot(path: Path, data: bytes) -> BoundarySnapshot:
    payload = json.loads(data.decode("utf-8"))
    if payload.get("type") == "Feature":
        geometry = payload.get("geometry") or {}
        properties = payload.get("properties") or {}
    elif payload.get("type") in ("Polygon", "MultiPolygon"):
        geometry = payload
        properties = {}
    else:
        raise ValueError("GeoJSON must be a Feature or Polygon/MultiPolygon")

    rings_raw = _parse_rings(geometry)
    if not rings_raw:
        raise ValueError("No polygon rings")

    frozen_rings: list[tuple[tuple[float, float], ...]] = []
    lats: list[float] = []
    lngs: list[float] = []
    vertex_count = 0
    for ring in rings_raw:
        frozen_rings.append(tuple(ring))
        vertex_count += len(ring)
        for lng, lat in ring:
            lats.append(lat)
            lngs.append(lng)

    etag = hashlib.sha256(data).hexdigest()[:16]
    version = properties.get("version")
    if version is not None:
        version = str(version)

    return BoundarySnapshot(
        rings=tuple(frozen_rings),
        min_lat=min(lats),
        max_lat=max(lats),
        min_lng=min(lngs),
        max_lng=max(lngs),
        version=version,
        vertex_count=vertex_count,
        etag=etag,
        source_path=str(path),
    )


def load_boundary_from_path(path: Path) -> BoundarySnapshot:
    if not path.is_file():
        raise FileNotFoundError(f"Service boundary file not found: {path}")
    data = path.read_bytes()
    return _build_snapshot(path, data)


def init_boundary(path: Path) -> BoundarySnapshot:
    """Load at process startup; raises if file missing or invalid."""
    global _snapshot, _load_error
    with _lock:
        snap = load_boundary_from_path(path)
        _snapshot = snap
        _load_error = None
        log.info(
            "service_boundary_loaded",
            etag=snap.etag,
            vertices=snap.vertex_count,
            version=snap.version,
        )
        return snap


def reload_boundary(path: Path) -> BoundarySnapshot:
    return init_boundary(path)


def get_boundary_snapshot() -> BoundarySnapshot | None:
    return _snapshot


def boundary_load_error() -> str | None:
    return _load_error


def boundary_etag() -> str | None:
    snap = _snapshot
    return snap.etag if snap else None


def boundary_outline_geojson() -> dict[str, Any]:
    snap = _snapshot
    if snap is None:
        raise HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, "Service boundary not loaded.")
    coords: list[list[list[float]]] = []
    for ring in snap.rings:
        coords.append([[lng, lat] for lng, lat in ring])
    if len(coords) == 1:
        geometry: dict[str, Any] = {"type": "Polygon", "coordinates": coords}
    else:
        multi = [[[[lng, lat] for lng, lat in ring]] for ring in snap.rings]
        geometry = {"type": "MultiPolygon", "coordinates": multi}
    return {
        "type": "Feature",
        "properties": {"version": snap.version, "etag": snap.etag},
        "geometry": geometry,
    }


def _point_in_ring(lng: float, lat: float, ring: tuple[tuple[float, float], ...]) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi + 1e-30) + xi
        ):
            inside = not inside
        j = i
    return inside


def is_serviceable(lat: float, lng: float) -> bool:
    snap = _snapshot
    if snap is None:
        return False
    if lat < snap.min_lat or lat > snap.max_lat or lng < snap.min_lng or lng > snap.max_lng:
        return False
    for ring in snap.rings:
        if _point_in_ring(lng, lat, ring):
            return True
    return False


def check_serviceable(lat: float, lng: float) -> tuple[bool, str | None]:
    if is_serviceable(lat, lng):
        return True, None
    return False, OUT_OF_SERVICE_AREA


def assert_serviceable(
    lat: float,
    lng: float,
    *,
    route: str | None = None,
) -> None:
    """Raises 422 OUT_OF_SERVICE_AREA or 503 if boundary required but unloaded."""
    snap = _snapshot
    if snap is None:
        raise HTTPException(
            http.HTTP_503_SERVICE_UNAVAILABLE,
            "Service boundary is not available.",
        )
    if is_serviceable(lat, lng):
        return
    log.info(
        "service_boundary_reject",
        route=route,
        lat=round(lat, 3),
        lng=round(lng, 3),
        code=OUT_OF_SERVICE_AREA,
    )
    raise HTTPException(
        http.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": OUT_OF_SERVICE_AREA, "message": _OUT_OF_SERVICE_MSG},
    )


def boundary_status_dict() -> dict[str, Any]:
    snap = _snapshot
    if snap is None:
        return {
            "loaded": False,
            "etag": None,
            "version": None,
            "vertex_count": 0,
            "bbox": None,
            "source_path": None,
            "load_error": _load_error,
        }
    return {
        "loaded": True,
        "etag": snap.etag,
        "version": snap.version,
        "vertex_count": snap.vertex_count,
        "bbox": {
            "min_lat": snap.min_lat,
            "max_lat": snap.max_lat,
            "min_lng": snap.min_lng,
            "max_lng": snap.max_lng,
        },
        "source_path": snap.source_path,
        "load_error": None,
    }