"""SSH local forward to staging Postgres (binds 127.0.0.1:5432 on VM only).

Recommended laptop flow:
  ssh -L 15432:127.0.0.1:5432 opc@140.245.245.201
  STAGING_DATABASE_URL=postgresql://puja_migrate:...@127.0.0.1:15432/Mana_Guruji

No OCI/firewalld exposure of Postgres on the public IP required.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from urllib.parse import quote, urlparse, urlunparse

DEFAULT_SSH_TARGET = "opc@140.245.245.201"
DEFAULT_LOCAL_PORT = 15432
DEFAULT_REMOTE = ("127.0.0.1", 5432)


def local_port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def ensure_tunnel(
    ssh_target: str = DEFAULT_SSH_TARGET,
    local_port: int = DEFAULT_LOCAL_PORT,
    remote_host: str = DEFAULT_REMOTE[0],
    remote_port: int = DEFAULT_REMOTE[1],
) -> None:
    if local_port_open(local_port):
        print(f"staging_db_tunnel: 127.0.0.1:{local_port} already accepts connections")
        return
    bind = f"{local_port}:{remote_host}:{remote_port}"
    cmd = [
        "ssh",
        "-f",
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=60",
        "-L",
        bind,
        ssh_target,
    ]
    print("staging_db_tunnel: starting", " ".join(cmd))
    subprocess.run(cmd, check=True)
    if not local_port_open(local_port):
        raise SystemExit(
            f"staging_db_tunnel: forward failed — is SSH key loaded and is {ssh_target} reachable?"
        )
    print(f"staging_db_tunnel: OK — use 127.0.0.1:{local_port} in STAGING_DATABASE_URL")


def staging_url_via_tunnel(
    url: str,
    local_port: int = DEFAULT_LOCAL_PORT,
    rewrite_remote: bool = True,
) -> str:
    """Point URL at localhost tunnel; optionally rewrite public-IP :5432 URLs."""
    parsed = urlparse(url)
    if not parsed.hostname:
        return url
    host = parsed.hostname
    port = parsed.port or 5432
    if host in ("127.0.0.1", "localhost") and port == local_port:
        return url
    if port == 5432 and host not in ("127.0.0.1", "localhost"):
        if rewrite_remote:
            print(
                f"staging_db_tunnel: rewriting {host}:5432 → 127.0.0.1:{local_port} (SSH tunnel)",
                file=sys.stderr,
            )
            new = parsed._replace(netloc=_replace_host_port(parsed.netloc, "127.0.0.1", local_port))
            return urlunparse(new)
        print(
            f"staging_db_tunnel: WARNING — {host}:5432 is not reachable; "
            f"Postgres on staging is 127.0.0.1 only. Tunnel to 127.0.0.1:{local_port}.",
            file=sys.stderr,
        )
    return url


def _replace_host_port(netloc: str, host: str, port: int) -> str:
    # preserve user:pass@
    if "@" in netloc:
        auth, _ = netloc.rsplit("@", 1)
        return f"{auth}@{host}:{port}"
    return f"{host}:{port}"


def build_staging_database_url(
    *,
    user: str,
    password: str,
    database: str = "Mana_Guruji",
    local_port: int = DEFAULT_LOCAL_PORT,
) -> str:
    safe_user = quote(user, safe="")
    safe_pass = quote(password, safe="")
    return f"postgresql://{safe_user}:{safe_pass}@127.0.0.1:{local_port}/{database}"


def resolve_staging_url(
    explicit_url: str | None,
    local_port: int = DEFAULT_LOCAL_PORT,
) -> str:
    if explicit_url:
        return staging_url_via_tunnel(explicit_url, local_port)
    user = os.environ.get("STAGING_DB_USER", "puja_migrate")
    password = os.environ.get("STAGING_DB_PASSWORD", "")
    if not password:
        return ""
    return build_staging_database_url(
        user=user,
        password=password,
        database=os.environ.get("STAGING_DB_NAME", "Mana_Guruji"),
        local_port=local_port,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="SSH tunnel to staging Postgres")
    parser.add_argument("--ssh", default=os.environ.get("STAGING_SSH", DEFAULT_SSH_TARGET))
    parser.add_argument(
        "--local-port",
        type=int,
        default=int(os.environ.get("STAGING_DB_TUNNEL_PORT", str(DEFAULT_LOCAL_PORT))),
    )
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if args.check_only:
        ok = local_port_open(args.local_port)
        print(f"127.0.0.1:{args.local_port} open={ok}")
        sys.exit(0 if ok else 1)

    ensure_tunnel(args.ssh, args.local_port)


if __name__ == "__main__":
    main()
