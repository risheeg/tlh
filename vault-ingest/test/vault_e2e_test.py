#!/usr/bin/env python3
"""
E2E helper for vault-ingest: clean R2 + Neon, upload, poll, download artifacts.

Requires: npx wrangler, NEON_CONNECTION_STRING, optional CLOUDFLARE_API_TOKEN for listing R2.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

# Per wrangler CLI call (R2 get/put/delete are slow on large files or cold API).
_DEFAULT_WRANGLER_TIMEOUT = 180
_DEFAULT_POLL_TIMEOUT = 600.0
_DEFAULT_POLL_INTERVAL = 8.0

# Set from CLI in main() so all wrangler calls share one timeout.
_CFG: dict[str, int | float] = {
    "wrangler_timeout": _DEFAULT_WRANGLER_TIMEOUT,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def document_id_for_inbox_key(inbox_key: str, bucket: str = "vault-ingest") -> str:
    """Must match src/entry._document_id (uuid5 over r2://bucket/key)."""
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"r2://{bucket}/{inbox_key}",
        )
    )


def neon_sql_endpoint(connection_string: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(connection_string)
    host = parsed.hostname
    if not host:
        raise RuntimeError("NEON_CONNECTION_STRING missing hostname")
    parts = host.split(".", 1)
    if len(parts) != 2:
        raise RuntimeError(f"Unexpected Neon hostname: {host}")
    return f"https://api.{parts[1]}/sql"


def neon_sql(
    connection_string: str,
    query: str,
    params: list,
) -> dict | list:
    body = json.dumps({"query": query, "params": params})
    req = urllib.request.Request(
        neon_sql_endpoint(connection_string),
        data=body.encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Neon-Connection-String": connection_string,
            "Neon-Raw-Text-Output": "true",
            "Neon-Array-Mode": "true",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Neon SQL HTTP {e.code}: {e.read().decode()}") from e
    if not raw:
        return {}
    data = json.loads(raw)
    if isinstance(data, dict) and data.get("message") and "error" in str(data).lower():
        raise RuntimeError(str(data))
    return data


def cf_r2_list_keys(
    account_id: str,
    api_token: str,
    bucket: str,
    prefix: str,
) -> list[str]:
    keys: list[str] = []
    cursor: str | None = None
    while True:
        q: dict[str, str | int] = {"per_page": 100, "prefix": prefix}
        if cursor:
            q["cursor"] = cursor
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/"
            f"r2/buckets/{urllib.parse.quote(bucket)}/objects?"
            + urllib.parse.urlencode(q)
        )
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {api_token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"R2 list HTTP {e.code}: {e.read().decode()}") from e
        if not payload.get("success"):
            raise RuntimeError(f"CF API: {payload}")
        result = payload.get("result") or []
        for obj in result:
            if isinstance(obj, dict) and "key" in obj:
                keys.append(str(obj["key"]))
        info = payload.get("result_info") or {}
        cursor = info.get("cursor")
        if not cursor:
            break
    return keys


def wrangler(
    cwd: Path,
    args: list[str],
    *,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    if timeout is None:
        timeout = int(_CFG["wrangler_timeout"])
    cmd = ["npx", "wrangler", *args]
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"wrangler timed out after {timeout}s: {' '.join(cmd[:6])}..."
        ) from e
    if check and p.returncode != 0:
        sys.stderr.write(p.stdout)
        sys.stderr.write(p.stderr)
        p.check_returncode()
    return p


def r2_delete_remote(cwd: Path, wrangler_config: str, bucket: str, key: str) -> bool:
    """Return True if deleted, False if wrangler reported missing."""
    path = f"{bucket}/{key}"
    p = wrangler(
        cwd,
        [
            "r2",
            "object",
            "delete",
            path,
            "--remote",
            "-c",
            wrangler_config,
            "-y",
        ],
        check=False,
    )
    if p.returncode == 0:
        return True
    err = (p.stdout + p.stderr).lower()
    if "not found" in err or "does not exist" in err or "404" in err:
        return False
    sys.stderr.write(p.stdout)
    sys.stderr.write(p.stderr)
    p.check_returncode()
    return True


def r2_put(
    cwd: Path,
    wrangler_config: str,
    bucket: str,
    key: str,
    local_path: Path,
    content_type: str | None,
) -> None:
    path = f"{bucket}/{key}"
    args = [
        "r2",
        "object",
        "put",
        path,
        "--remote",
        "-f",
        str(local_path),
        "-c",
        wrangler_config,
        "-y",
    ]
    if content_type:
        args.extend(["--content-type", content_type])
    wrangler(cwd, args, check=True)


def r2_get(
    cwd: Path,
    wrangler_config: str,
    bucket: str,
    key: str,
    out_path: Path,
) -> None:
    path = f"{bucket}/{key}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wrangler(
        cwd,
        [
            "r2",
            "object",
            "get",
            path,
            "--remote",
            "-f",
            str(out_path),
            "-c",
            wrangler_config,
        ],
        check=True,
    )


