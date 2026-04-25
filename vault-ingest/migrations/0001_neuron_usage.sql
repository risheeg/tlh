CREATE TABLE IF NOT EXISTS neuron_usage (
    usage_date TEXT PRIMARY KEY,
    neurons_consumed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (neurons_consumed >= 0)
);

CREATE TRIGGER IF NOT EXISTS neuron_usage_set_updated_at
AFTER UPDATE ON neuron_usage
FOR EACH ROW
BEGIN
    UPDATE neuron_usage
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE usage_date = NEW.usage_date;
END;
