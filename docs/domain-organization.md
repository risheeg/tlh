# Design: Domain Organization for Backend Logics

**Status:** Proposed  
**Date:** 2026-09-07  
**Scope:** Backend FastAPI app (`backend/`). Vault-ingest Worker stays a separate DB client per `AGENT.MD`.

---

## 1. Problem

The backend already has four distinct capabilities, but they are packaged unevenly:

| Capability | Maturity | Pain |
| :--- | :--- | :--- |
| **Tax** | Package under `services/taxes/`, schema `taxes`, dedicated router | Duplicates TLH unrealized-loss scan inside the calculator |
| **TLH** | Single flat `tlh_service.py`, settings-driven, cron-only | No package boundary; logic copied into tax projection |
| **File upload** | Portfolio lot/position rules live in `routers/ingest.py`; document upload lives in `vault-ingest/` | “Ingest” means two things; portfolio upload has no service layer |
| **Expense traffic** | Models + Postgres schema `expenses` only | No service/router yet — easy to dump into the wrong place when built |

Without clearer boundaries, new work (Telegram expenses, vault→tax bridges, more tax forms) will land in the wrong module and increase coupling.

---

## 2. Goals

1. One obvious home for each capability (models, schemas, services, HTTP).
2. Explicit, one-way dependencies between domains.
3. Thin routers; business rules in services.
4. Incremental migration — no big-bang rewrite, no vault↔backend file moves.
5. Preserve existing Postgres schemas (`public`, `taxes`, `expenses`, `vault_ingest`).

### Non-goals

- Microservices / separate deployables per domain.
- Changing vault-ingest ownership of OCR/classification.
- Redesigning the tax formula or TLH email copy in this doc.
- Frontend architecture.

---

## 3. Current architecture (as-is)

```text
routers/          → HTTP (taxes, ingest, portfolio, settings, …)
services/
  taxes/          → parser + calculator (also scans holdings for TLH losses)
  portfolio/      → net worth, queries, history, spreadsheet
  tlh_service.py  → scan + notify (duplicates scan logic)
  …               → email, prices, settings, digest (flat)
models/           → split files + barrel `models.py`
schemas/          → taxes/settings/portfolio + catch-all `schemas.py`
vault-ingest/     → separate Worker writing `vault_ingest.documents`
```

**Known couplings**

- Tax calculator and TLH both query `PortfolioHoldingEnriched` with the same exclusion rules.
- Daily job in `main.py` orchestrates prices → net-worth snapshot → TLH.
- Lot/position upload business rules sit in the ingest router.
- Vault can classify paystubs/tax docs but does not call tax or expense APIs.

---

## 4. Options

### Option A — Status quo + light cleanup

Keep the current folder layout. Extract a shared `get_harvestable_losses()` helper. Move ingest router logic into `services/portfolio/`. Add `services/expenses/` when needed. Do not introduce a `domains/` tree.

| Pros | Cons |
| :--- | :--- |
| Lowest churn; smallest PR surface | Boundaries stay implicit; new contributors must “know” conventions |
| Matches what already works for `taxes/` and `portfolio/` | Flat `services/*.py` files keep growing |
| Easy to land the TLH/tax scan fix immediately | `schemas/schemas.py` and barrel imports remain fuzzy |
| No import-path churn for existing tests | Harder to see “expense traffic” as a first-class peer |

**Best when:** You only want the scan dedupe and ingest thin-router fix soon.

---

### Option B — Vertical domain packages (recommended) — **chosen: `domains/`**

**Hard rule: persistence ≠ business logic.**

| Layer | Folder | Contains | Must not contain |
| :--- | :--- | :--- | :--- |
| Persistence | `models/`, `db/` | SQLAlchemy ORM, enums, table DDL helpers, DB views/constraints | Tax brackets, TLH thresholds, ingest rules, email copy |
| API contracts | `schemas/` | Pydantic request/response DTOs | DB sessions, ORM queries, side effects |
| Business logic | `domains/<name>/` | Domain rules, orchestration, pure helpers | ORM *class definitions*, table schema |
| Cross-cutting | `shared/` | Email transport, settings access, digest helpers | Domain-specific tax/TLH/expense rules |
| HTTP | `routers/` | Parse request → call domain → return schema | SQL business rules |

Organize **business logic** by capability under `domains/`; keep **ORM/schema** in top-level packages. Rename today’s `services/` into this layout (migrate incrementally).

