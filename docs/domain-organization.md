# Design: Domain Organization for Backend Logics

**Status:** Implemented (Option B)  
**Date:** 2026-09-07 · **Updated:** 2026-09-08  
**Scope:** Backend FastAPI app (`backend/`). Vault-ingest Worker stays a separate DB client per `AGENTS.md`.

---

## 1. What changed

Business logic moved out of flat `services/` into vertical **`domains/`** packages. Cross-cutting helpers live in **`shared/`**. ORM stays in **`models/`**, HTTP DTOs in **`schemas/`**, thin adapters in **`routers/`**. The old `services/` tree is gone.

| Capability | Before | After |
| :--- | :--- | :--- |
| **Tax** | `services/taxes/` (parser + monolithic calculator that re-scanned holdings) | `domains/taxes/` (`parser`, `types`, `brackets`, `projection`); projection calls `domains.tlh.scan` |
| **TLH** | Flat `services/tlh_service.py` | `domains/tlh/` (`scan`, `notify`, `jobs`) |
| **Portfolio** | `services/portfolio/` + fat `routers/ingest.py` | `domains/portfolio/` (incl. `ingest`, `prices`, `corporate_actions`, …); ingest router is thin |
| **Expense traffic** | Models + Postgres schema only | `domains/expenses/` scaffold (`service.py` placeholder) |
| **Cross-cutting** | Flat `services/email_service.py`, settings, digest, sheets | `shared/` (`email`, `user_settings`, `sheets`); monthly digest → `domains/portfolio/digest.py` |

---

## 2. Goals (unchanged)

1. One obvious home for each capability.
2. Explicit, one-way dependencies between domains.
3. Thin routers; business rules in domains.
4. Incremental migration — no vault↔backend file moves.
5. Preserve existing Postgres schemas (`public`, `taxes`, `expenses`, `vault_ingest`).

### Non-goals

- Microservices / separate deployables per domain.
- Changing vault-ingest ownership of OCR/classification.
- Redesigning tax formulas or TLH email copy.
- Frontend architecture.

---

## 3. As-built architecture

```text
backend/
  models/                    # ORM ONLY
    core.py                  # User, Account
    portfolio.py             # Lot, AggregatePosition, StockPrice, Transaction, views
    taxes.py
    expenses.py
    documents.py             # vault_ingest.documents (DDL ownership)
    user_settings.py
    enums.py

  schemas/                   # Pydantic API DTOs ONLY
    portfolio.py
    taxes.py
    settings.py
    accounts.py
    corporate_actions.py

  db/
    session.py
    constraints.py           # legacy view/trigger bootstrap (fold into Alembic over time)

  alembic/                   # durable schema migrations
    versions/0001_baseline.py

  domains/                   # BUSINESS LOGIC ONLY (no ORM class defs)
    portfolio/
      service.py             # snapshot / net worth / category summary
      accounts.py            # register + ACATS transfer
      ingest.py              # lot + position upload rules
      queries.py
      history.py             # net-worth snapshots
      spreadsheet.py
      layout.py              # internal dataclasses (not HTTP DTOs)
      prices.py
      price_history.py       # local SQLite daily price backup
      corporate_actions.py   # stock splits adjust lots/positions
      digest.py              # monthly portfolio email digest
      jobs.py                # daily maintenance + monthly digest entrypoints
    tlh/
      scan.py                # single harvestable-loss API
      notify.py
      jobs.py
    taxes/
      parser.py
      types.py
      brackets.py
      projection.py          # consumes domains.tlh.scan
      service.py             # prior-year + paystub write paths
    expenses/
      service.py             # scaffold only

  shared/                    # cross-cutting (no domain imports)
    email.py
    user_settings.py
    sheets.py

  routers/                   # thin HTTP adapters
    accounts.py
    portfolio.py
    ingest.py                # → domains.portfolio.ingest
    taxes.py                 # → domains.taxes.service / projection
    settings.py              # → shared.user_settings
    prices.py
    corporate_actions.py     # → domains.portfolio.corporate_actions

  scheduler.py               # APScheduler wiring → domains/*/jobs
  cli/                       # `tlh` console entrypoint
  main.py                    # register routers + start scheduler
```

**Layer dependency (strict):**

```text
routers  →  schemas + domains (+ shared)
domains  →  models + db session (+ other domains per rules below) + shared
shared   →  models + db session (no domain imports)
models   →  (nothing in domains/routers/schemas/shared)
schemas  →  (nothing in domains/models)   # pure DTOs
```

**Domain dependency (strict):**

```text
expenses ──┐
taxes ─────┼──► portfolio   (read holdings / accounts)
tlh ───────┘
taxes ──► tlh.scan
# vault-ingest Worker does not import backend domains
```

Forbidden: portfolio importing taxes/tlh/expenses; vault embedding tax brackets or reimbursement state machines; ORM models importing domains; `shared` importing `domains`.

---

## 4. Decision record (options considered)

| Option | Verdict |
| :--- | :--- |
| **A. Light cleanup only** | Rejected as end state — fixed scan dupes but no peer seat for expenses |
| **B. Vertical `domains/` packages** | **Chosen and implemented** |
| **C. Layer-first mega packages** | Rejected — domains stay scattered |
| **D. Separate deployables** | Rejected — overkill for this app |

Hard rule kept: **persistence ≠ business logic** (`models/` / `db/` / `schemas/` ≠ `domains/`).

---

## 5. Domain contracts

### Portfolio

