# Agent Notes

- `vault-ingest` is standalone and acts only as a database client.
- The backend owns the database schema and model definitions.
- Do not let `vault-ingest` become the source of truth for DB structure.
- Do not move files between `backend` and `vault-ingest` or change both in one task unless explicitly asked.
