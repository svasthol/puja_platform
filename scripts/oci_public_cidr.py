"""Resolve current machine public IPv4 as a /32 CIDR for OCI ingress rules."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def fetch_public_ipv4(timeout: float = 10.0) -> str:
    for url in (
        "https://api.ipify.org?format=text",
        "https://ifconfig.me/ip",
    ):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                ip = resp.read().decode("ascii").strip()
            if ip and "." in ip and ":" not in ip:
                return ip
        except OSError:
            continue
    raise SystemExit("oci_public_cidr: could not resolve public IPv4")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    ip = fetch_public_ipv4()
    cidr = f"{ip}/32"
    if args.json:
        print(json.dumps({"ip": ip, "cidr": cidr}))
    else:
        print(cidr)


if __name__ == "__main__":
    main()
