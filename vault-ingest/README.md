# Vault Ingest

Cloudflare Python Worker pipeline for backing up, classifying, and indexing personal documents.

## Flow

1. A local cron job runs `scripts/upload-and-prune.sh`.
2. `rclone` copies new files from a Linux folder into the R2 `inbox/` prefix.
3. R2 Event Notifications send `object-create` events for `inbox/` to the `vault-ingest` queue.
4. The Python Worker checks the D1 daily AI budget.
5. PDFs and rich documents are converted with `env.AI.toMarkdown(...)`; plain text is sent directly to Gemma.
6. `@cf/google/gemma-4-26b-a4b-it` returns structured JSON.
7. The Worker writes the parsed JSON sidecar and processed original to R2, inserts the catalog row into Neon over HTTP, records D1 usage, and deletes the `inbox/` object.

## Cloudflare Resources

Create the resources, then replace placeholders in `wrangler.jsonc`.

```bash
npx wrangler r2 bucket create vault-ingest
npx wrangler queues create vault-ingest
npx wrangler queues create vault-ingest-dlq
npx wrangler d1 create vault-ingest
```

Apply the D1 migration:

```bash
npm run d1:migrate:remote
```

Configure the R2 notification after the queue exists:

```bash
npx wrangler r2 bucket notification create vault-ingest \
  --event-type object-create \
  --queue vault-ingest \
  --prefix "inbox/"
```

Set the Neon connection string as a Worker secret:

```bash
npx wrangler secret put NEON_CONNECTION_STRING
```

The Python Worker derives Neon's SQL-over-HTTP `/sql` endpoint from the hostname in `NEON_CONNECTION_STRING` and sends the connection string in the `Neon-Connection-String` header, matching the Neon serverless driver's HTTP protocol without importing the JavaScript driver.

## Local Upload Cron

Configure an R2-compatible rclone remote first. For Cloudflare R2, that is typically an S3 remote with the R2 endpoint, access key, and secret key.

Run once manually:

```bash
TARGET_DIR="$HOME/Downloads/vault-target" \
R2_REMOTE="r2:vault-ingest/inbox" \
./scripts/upload-and-prune.sh
```

Example cron entry to run every hour:

```cron
0 * * * * TARGET_DIR=/home/you/Downloads/vault-target R2_REMOTE=r2:vault-ingest/inbox /home/you/tlh/vault-ingest/scripts/upload-and-prune.sh >> /home/you/.local/state/vault-ingest.log 2>&1
```

The script only prunes files older than `RETENTION_DAYS` after `rclone copy` succeeds. The default retention is 14 days.

## Development

```bash
uv sync
npm run check
npm run dev
```

Deploy:

```bash
npm run deploy
```

Python Workers run on Pyodide, so do not add socket-based HTTP or database clients such as `requests`, `httpx`, or `psycopg`. Use platform bindings and `pyodide.http.pyfetch` for HTTP calls.
