# TLH & Net Worth Tracker

A sleek, premium backend application built with FastAPI for tracking net worth and identifying Tax Loss Harvesting (TLH) opportunities.

## 🚀 Overview

This application provides users with a real-time view of their financial health by aggregating tax lots and stock positions. It proactively monitors market conditions to alert users via email when tax loss harvesting opportunities arise, helping optimize tax efficiency.

### Key Features

- **💰 Net Worth Tracking**: Real-time calculation based on active tax lots and aggregated stock positions.
- **📉 Tax Loss Harvesting Alerts**: Automatic email notifications when stocks drop below their cost basis, signaling a harvest opportunity.
- **🔄 Automated Data Ingestion**: Daily synchronization of stock prices from Google Sheets to ensure accuracy.
- **🏷️ Corporate Actions**: Reusable stock split support that adjusts stored lots and aggregate positions without changing current quote data.
- **📝 Snapshot Comments**: Optional comments on net worth snapshots for life events, account changes, or other context.
- **🖥️ Management CLI**: Robust command-line interface for account creation, lot uploads, and transaction management.
- **📅 Scheduled Jobs**: Integrated background scheduler for daily price updates and system maintenance.

## 🛠️ Technology Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Database**: [Neon](https://neon.tech/) (Serverless PostgreSQL)
- **ORM**: [SQLAlchemy](https://www.sqlalchemy.org/)
- **Package Manager**: [uv](https://github.com/astral-sh/uv)
- **Task Scheduling**: [APScheduler](https://apscheduler.readthedocs.io/)
- **Data Source**: Google Sheets API

## 🏃 Getting Started

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (Fast Python package installer and resolver)

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd tlh/backend
   ```

2. **Set up environment variables**:
   Create a `.env` file in this directory with the following configuration:
   ```env
   # Google Sheets Configuration
   GOOGLE_SHEET_ID=your_google_sheet_id
   GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/tlh/backend/google_credentials.json

   # Neon Database URL
   NEON_DB_HOST=postgresql://user:password@host/neondb?sslmode=require

   # SMTP Configuration
   SMTP_HOST=your_smtp_host
   SMTP_PORT=587
   SMTP_USER=your_smtp_user
   SMTP_PASSWORD=your_smtp_password
   EMAILS_FROM_EMAIL=your_email@example.com
   SMTP_USE_TLS=True

   # Optional: local SQLite archive for daily price history
   TLH_PRICE_HISTORY_DB_PATH=/path/to/stock_price_history.sqlite3
   ```

3. **Install dependencies**:
   ```bash
   uv sync
   ```

### Running the Application

All commands should be run from this `backend/` directory:

**Start the FastAPI Dev Server**:
```bash
uv run fastapi dev main.py
```

**Access the API Documentation**:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Redoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## API Endpoints

Base URL for local development: `http://localhost:8000`

### Health

- `GET /health` - Check that the API is running.

### Accounts

- `POST /accounts` - Create an account for a user. If the same `(user_id, name)` already exists, the existing account is returned.
- `POST /accounts/transfer-lots` - Transfer all lots from an origin taxable account to a destination taxable account via ACATS.

### Ingest

- `POST /ingest/lots` - Batch upload tax lots for taxable accounts. Duplicate `external_ref_id` values are skipped.
- `POST /ingest/positions` - Batch upsert aggregate positions by `(user_id, account_id, ticker)`.

### Portfolio

- `GET /portfolio/{user_id}/snapshot` - Return enriched holdings, total net worth, and the latest price timestamp.
- `GET /portfolio/{user_id}/net-worth` - Return the user's current total net worth and last update timestamp.
- `GET /portfolio/{user_id}/net-worth/history` - Return persisted net worth snapshots. Optional query params: `start_date`, `end_date`.
- `PATCH /portfolio/{user_id}/net-worth/history/{snapshot_date}/comments` - Update comments for a net worth snapshot.
- `POST /portfolio/{user_id}/snapshot/sync` - Append today's portfolio snapshot to Google Sheets if it has not already been synced. Optional query param: `group_by`.
- `GET /portfolio/{user_id}/allocation` - Return asset allocation by category.
- `GET /portfolio/{user_id}/snapshot/view` - Return an HTML snapshot report with multiple grouping views.

### Prices

- `POST /prices/sync` - Manually sync current stock prices from Google Sheets.

### Corporate Actions

- `POST /corporate-actions/stock-splits/preview` - Preview the impact of a stock split on stored lots and aggregate positions.
- `POST /corporate-actions/stock-splits/apply` - Apply a stock split to stored lots and aggregate positions.

### Using the CLI

Administrative tasks are also managed via the CLI from this directory:
```bash
# View available commands
tlh --help

# Example: Create a new account
tlh accounts create --name "Personal Wealth" --type taxable

# Show local API links in logical order
tlh links          # main: http://127.0.0.1:8001
tlh links devbox   # devbox: http://localhost:8000
```

The links command fills `{user_id}` path values from the active CLI user set with `tlh auth set-user`.

## Operations

### Corporate Actions

Stock splits are modeled as corporate actions and applied to stored holdings. A forward split multiplies share quantities and divides per-share basis for taxable lots; aggregate position `cost_basis` stays unchanged because it is a total basis.

Preview and apply a split from this directory:

```bash
tlh stock-splits preview --ticker VUG --effective-date 2026-04-21 --numerator 6 --denominator 1
tlh stock-splits apply --ticker VUG --effective-date 2026-04-21 --numerator 6 --denominator 1
```

The command records the split and is idempotent, so reapplying the same ticker/date/ratio will not double-adjust holdings.

### Price History Archive

`stock_prices` stores only the latest quote in Neon. During each price refresh, the refreshed prices are also written to a local SQLite archive at `var/stock_price_history.sqlite3` by default. The archive stores at most one row per ticker per UTC day and is ignored by git.

Use `TLH_PRICE_HISTORY_DB_PATH` to place the archive elsewhere on the instance.

### Net Worth Snapshot Comments

Net worth snapshots support optional free-form `comments` for life events and other context. Add comments while capturing today's snapshot, or update an existing snapshot by date:

```bash
tlh history capture --comment "Moved apartments"
tlh history comment --date 2026-04-24 --comment "VUG split applied"
```

The API also exposes snapshot history at `GET /portfolio/{user_id}/net-worth/history` and comment updates at `PATCH /portfolio/{user_id}/net-worth/history/{snapshot_date}/comments`.

## 📁 Project Structure

```text
backend/
├── AGENTS.md           # Backend project rules and guidelines
├── core/               # Configuration and core logic
├── db/                 # Database connection and session management
├── models/             # SQLAlchemy database models
├── routers/            # FastAPI route handlers (API endpoints)
├── schemas/            # Pydantic models for request/response validation
├── scripts/            # CLI tools and utility scripts
├── services/           # Business logic and external integrations
├── main.py             # Application entry point
└── README.md           # You are here!
```

## 📄 License

This project is licensed under the MIT License.
