"""
CLI ingestion tool for the TLH backend.

Usage:
    uv run python scripts/ingest.py --endpoint lots      --file scripts/data/lots.json
    uv run python scripts/ingest.py --endpoint positions --file scripts/data/positions.json

The JSON file must match the request body expected by the corresponding endpoint:
    /ingest/lots       → scripts/data/lots.json
    /ingest/positions  → scripts/data/positions.json

See the sample files in scripts/data/ for the exact schema.
"""

import argparse
import json
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "http://127.0.0.1:8000"

ENDPOINT_MAP = {
    "lots":      "/ingest/lots",
    "positions": "/ingest/positions",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Post a JSON payload to a TLH ingest endpoint.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--endpoint",
        required=True,
        choices=list(ENDPOINT_MAP),
        help="Which ingest endpoint to hit: 'lots' or 'positions'.",
    )
    parser.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Path to the JSON file containing the request body.",
    )
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"Base URL of the TLH API (default: {BASE_URL}).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ------------------------------------------------------------------
    # Load JSON
    # ------------------------------------------------------------------
    if not args.file.exists():
        print(f"[error] File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(args.file.read_text())
    except json.JSONDecodeError as exc:
        print(f"[error] Invalid JSON in {args.file}: {exc}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # POST to API
    # ------------------------------------------------------------------
    url = f"{args.base_url}{ENDPOINT_MAP[args.endpoint]}"
    print(f"[ingest] POST {url}")
    print(f"[ingest] Payload preview: {json.dumps(payload, indent=2)[:400]} …")
    print()

    try:
        resp = requests.post(url, json=payload, timeout=15)
    except requests.ConnectionError:
        print(
            f"[error] Could not connect to {args.base_url}. Is the server running?",
            file=sys.stderr,
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Print result
    # ------------------------------------------------------------------
    print(f"[ingest] HTTP {resp.status_code}")
    try:
        result = resp.json()
        print(json.dumps(result, indent=2))
    except Exception:
        print(resp.text)

    if not resp.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
