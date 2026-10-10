"""Export committed OpenAPI artifact from the FastAPI app (D5)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


def main() -> None:
    out = ROOT / "spec" / "openapi.json"
    payload = app.openapi()
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(payload.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
