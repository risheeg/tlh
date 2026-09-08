# Agent Notes

- `vault-ingest` is standalone and acts only as a database client.
- The backend owns the database schema and model definitions (ORM in `backend/models/`, migrations in `backend/alembic/`).
- Do not let `vault-ingest` become the source of truth for DB structure.
- Do not move files between `backend` and `vault-ingest` or change both in one task unless explicitly asked.

## Backend layout

- Business logic: `backend/domains/`
- ORM: `backend/models/`
- HTTP DTOs: `backend/schemas/`
- Cross-cutting helpers: `backend/shared/`
- Thin HTTP adapters: `backend/routers/`
- Scheduled jobs: `backend/scheduler.py` → `domains/*/jobs.py`
- Schema changes: Alembic (`cd backend && alembic revision` / `alembic upgrade head`)
- Ad-hoc scripts: keep out of git (`backend/scratch/` is gitignored); delete when done
