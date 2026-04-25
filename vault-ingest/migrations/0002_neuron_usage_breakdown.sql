-- Add a breakdown column that accumulates a JSON payload per day with:
-- { markdown_tokens, markdown_neurons, llm_tokens, llm_neurons }
-- Stored as TEXT (JSON) and updated via JSON patch on each write.

ALTER TABLE neuron_usage ADD COLUMN usage_breakdown TEXT NOT NULL DEFAULT '{"markdown_tokens":0,"markdown_neurons":0,"llm_tokens":0,"llm_neurons":0}';