```text
backend/
  models/                    # ORM ONLY
    core.py                  # User, Account
    portfolio.py             # Lot, AggregatePosition, StockPrice, views
    taxes.py
    expenses.py
    documents.py             # vault_ingest.documents (DDL ownership)
    user_settings.py
    enums.py
    # deprecate barrel models/models.py over time

  schemas/                   # Pydantic API DTOs ONLY
    portfolio.py             # includes lot/position upload shapes
    taxes.py
    expenses.py              # add when APIs land
    settings.py
    # split remaining catch-all schemas/schemas.py

  db/
    session.py
    constraints.py           # schemas, triggers, views

  domains/                   # BUSINESS LOGIC ONLY (no ORM class defs)
    portfolio/
      service.py
      ingest.py              # ← logic currently in routers/ingest.py
      queries.py
      history.py
      spreadsheet.py
      prices.py
    tlh/
      scan.py                # harvestable unrealized losses (shared input)
      notify.py
      jobs.py
    taxes/
      parser.py
      calculator.py          # consumes tlh.scan or portfolio scan helper
      service.py
    expenses/
      service.py             # status machine; Telegram later

  shared/                    # cross-cutting helpers (not a product domain)
    email.py
    user_settings.py
    weekly_digest.py
    corporate_actions.py     # or under domains/portfolio if preferred
    sheets.py

  routers/                   # thin HTTP adapters only
    accounts.py
    portfolio.py
    ingest.py                # delegates to domains.portfolio.ingest
    taxes.py
    expenses.py              # later
    settings.py
    prices.py
    corporate_actions.py

  main.py                    # register routers + schedule jobs
```

