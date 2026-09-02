from sqlalchemy import text


def ensure_db_schemas(engine) -> None:
    """Create PostgreSQL schemas used by SQLAlchemy models before create_all."""
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS vault_ingest;"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS expenses;"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS taxes;"))


def ensure_db_constraints(engine) -> None:
    """
    Create DB-level constraints that can't be expressed as simple FK/CHECK constraints.

    This runs safely on every startup (idempotent).
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS accounts
                ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
                """
            )
        )

        conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS net_worth_snapshots
                ADD COLUMN IF NOT EXISTS comments TEXT;
                """
            )
        )

        # Preserve per-share basis precision after stock splits. The portfolio
        # views depend on these columns, so refresh them around the type change.
        conn.execute(
            text(
                """
                DROP VIEW IF EXISTS portfolio_holdings_enriched;
                DROP VIEW IF EXISTS portfolio_aggregated_positions;

                ALTER TABLE IF EXISTS lots
                ALTER COLUMN original_purchase_price TYPE NUMERIC(18, 8)
                USING original_purchase_price::numeric,
                ALTER COLUMN current_adjusted_basis TYPE NUMERIC(18, 8)
                USING current_adjusted_basis::numeric;

                -- Create cash_holdings table if missing (idempotent setup)
                CREATE TABLE IF NOT EXISTS cash_holdings (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id),
                    account_id UUID NOT NULL REFERENCES accounts(id),
                    amount NUMERIC(18, 2) NOT NULL,
                    last_updated TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE VIEW portfolio_aggregated_positions AS
                SELECT
                    md5(l.account_id::text || l.ticker)::uuid AS holding_id,
                    l.user_id,
                    l.account_id,
                    l.ticker,
                    SUM(l.quantity) AS quantity,
                    SUM(l.quantity * l.original_purchase_price) AS cost_basis,
                    'lot'::text AS holding_type,
                    'Equity'::text AS asset_type
                FROM lots l
                WHERE l.status = 'active'
                GROUP BY l.user_id, l.account_id, l.ticker

                UNION ALL

                SELECT
                    ap.id AS holding_id,
                    ap.user_id,
                    ap.account_id,
                    ap.ticker,
                    ap.quantity,
                    ap.cost_basis,
                    'aggregate'::text AS holding_type,
                    'Equity'::text AS asset_type
                FROM aggregate_positions ap
                WHERE asset_type = 'Equity' OR asset_type IS NULL

                UNION ALL

                SELECT
                    ch.id AS holding_id,
                    ch.user_id,
                    ch.account_id,
                    'CASH'::text AS ticker,
                    ch.amount AS quantity,
                    ch.amount AS cost_basis,
                    'cash'::text AS holding_type,
                    'Cash'::text AS asset_type
                FROM cash_holdings ch;

                CREATE VIEW portfolio_holdings_enriched AS
                SELECT
                    pap.holding_id,
                    pap.user_id,
                    pap.account_id,
                    pap.ticker,
                    pap.quantity,
                    pap.cost_basis,
                    CASE
                        WHEN pap.asset_type = 'Cash' THEN 1.0
                        WHEN pap.quantity > 0 THEN pap.cost_basis / pap.quantity
                        ELSE 0
                    END AS original_purchase_price,
                    pap.holding_type,
                    pap.asset_type,
                    CASE
                        WHEN pap.asset_type = 'Cash' THEN 'Cash/Cash Equivalents'::text
                        ELSE sp.category
                    END AS category,
                    CASE
                        WHEN pap.asset_type = 'Cash' THEN 0::numeric
                        ELSE sp.expense_ratio
                    END AS expense_ratio,
                    CASE
                        WHEN pap.asset_type = 'Cash' THEN 1.0
                        ELSE sp.price
                    END AS current_price,
                    CASE
                        WHEN pap.asset_type = 'Cash' THEN pap.quantity
                        ELSE pap.quantity * sp.price
                    END AS market_value,
                    CASE
                        WHEN pap.asset_type = 'Cash' THEN pap.last_updated
                        ELSE sp.last_updated
                    END AS price_last_updated
                FROM (
                    SELECT pap.*, 
                           COALESCE(ap.last_updated, ch.last_updated, CURRENT_TIMESTAMP) as last_updated
                    FROM portfolio_aggregated_positions pap
                    LEFT JOIN aggregate_positions ap ON pap.holding_id = ap.id AND pap.holding_type = 'aggregate'
                    LEFT JOIN cash_holdings ch ON pap.holding_id = ch.id AND pap.holding_type = 'cash'
                ) pap
                LEFT JOIN stock_prices sp ON pap.ticker = sp.ticker AND pap.asset_type = 'Equity';
                """
            )
        )

        # Enforce: lots can only be associated to taxable accounts.
        conn.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION enforce_lots_taxable_account()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                DECLARE
                    acct_type text;
                BEGIN
                    SELECT type::text INTO acct_type
                    FROM accounts
                    WHERE id = NEW.account_id;

                    IF acct_type IS NULL THEN
                        RAISE EXCEPTION 'Account % does not exist', NEW.account_id;
                    END IF;

                    IF acct_type <> 'taxable' THEN
                        RAISE EXCEPTION
                            'Lots can only belong to taxable accounts. Account % is %',
                            NEW.account_id, acct_type
                            USING ERRCODE = '23514';
                    END IF;

                    RETURN NEW;
                END;
                $$;
                """
            )
        )

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_trigger
                        WHERE tgname = 'lots_enforce_taxable_account'
                    ) THEN
                        CREATE TRIGGER lots_enforce_taxable_account
                        BEFORE INSERT OR UPDATE OF account_id ON lots
                        FOR EACH ROW
                        EXECUTE FUNCTION enforce_lots_taxable_account();
                    END IF;
                END
                $$;

                -- Ensure vault_ingest.documents has a user_id with FK to users.
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'vault_ingest' AND table_name = 'documents'
                    ) THEN
                        -- Add user_id column if missing
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_schema = 'vault_ingest' AND table_name = 'documents' AND column_name = 'user_id'
                        ) THEN
                            ALTER TABLE vault_ingest.documents ADD COLUMN user_id UUID;
                        END IF;

                        -- Ensure user_id is NOT NULL
                        ALTER TABLE vault_ingest.documents ALTER COLUMN user_id SET NOT NULL;

                        -- Add Foreign Key if missing
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.table_constraints 
                            WHERE table_schema = 'vault_ingest' AND table_name = 'documents' AND constraint_type = 'FOREIGN KEY'
                        ) THEN
                            ALTER TABLE vault_ingest.documents 
                            ADD CONSTRAINT fk_documents_user_id 
                            FOREIGN KEY (user_id) REFERENCES users(id);
                        END IF;
                    END IF;
                END
                $$;
                """
            )
        )
