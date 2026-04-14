from sqlalchemy import text


def ensure_db_constraints(engine) -> None:
    """
    Create DB-level constraints that can't be expressed as simple FK/CHECK constraints.

    This runs safely on every startup (idempotent).
    """
    with engine.begin() as conn:
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
                """
            )
        )

