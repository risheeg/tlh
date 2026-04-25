-- Change neurons_consumed from INTEGER to REAL to support fractional neuron values.
-- SQLite does not support ALTER COLUMN, so we recreate the table.

CREATE TABLE neuron_usage_new (
    usage_date       TEXT PRIMARY KEY,
    neurons_consumed REAL NOT NULL DEFAULT 0.0,
    usage_breakdown  TEXT NOT NULL DEFAULT '{"markdown_output_tokens":0,"markdown_neurons":0.0,"llm_input_tokens":0,"llm_input_neurons":0.0,"llm_output_tokens":0,"llm_output_neurons":0.0}',
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (neurons_consumed >= 0.0)
);

INSERT INTO neuron_usage_new SELECT * FROM neuron_usage;

DROP TABLE neuron_usage;

ALTER TABLE neuron_usage_new RENAME TO neuron_usage;

CREATE TRIGGER IF NOT EXISTS neuron_usage_set_updated_at
AFTER UPDATE ON neuron_usage
FOR EACH ROW
BEGIN
    UPDATE neuron_usage
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE usage_date = NEW.usage_date;
END;
