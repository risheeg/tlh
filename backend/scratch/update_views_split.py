
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv("../.env")

database_url = os.getenv("NEON_DB_HOST")
if not database_url:
    print("NEON_DB_HOST not set")
    exit(1)

sql = """
-- Drop existing views to allow column changes
DROP VIEW IF EXISTS portfolio_holdings_enriched;
DROP VIEW IF EXISTS portfolio_aggregated_positions;

-- 1. Aggregation Layer: Summing lots and combining with aggregate positions
CREATE VIEW portfolio_aggregated_positions AS
-- 1.1. Aggregated Tax Lots (taxable accounts)
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

-- 1.2. Aggregate Positions (retirement/cash accounts)
SELECT 
    ap.id AS holding_id,
    ap.user_id,
    ap.account_id,
    ap.ticker,
    ap.quantity,
    ap.cost_basis,
    'aggregate'::text AS holding_type,
    ap.asset_type::text AS asset_type
FROM aggregate_positions ap;

-- 2. Enrichment Layer: Joining with stock prices for market data
CREATE VIEW portfolio_holdings_enriched AS
SELECT 
    pap.holding_id,
    pap.user_id,
    pap.account_id,
    pap.ticker,
    pap.quantity,
    pap.cost_basis,
    CASE 
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
        WHEN pap.asset_type = 'Cash' THEN CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
        ELSE sp.last_updated 
    END AS price_last_updated
FROM portfolio_aggregated_positions pap
LEFT JOIN stock_prices sp ON pap.ticker = sp.ticker AND pap.asset_type = 'Equity';
"""

engine = create_engine(database_url)
with engine.connect() as conn:
    for statement in sql.split(";"):
        if statement.strip():
            conn.execute(text(statement))
    conn.commit()
    print("Portfolio views (aggregation + enrichment) created successfully.")
