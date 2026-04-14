# Database Schema

## Overview

The TLH backend uses a PostgreSQL database (hosted on Neon) with four core tables.

---

## Table: `users`
Stores core user identity and account-level metadata.

| Field | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Primary Key | Unique identifier for the user. |
| `email` | String | Unique, Indexed | User's email for login and notifications. |
| `created_at` | DateTime (UTC) | Not Null | Timestamp of account creation. |

---

## Table: `accounts`
Represents a real-world brokerage or holding entity (e.g., "Fidelity," "Vanguard IRA").

| Field | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Primary Key | Unique identifier for the account. |
| `user_id` | UUID | Foreign Key (`users.id`), Indexed | Owner of the account. |
| `name` | String | Not Null | User-defined name (e.g., "Main Brokerage"). |
| `type` | Enum | Not Null | `taxable` or `retirement`. |
| `institution` | String | Nullable | Name of the provider (e.g., "Schwab"). |
| `created_at` | DateTime (UTC) | Not Null | Timestamp of creation. |

---

## Table: `lots`
Stores individual tax lots. **Must only be associated with `taxable` type accounts.**

| Field | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Primary Key | Unique identifier for the lot. |
| `user_id` | UUID | Foreign Key (`users.id`), Indexed | Owner of the lot. |
| `account_id` | UUID | Foreign Key (`accounts.id`), Indexed | The specific taxable account holding this lot. |
| `ticker` | String | Indexed | Stock symbol (e.g., "NVDA"). |
| `quantity` | Numeric (18,8) | Not Null | Number of shares currently held. |
| `original_purchase_price` | Numeric (18,2) | Not Null | Price per share at acquisition. |
| `current_adjusted_basis` | Numeric (18,2) | Not Null | **[MATERIALIZED STATE]** The IRS-compliant basis. |
| `purchase_date` | Date | Not Null | Date of acquisition. |
| `status` | Enum | Default: `active` | `active`, `closed`, `ignored`. |
| `external_ref_id` | String | Unique, Indexed | Deterministic hash for idempotency. |

---

## Table: `aggregate_positions`
Stores high-level totals for accounts where lot-level tracking is unnecessary.  
Usually mapped to `retirement` type accounts.

| Field | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Primary Key | Unique identifier. |
| `user_id` | UUID | Foreign Key (`users.id`), Indexed | Owner of the position. |
| `account_id` | UUID | Foreign Key (`accounts.id`), Indexed | The specific account holding this total. |
| `ticker` | String | Indexed | Asset symbol. |
| `quantity` | Numeric (18,8) | Not Null | Total shares held in this specific account. |
| `last_updated` | DateTime (UTC) | Not Null | Timestamp of last user update. |

---

## Relationships

```
users
 ├── accounts  (one-to-many)
 ├── lots      (one-to-many, taxable accounts only)
 └── aggregate_positions (one-to-many)

accounts
 ├── lots               (one-to-many, type=taxable only)
 └── aggregate_positions (one-to-many)
```

## Key Business Rules

- **Lots → taxable accounts only**: The API enforces that any uploaded lot's `account_id` must reference an account with `type = taxable`.
- **Aggregate positions → upsert**: Uploading a position for an existing `(user, account, ticker)` triple updates it in place rather than creating a duplicate.
- **Idempotency via `external_ref_id`**: Lot uploads with a duplicate `external_ref_id` are silently skipped so callers can safely re-submit.