def extract_rows(neon_response: dict | list) -> list[dict]:
    """Parse Neon SQL-over-HTTP (array mode) into a list of row dicts."""
    if isinstance(neon_response, list):
        if neon_response and isinstance(neon_response[0], dict):
            return neon_response  # type: ignore[return-value]
        return []
    if not isinstance(neon_response, dict):
        return []
    for k in ("rows", "result", "data"):
        v = neon_response.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
    r = neon_response.get("result")
    if isinstance(r, dict) and isinstance(r.get("rows"), list):
        return _rows_from_fields(r.get("rows"), r.get("fields"))
    if isinstance(neon_response.get("rows"), list):
        return _rows_from_fields(neon_response.get("rows"), neon_response.get("fields"))
    return []


def _rows_from_fields(rows, fields) -> list[dict]:
    if not (isinstance(rows, list) and isinstance(fields, list)):
        return []
    if not rows:
        return []
    if not isinstance(rows[0], list):
        return []
    names = [f.get("name") for f in fields if isinstance(f, dict)]
    out = []
    for row in rows:
        if not isinstance(row, list):
            continue
        out.append({names[i]: row[i] for i in range(min(len(names), len(row)))})
    return out


def select_neon_row(neon: str, document_id: str, debug: Path | None) -> dict | None:
    raw = neon_sql(
        neon,
        "SELECT * FROM vault_ingest.documents WHERE id = $1::uuid",
        [document_id],
    )
    rows = extract_rows(raw)
    if rows:
        return rows[0]
    if debug is not None:
        (debug / "neon_last_select.json").write_text(json.dumps(raw, default=str, indent=2))
    return None


def guess_content_type(key: str) -> str:
    lower = key.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".txt"):
        return "text/plain"
    if lower.endswith(".json"):
        return "application/json"
    return "application/octet-stream"


def _json_contains_null(value) -> bool:
    """True if any leaf value in nested dict/list is JSON null."""
    if value is None:
        return True
    if isinstance(value, dict):
        return any(_json_contains_null(v) for v in value.values())
    if isinstance(value, list):
        return any(_json_contains_null(v) for v in value)
    return False


def validate_e2e_artifacts(out_dir: Path, row: dict | None) -> tuple[bool, list[str]]:
    """Return (all_checks_pass, human-readable issues)."""
    issues: list[str] = []
    if not row:
        return False, ["no Neon row"]
    pj = row.get("parsed_json")
    if isinstance(pj, str):
        try:
            pj = json.loads(pj)
        except Exception as e:
            issues.append(f"parsed_json in DB is not valid JSON: {e}")
            pj = None
    if not isinstance(pj, dict):
        issues.append("parsed_json missing or not an object in Neon row")
    else:
        if pj.get("schema_version") != 1:
            issues.append(f"schema_version expected 1, got {pj.get('schema_version')!r}")
        if _json_contains_null(pj):
            issues.append("parsed_json in Neon must not contain null (expect '' / 0 / [] per pipeline)")
        if "full_text_or_records" in pj:
            issues.append("Neon parsed_json must not include full_text_or_records (kept in R2 parsed .json only)")
        sub = (row.get("subcategory") or "")
        if sub == "statement_credit_card":
            meta = pj.get("metadata")
            if not isinstance(meta, dict):
                issues.append("statement_credit_card: metadata object missing in Neon")
            else:
                for key in (
                    "account_number",
                    "account_hint",
                    "statement_period_start",
                    "statement_period_end",
                    "account_type",
                    "ending_balance",
                    "transaction_count",
                    "rewards_earned",
                    "rewards_balance",
                ):
                    if key not in meta:
                        issues.append(f"statement_credit_card: metadata missing {key!r}")
    pj_path = out_dir / "parsed.json"
    if not pj_path.is_file():
        issues.append(f"missing {pj_path.name} (download step)")
    else:
        try:
            disk = json.loads(pj_path.read_text())
        except Exception as e:
            issues.append(f"parsed.json on disk invalid: {e}")
        else:
            if disk.get("schema_version") != 1:
                issues.append(f"disk parsed.json schema_version expected 1, got {disk.get('schema_version')!r}")
            if (row.get("subcategory") or "") == "statement_credit_card":
                if "full_text_or_records" not in disk or not isinstance(
                    disk.get("full_text_or_records"), list
                ):
                    issues.append(
                        "statement_credit_card: full_text_or_records must be present on R2 parsed.json (not in Neon)"
                    )
    for name in ("markdown.md", "processed.replica.bin"):
        p = out_dir / name
        if not p.is_file() or p.stat().st_size == 0:
            issues.append(f"missing or empty {name}")
    return len(issues) == 0, issues


