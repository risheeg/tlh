# Vault Ingest Agent Notes

- Keep Worker code Python-only. Python Workers run on Pyodide, so do not add `requests`, `httpx`, `psycopg`, or socket-based database clients.
- Use Cloudflare bindings for R2, D1, Queues, and Workers AI. Use `pyodide.http.pyfetch` for Neon SQL-over-HTTP.
- Keep secrets out of source. Set `NEON_CONNECTION_STRING` with `npx wrangler secret put NEON_CONNECTION_STRING`.
- Only process objects under the R2 `inbox/` prefix. `processed/` and `parsed/` are Worker-owned output prefixes.
- Before deploying, run `npm run check` from `vault-ingest/`.
