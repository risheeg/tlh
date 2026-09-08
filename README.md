# TLH Project

This workspace contains two distinct applications:

- **[backend](./backend)**: A FastAPI application for tracking net worth and identifying Tax Loss Harvesting (TLH) opportunities.
- **[vault-ingest](./vault-ingest)**: A Cloudflare Python Worker pipeline for backing up, classifying, and indexing personal documents.

See [docs/domain-organization.md](./docs/domain-organization.md) for backend package boundaries and [docs/schema.md](./docs/schema.md) for the database overview.
