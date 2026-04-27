# Vault Ingest Agent Notes

- Keep Worker code Python-only. Python Workers run on Pyodide, so do not add `requests`, `httpx`, `psycopg`, or socket-based database clients.
- Use Cloudflare bindings for R2, D1, Queues, and Workers AI. Use `pyodide.http.pyfetch` for Neon SQL-over-HTTP.
- Keep secrets out of source. Set `NEON_CONNECTION_STRING` with `npx wrangler secret put NEON_CONNECTION_STRING`. Optional: `VAULT_INGEST_HTTP_SECRET` gates `POST /__vault_ingest/trigger` (same ingestion path as the queue) for e2e and ops without R2 event notifications.
- Only process objects under the R2 `inbox/` prefix. `processed/` and `parsed/` are Worker-owned output prefixes.
- Before deploying, run `npm run check` from `vault-ingest/`.
- When modifying JSONB (`METADATA_SCHEMAS`) or full-text (`FULL_TEXT_SCHEMAS`) schemas, remember to increment the `schema_version` number in the relevant ingestion files (e.g., `src/entry.py`) for the schemas that changed.