def http_trigger_ingest(worker_base_url: str, secret: str, inbox_key: str) -> None:
    """POST to Worker HTTP trigger (same pipeline as queue).

    Uses ``curl`` when available to avoid some networks returning CF error 1010
    to Python’s default User-Agent; falls back to urllib with browser-like headers.
    """
    url = worker_base_url.rstrip("/") + "/__vault_ingest/trigger"
    payload = json.dumps({"key": inbox_key})
    curl_cmd = [
        "curl",
        "-sS",
        "-X",
        "POST",
        url,
        "-H",
        "Content-Type: application/json",
        "-H",
        f"X-Vault-Ingest-Secret: {secret}",
        "-H",
        "User-Agent: curl/8.0 (vault-e2e)",
        "--data-binary",
        payload,
        "-w",
        "\n__HTTP_STATUS__:%{http_code}",
        "--connect-timeout",
        "30",
        "--max-time",
        "600",
    ]
    try:
        p = subprocess.run(curl_cmd, text=True, capture_output=True, timeout=620, check=False)
    except FileNotFoundError:
        p = None
    if p and p.returncode == 0 and "__HTTP_STATUS__:" in (p.stdout or ""):
        raw, _, rest = p.stdout.partition("__HTTP_STATUS__:")
        st_str = rest.strip()
        st = int(st_str) if st_str.isdigit() else 0
        if st >= 400:
            raise RuntimeError(f"HTTP trigger {st}: {raw[:2000]}")
        try:
            out = json.loads(raw) if raw.strip() else {}
        except Exception:
            out = {"raw": raw}
        print(f"HTTP trigger response: {out}", flush=True)
        return
    if p and p.returncode != 0:
        raise RuntimeError(
            f"curl failed ({p.returncode}): {(p.stdout or '') + (p.stderr or '')}"
        )

    # Fallback: urllib (may hit CF 1010 on some edge IPs)
    body = payload.encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Vault-Ingest-Secret": secret,
            "User-Agent": "curl/8.0 (vault-e2e-fallback)",
            "Accept": "application/json,*/*;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode()
            st = getattr(resp, "status", 200) or 200
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"HTTP trigger {e.code}: {err_body}") from e
    if st >= 400:
        raise RuntimeError(f"HTTP trigger {st}: {raw}")
    try:
        out = json.loads(raw) if raw else {}
    except Exception:
        out = {"raw": raw}
    print(f"HTTP trigger response: {out}", flush=True)


def write_eval_template(out_dir: Path, parsed: dict | None) -> None:
    lines = [
        "# E2E quality review",
        "",
        "Fill after reviewing downloaded JSON and Neon row.",
        "",
        "- [ ] Classification (category / subcategory) matches the source document.",
        "- [ ] `summary` is accurate; `notes` / `document_date` / `issuer` sensible.",
        "- [ ] `metadata` keys match taxonomy for this pair; values are not PDF header noise.",
        "- [ ] Dates are YYYY-MM-DD or null.",
        "- [ ] `full_text_or_records` shape is correct when present (structured rows, not one raw string).",
        "- [ ] `schema_version` is 1.",
        "",
    ]
    if parsed:
        lines.append("## Parsed preview\n\n```json\n")
        lines.append(json.dumps(parsed, indent=2)[:8000])
        lines.append("\n```\n")
    (out_dir / "EVAL.md").write_text("\n".join(lines))


