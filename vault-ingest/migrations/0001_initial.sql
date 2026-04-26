CREATE TABLE IF NOT EXISTS neuron_usage (
    usage_date       TEXT PRIMARY KEY,
    neurons_consumed REAL NOT NULL DEFAULT 0.0,
    usage_breakdown  TEXT NOT NULL DEFAULT '{"markdown_output_tokens":0,"markdown_neurons":0.0,"llm_input_tokens":0,"llm_input_neurons":0.0,"llm_output_tokens":0,"llm_output_neurons":0.0}',
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (neurons_consumed >= 0.0)
);

CREATE TRIGGER IF NOT EXISTS neuron_usage_set_updated_at
AFTER UPDATE ON neuron_usage
FOR EACH ROW
BEGIN
    UPDATE neuron_usage
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE usage_date = NEW.usage_date;
END;

CREATE TABLE IF NOT EXISTS gemini_request_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    called_at   TEXT NOT NULL,
    model       TEXT NOT NULL DEFAULT '',
    outcome     TEXT NOT NULL DEFAULT 'ok',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS gemini_request_log_called_at
    ON gemini_request_log (called_at);
