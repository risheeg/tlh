-- Ledger of every Gemini API request so we can pre-flight check the free-tier
-- limits before calling (RPM + RPD). Mirrors the ``neuron_usage`` + ``has_budget``
-- pattern: we log to D1, then query D1 before the next call to decide whether
-- to proceed or requeue with a smart delay.

CREATE TABLE IF NOT EXISTS gemini_request_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    called_at   TEXT NOT NULL,                -- ISO-8601 UTC, e.g. 2026-04-25T17:32:10.123Z
    model       TEXT NOT NULL DEFAULT '',
    outcome     TEXT NOT NULL DEFAULT 'ok',   -- 'ok' | 'rate_limit' | 'transient' | 'error'
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS gemini_request_log_called_at
    ON gemini_request_log (called_at);