def main() -> int:
    socket.setdefaulttimeout(90)
    ap = argparse.ArgumentParser(description="Vault ingest E2E test helper")
    ap.add_argument("--config", default="wrangler.jsonc", help="Wrangler config path")
    ap.add_argument("--bucket", default="vault-ingest")
    ap.add_argument("--inbox-key", default="inbox/original_statement.txt")
    ap.add_argument("--local-file", default="mock/hsa-receipt-sample.txt")
    ap.add_argument(
        "--cleanup-substring",
        default="original_statement",
        help="Delete Neon rows whose r2_original_path contains this (case-sensitive SQL LIKE).",
    )
    ap.add_argument(
        "--out-dir",
        default="test/last-e2e",
        help="Directory for downloaded artifacts and logs (relative to repo root unless absolute).",
    )
    ap.add_argument(
        "--poll-interval",
        type=float,
        default=_DEFAULT_POLL_INTERVAL,
        help=f"Seconds between polls (default {_DEFAULT_POLL_INTERVAL})",
    )
    ap.add_argument(
        "--poll-timeout",
        type=float,
        default=_DEFAULT_POLL_TIMEOUT,
        help=f"Max seconds to wait for Neon row after upload (default {_DEFAULT_POLL_TIMEOUT})",
    )
    ap.add_argument(
        "--wrangler-timeout",
        type=int,
        default=_DEFAULT_WRANGLER_TIMEOUT,
        help=f"Subprocess timeout for each wrangler r2 call in seconds (default {_DEFAULT_WRANGLER_TIMEOUT})",
    )
    ap.add_argument("--no-tail", action="store_true", help="Skip wrangler tail subprocess")
    ap.add_argument(
        "--no-http-trigger",
        action="store_true",
        help="Do not POST to /__vault_ingest/trigger (R2 event→queue only)",
    )
    ap.add_argument("--no-inbox-nuke", action="store_true", help="Skip listing/deleting all inbox/ objects")
    ap.add_argument("--content-type", default=None, help="Override R2 object Content-Type for upload")
    args = ap.parse_args()
    _CFG["wrangler_timeout"] = int(args.wrangler_timeout)

    root = _repo_root()
    load_dotenv(root / ".env")
    load_dotenv(root / ".dev.vars")

    wrangler_config = str(args.config)
    bucket = str(args.bucket)
    inbox_key = str(args.inbox_key).lstrip("/")
    if not inbox_key.startswith("inbox/"):
        print("--inbox-key should look like 'inbox/filename.txt'", file=sys.stderr)
        return 2

    local = (root / args.local_file).resolve()
    if not local.is_file():
        print(f"Local file not found: {local}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (root / out_dir).resolve()
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)

    neon = os.environ.get("NEON_CONNECTION_STRING")
    if not neon:
        print("Set NEON_CONNECTION_STRING in the environment or .env", file=sys.stderr)
        return 2

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not account_id:
        cache = root / ".wrangler/cache/wrangler-account.json"
        if cache.is_file():
            data = json.loads(cache.read_text())
            account_id = (data.get("account") or {}).get("id")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    document_id = document_id_for_inbox_key(inbox_key, bucket)

    # --- 1) Nuke entire inbox/ (optional) ---
    if not args.no_inbox_nuke and token and account_id:
        try:
            keys = cf_r2_list_keys(account_id, token, bucket, "inbox/")
        except Exception as e:
            print(f"[warn] inbox list failed ({e}); only deleting {inbox_key} later if needed")
            keys = []
        for k in keys:
            print(f"delete inbox: {k}")
            r2_delete_remote(root, wrangler_config, bucket, k)
    elif not args.no_inbox_nuke:
        print(
            "[warn] CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID not set; "
            "skipping full inbox nuke. Set them for full list/delete."
        )

    # --- 2) Neon: find rows, delete R2 outputs, delete rows (cleanup substring) ---
    sub = f"%{args.cleanup_substring}%"
    try:
        raw = neon_sql(
            neon,
            """
            SELECT id, r2_original_path, r2_file_path, r2_parsed_json_path, r2_markdown_path
            FROM vault_ingest.documents
            WHERE r2_original_path LIKE $1 OR id = $2::uuid
            """,
            [sub, document_id],
        )
    except Exception as e:
        print(f"[error] Neon SELECT failed: {e}", file=sys.stderr)
        return 1
    rows = extract_rows(raw)
    for row in rows:
        for col in (
            "r2_original_path",
            "r2_file_path",
            "r2_parsed_json_path",
            "r2_markdown_path",
        ):
            k = row.get(col)
            if not k or not isinstance(k, str):
                continue
            rk = k.lstrip("/")
            if rk:
                print(f"delete r2 (from neon): {rk}")
                r2_delete_remote(root, wrangler_config, bucket, rk)
    if rows:
        try:
            neon_sql(
                neon,
                "DELETE FROM vault_ingest.documents WHERE r2_original_path LIKE $1 OR id = $2::uuid",
                [sub, document_id],
            )
        except Exception as e:
            print(f"[error] Neon DELETE failed: {e}", file=sys.stderr)
            return 1
        print(f"Neon: deleted {len(rows)} row(s) matching cleanup / document id")
    else:
        print("Neon: no prior rows to delete for this test key / cleanup substring")

    # --- 3) Remove orphan inbox key if still there ---
    r2_delete_remote(root, wrangler_config, bucket, inbox_key)

    # --- 4) Start tail in background ---
    tail_proc: subprocess.Popen[bytes] | None = None
    tlog: object | None = None
    if not args.no_tail:
        tlog = (out_dir / "tail.log").open("wb")
        tail_proc = subprocess.Popen(
            [
                "npx",
                "wrangler",
                "tail",
                "vault-ingest",
                "--format",
                "pretty",
                "-c",
                wrangler_config,
            ],
            cwd=str(root),
            stdout=tlog,
            stderr=subprocess.STDOUT,
        )
        time.sleep(1.5)

    # --- 5) Upload ---
    ct = args.content_type or guess_content_type(inbox_key)
    print(f"upload {local} -> {bucket}/{inbox_key}")
    r2_put(root, wrangler_config, bucket, inbox_key, local, ct)

    worker_url = (os.environ.get("VAULT_INGEST_WORKER_URL") or os.environ.get("WORKER_URL") or "").rstrip(
        "/"
    )
    http_secret = (os.environ.get("VAULT_INGEST_HTTP_SECRET") or "").strip()
    if not args.no_http_trigger and worker_url and http_secret:
        try:
            print(f"HTTP trigger {worker_url}/__vault_ingest/trigger", flush=True)
            http_trigger_ingest(worker_url, http_secret, inbox_key)
        except Exception as e:
            print(f"[error] HTTP trigger failed: {e}", file=sys.stderr)
            return 1
    elif not args.no_http_trigger:
        print(
            "[info] Set VAULT_INGEST_WORKER_URL and VAULT_INGEST_HTTP_SECRET in .env "
            "to use POST /__vault_ingest/trigger after upload; otherwise R2→queue only.",
            flush=True,
        )

    # --- 6) Poll until Neon has the new row (or timeout) ---
    # The Worker calls insert_document before deleting the inbox key, so a Neon
    # row is the first reliable success signal; do not require inbox=gone first.
    t0 = time.time()
    ready = False
    while time.time() - t0 < args.poll_timeout:
        row = select_neon_row(neon, document_id, out_dir)
        if row is not None:
            print("Neon row present (pipeline completed insert).", flush=True)
            ready = True
            break
        time.sleep(args.poll_interval + random.random() * 0.3)

    if tail_proc:
        tail_proc.terminate()
        try:
            tail_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tail_proc.kill()
        if tlog:
            tlog.close()

    if not ready:
        print(
            f"[warn] Polling did not confirm completion within {args.poll_timeout}s. "
            "Check R2 event notification → queue, budget, and tail.log.",
            file=sys.stderr,
        )

    # Save Neon row and downloads
    row = select_neon_row(neon, document_id, out_dir)
    (out_dir / "document_row.json").write_text(
        (json.dumps(row, indent=2, default=str) if row else "null") + "\n"
    )

    if row:
        for col, out_name in [
            ("r2_file_path", "processed.replica.bin"),
            ("r2_parsed_json_path", "parsed.json"),
            ("r2_markdown_path", "markdown.md"),
        ]:
            k = row.get(col) if isinstance(row, dict) else None
            if not k or not isinstance(k, str):
                continue
            key = k.lstrip("/")
            if not key:
                continue
            dest = out_dir / out_name
            try:
                r2_get(root, wrangler_config, bucket, key, dest)
                print(f"downloaded {key} -> {dest.name}")
            except Exception as e:
                print(f"[warn] could not get {key}: {e}", file=sys.stderr)
        pj = row.get("parsed_json") if isinstance(row, dict) else None
        if isinstance(pj, str):
            try:
                pj = json.loads(pj)
            except Exception:
                pj = None
        write_eval_template(out_dir, pj if isinstance(pj, dict) else None)
    else:
        write_eval_template(out_dir, None)

    print(f"Artifacts under: {out_dir}", flush=True)
    if not ready:
        return 3

    ok, issues = validate_e2e_artifacts(out_dir, row)
    report = out_dir / "e2e_result.txt"
    if ok:
        report.write_text("PASS: Neon row + parsed.json + downloads OK (schema_version 1).\n")
        print("E2E PASSED — all automated checks OK.", flush=True)
        return 0

    msg = "FAIL: " + "; ".join(issues) + "\n"
    report.write_text(msg)
    print(msg, file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    sys.exit(main())