Routers stay top-level (FastAPI discovery stays simple) but only call into `domains.*` / `shared.*`.

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
taxes ──► tlh.scan          (or portfolio.unrealized helper — pick one)
# vault-ingest Worker does not import backend domains
```

Forbidden: portfolio importing taxes/tlh/expenses; vault embedding tax brackets or reimbursement state machines; ORM models importing domains.

| Pros | Cons |
| :--- | :--- |
| Clear ownership; new features have an obvious folder | More import moves; temporary dual paths during migration |
| Mirrors Postgres schemas (`taxes`, `expenses`, `vault_ingest`) | Slightly deeper paths than today’s flat services |
| Forces thin routers and shared scan extraction | Overkill if expenses/vault bridges stay dormant for a long time |
| Easy to review PRs by domain | Requires discipline (lint/import-linter optional later) |
| Scales when expense traffic and vault→ledger bridges land | Must document “shared” carefully so it doesn’t become a junk drawer |

**Best when:** You expect expenses + more tax/TLH work soon and want structure to guide it.

---

### Option C — Layer-first mega packages

Keep `models/`, `schemas/`, `services/`, `routers/` as the primary split; enforce naming prefixes (`tax_*`, `tlh_*`, `expense_*`) and maybe subfolders only under `services/`.

| Pros | Cons |
| :--- | :--- |
| Familiar FastAPI textbook layout | Cross-cutting features still scatter across four trees |
| Minimal mental model change | Easy to “just add one more function” in the wrong service file |
| Works fine at small scale | Domain ownership still tribal knowledge |

**Best when:** Team strongly prefers layer folders over feature folders and will stay small.

---

### Option D — Separate services / deployables

Split tax, TLH, expenses, portfolio into separate apps or Workers with their own DBs or RPC.

| Pros | Cons |
| :--- | :--- |
| Hard isolation; independent deploy/scale | Far too heavy for a single-user / small net-worth app |
| | Cross-domain projection (tax + TLH losses) needs network contracts |
| | Violates current “backend owns schema” simplicity |

**Best when:** Not recommended for this codebase.

---

## 5. Recommendation

**Adopt Option B**, migrated in phases (see §7), starting with Option A’s concrete fixes so value lands early:

1. Extract `domains.tlh.scan` (or `domains.portfolio.unrealized`) as the single harvestable-loss API.
2. Tax calculator calls that API; delete duplicated scan code.
3. Move lot/position upload into `domains.portfolio.ingest`; keep HTTP under a portfolio-tagged router (prefer `/portfolio/ingest/...`; keep `/ingest/...` aliases temporarily if needed).
4. Move business logic from `services/` → `domains/{portfolio,tlh,taxes,expenses}/`. Keep ORM in `models/` and DTOs in `schemas/` — do **not** move table classes into domain packages. Put email/settings/digest under `shared/`.
5. Leave vault-ingest alone; backend keeps `Document` in `models/documents.py`. Any paystub→tax or receipt→expense path is an **explicit bridge in domains**, not shared mud.

### Why not stay on Option A forever?

Option A fixes the worst bug (duplicated TLH math) but does not give expense traffic a peer seat next to tax/TLH. Option B’s cost is mostly moves and import updates — acceptable while the surface area is still small.

---

## 6. Domain contracts (what each owns)

### Portfolio

- **Owns:** Lots, aggregate positions, stock prices, enriched holdings view, net-worth snapshots, lot/position upload idempotency.
- **Exposes:** Holdings queries, market values, ingest commands.
- **Does not:** Send TLH emails; compute Form 1040; store expenses.

### TLH

- **Owns:** Unrealized-loss scan rules (taxable lots, exclusions, threshold), notification decision, daily notify job entrypoint.
- **Exposes:** `scan_harvestable_losses(user_id) → {total_loss, lots, …}`; `check_and_notify(user_id)`.
- **Does not:** Persist lots; own SMTP implementation (calls shared email).

### Taxes

- **Owns:** Paystub document events, tax ledger entries, prior-year records, projection math (brackets, SALT, safe harbor).
- **Exposes:** Ingest paystub lines; prior-year write; projection read.
- **Consumes:** `tlh.scan` (or override) for capital-loss input — does not re-query holdings for the same rules.

### Expenses (expense traffic)

- **Owns:** Expense rows, parse details, reimbursement status machine (`pending` → … / `to_be_reimbursed` → `filed` → `received`).
- **Exposes:** Create/verify expenses; update reimbursement; list by trip/user (when APIs exist).
- **Does not:** OCR PDFs (vault); affect tax projection unless a future explicit bridge is designed.

### Vault (document upload)

- **Owns (Worker):** Upload, OCR/classify, write `vault_ingest.documents`.
- **Owns (Backend):** SQLAlchemy `Document` model and DDL as schema source of truth.
- **Bridge (future, optional):** `taxes.ingest_from_document(document_id)` or `expenses.create_from_document(document_id)` — named, one-way, testable.

### Shared

- Users, accounts, settings storage, email transport, DB session/engine, schedulers wiring.
- Settings may *store* TLH knobs; only TLH (and tax via TLH scan) should *interpret* them for harvest math.

---

## 7. Migration plan

| Phase | Work | Risk | Exit criteria |
| :--- | :--- | :--- | :--- |
| **0** | Document this design; no code moves | None | Team aligned on Option B |
| **1** | Extract shared harvestable-loss scan; tax + TLH both use it; add/adjust regression tests | Low | No duplicated holdings scan; tests green |
| **2** | Portfolio ingest in `domains.portfolio`; thin `routers/ingest.py` | Low | Router has no SQL business rules |
| **3** | Stand up `domains/{portfolio,tlh,taxes,expenses}/` + `shared/`; migrate off `services/` | Medium | New code lands in `domains/`; expenses has a home |
| **4** | Split catch-all `schemas/schemas.py`; prefer domain imports over `models.models` barrel | Medium | New code never imports the barrel |
| **5** | Optional: import-linter (`domains` ↛ define ORM; `models` ↛ `domains`) | Medium | CI fails illegal imports |

Phases 1–4 are **done** (2026-09-08). Phase 5 remains optional polish.

---

## 8. Testing expectations

- **TLH scan:** unit tests for exclusions, threshold, empty portfolio (already partially in `test_regression.py`).
- **Tax projection:** tests call scan via the public TLH/portfolio helper (including `harvested_losses_override`).
- **Portfolio ingest:** idempotent lot insert + position upsert tests at service layer.
- **Expenses:** when APIs land, status-transition tests live under expenses — not taxes or vault.
- **Vault:** schema ownership tests remain in backend; Worker tests stay in `vault-ingest/`.

---

## 9. Open questions

1. **Route rename:** Keep `/ingest/lots` forever, or migrate to `/portfolio/ingest/lots` with a deprecation window?
2. **Scan ownership:** Prefer `domains.tlh.scan` (harvest semantics) vs `domains.portfolio.unrealized_losses` (data semantics)? Recommendation: **TLH owns the function**, portfolio owns the holdings view it reads.
3. **Settings home:** Stay in `shared` with TLH-specific fields, or move TLH settings into the TLH package with a thin settings facade?
4. **Folder name:** **`domains/`** for business logic (chosen). Cross-cutting helpers live in `shared/`. ORM stays in `models/`.

---

## 10. Decision summary

| Question | Decision |
| :--- | :--- |
| Packaging style | Vertical **`domains/`** packages (Option B) |
| Persistence vs logic | `models/` + `db/` + `schemas/` ≠ `domains/` |
| Cross-cutting | `shared/` (email, settings access, digest) |
| Tax ↔ TLH overlap | Single scan helper; tax consumes it (no duplicated scan) |
| Lot/position upload | `domains/portfolio/ingest.py`; thin router |
| Document upload | Remains `vault-ingest` Worker; backend owns ORM in `models/documents.py` |
| Expense traffic | `domains/expenses/` before feature wiring |
| Terminology | Prefer `domains` over `services` for business logic |
| Microservices | Out of scope |

---

## Appendix: Pros/cons cheat sheet

| Approach | Pros (short) | Cons (short) |
| :--- | :--- | :--- |
| **A. Light cleanup** | Fast, low risk | Weak long-term boundaries |
| **B. Domain packages** | Clear ownership, scalable | Import churn, needs discipline |
| **C. Layer-first** | Familiar FastAPI shape | Domains stay scattered |
| **D. Split services** | Hard isolation | Over-engineered for this app |