- **Owns:** Lots, aggregate positions, cash holdings reads via views, stock prices, enriched holdings, net-worth snapshots, lot/position upload idempotency, corporate-action application to holdings.
- **Exposes:** Holdings queries, market values, ingest commands, price sync, split apply/preview.
- **Does not:** Send TLH emails; compute Form 1040; store expenses.

### TLH

- **Owns:** Unrealized-loss scan rules (taxable lots, exclusions, threshold), notification decision, daily notify job entrypoint.
- **Exposes:** `scan_harvestable_losses(db, user_id) → {total_loss, lots, …}`; `check_and_notify_tlh(user)`.
- **Does not:** Persist lots; own SMTP (calls `shared.email`).

### Taxes

- **Owns:** Paystub document events, tax ledger entries, prior-year records, projection math (brackets, SALT, safe harbor).
- **Exposes:** Ingest paystub lines; prior-year write; projection read.
- **Consumes:** `domains.tlh.scan` for capital-loss input — does not re-implement holdings scan rules.

### Expenses (expense traffic)

- **Owns (planned):** Expense rows, parse details, reimbursement status machine.
- **Today:** Package scaffold only (`stub_status`).
- **Does not:** OCR PDFs (vault); affect tax projection unless a future explicit bridge is designed.

### Vault (document upload)

- **Owns (Worker):** Upload, OCR/classify, write `vault_ingest.documents`.
- **Owns (Backend):** SQLAlchemy `Document` model and DDL as schema source of truth.
- **Bridge (future):** Named one-way helpers such as `taxes.ingest_from_document(document_id)` — not shared mud.

### Shared

- Settings access, email transport, Sheets clients, weekly digest helpers.
- Settings may *store* TLH knobs; only TLH (and tax via TLH scan) should *interpret* them for harvest math.

---

## 6. Migration status

| Phase | Work | Status |
| :--- | :--- | :--- |
| **0** | Document Option B | Done |
| **1** | Single `domains.tlh.scan`; tax projection consumes it | Done |
| **2** | `domains.portfolio.ingest`; thin `routers/ingest.py` | Done |
| **3** | Stand up `domains/{portfolio,tlh,taxes,expenses}/` + `shared/`; remove `services/` | Done |
| **4** | Split catch-all HTTP schemas; remove barrels | Done |
| **5** | Import-linter contracts in `pyproject.toml` | Done |
| **6** | Thin accounts/taxes routers; domain jobs + scheduler | Done |
| **7** | Alembic baseline (`alembic/versions/0001_baseline.py`) | Done |
| **Follow-ups** | See §8 | Open |

---

## 7. Testing expectations

- **TLH scan:** exclusions, threshold, empty portfolio (`test_regression.py`).
- **Tax projection:** calls scan via `domains.tlh.scan` (incl. `harvested_losses_override`).
- **Portfolio ingest:** idempotent lot insert + position upsert at domain layer.
- **Corporate actions:** apply/preview tests import `domains.portfolio.corporate_actions`.
- **Expenses:** status-transition tests under expenses when APIs land.
- **Vault:** schema ownership tests in backend; Worker tests in `vault-ingest/`.

---

## 8. Remaining open items

1. **Route rename:** `/ingest/lots` kept for compatibility. Prefer `/portfolio/ingest/lots` later with a deprecation window — not required for the refactor.
2. **Fold `db.constraints` into Alembic:** Views/triggers still bootstrapped at startup when `TLH_AUTO_CREATE_SCHEMA=1`. Move them into explicit revisions over time, then default auto-create off.
3. **Expenses APIs / Telegram:** Scaffold only; build status machine here when ready.
4. **Portfolio subpackages:** Optional split of `domains/portfolio/` into `holdings/`, `prices/`, `ops/` if the package keeps growing.

---

## 9. Decision summary

| Question | Decision |
| :--- | :--- |
| Packaging style | Vertical **`domains/`** packages (Option B) |
| Persistence vs logic | `models/` + `db/` + `schemas/` ≠ `domains/` |
| Cross-cutting | `shared/` (email, settings access, sheets) |
| Tax ↔ TLH overlap | Single `domains.tlh.scan`; tax consumes it |
| Lot/position upload | `domains/portfolio/ingest.py`; thin router |
| Account register / ACATS | `domains/portfolio/accounts.py`; thin router |
| Tax writes | `domains/taxes/service.py`; thin router |
| Corporate actions | `domains/portfolio/corporate_actions.py` (not `shared/`) |
| Monthly digest | `domains/portfolio/digest.py` (not `shared/`) |
| Jobs | `scheduler.py` → `domains.portfolio.jobs` / `domains.tlh.jobs` |
| Schema migrations | Alembic baseline; `TLH_AUTO_CREATE_SCHEMA` for legacy bootstrap |
| Tax calculator split | `types` + `brackets` + `projection` (no monolithic calculator) |
| Document upload | Remains `vault-ingest` Worker; backend owns ORM in `models/documents.py` |
| Expense traffic | `domains/expenses/` scaffold before feature wiring |
| Terminology | Prefer `domains` over `services` for business logic |
| Microservices | Out of scope |

---

## Appendix: Pros/cons (historical)

| Approach | Pros (short) | Cons (short) |
| :--- | :--- | :--- |
| **A. Light cleanup** | Fast, low risk | Weak long-term boundaries |
| **B. Domain packages** | Clear ownership, scalable | Import churn, needs discipline |
| **C. Layer-first** | Familiar FastAPI shape | Domains stay scattered |
| **D. Split services** | Hard isolation | Over-engineered for this app |
