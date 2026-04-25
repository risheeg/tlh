from utils import js_to_py, usage_date


async def get_neurons_consumed(db, date_value: str | None = None) -> int:
    date_value = date_value or usage_date()
    row = await db.prepare(
        "SELECT neurons_consumed FROM neuron_usage WHERE usage_date = ?"
    ).bind(date_value).first()
    row = js_to_py(row)
    if not row:
        return 0
    return float(row.get("neurons_consumed") or 0.0)


async def has_budget(db, limit: int, date_value: str | None = None) -> bool:
    return await get_neurons_consumed(db, date_value) < limit


async def add_neurons_consumed(
    db,
    amount: int,
    usage_breakdown: dict | None = None,
    date_value: str | None = None,
) -> None:
    date_value = date_value or usage_date()
    amount = max(0.0, float(amount))
    bd = usage_breakdown or {}
    md_out     = float(bd.get("markdown_output_tokens", 0))
    md_neu     = float(bd.get("markdown_neurons",       0.0))
    llm_in     = float(bd.get("llm_input_tokens",       0))
    llm_in_neu = float(bd.get("llm_input_neurons",      0.0))
    llm_out    = float(bd.get("llm_output_tokens",      0))
    llm_out_neu= float(bd.get("llm_output_neurons",     0.0))
    await db.prepare(
        """
        INSERT INTO neuron_usage (usage_date, neurons_consumed, usage_breakdown)
        VALUES (?, ?, JSON_OBJECT(
            'markdown_output_tokens', ?,
            'markdown_neurons',       ?,
            'llm_input_tokens',       ?,
            'llm_input_neurons',      ?,
            'llm_output_tokens',      ?,
            'llm_output_neurons',     ?
        ))
        ON CONFLICT(usage_date) DO UPDATE SET
            neurons_consumed = neurons_consumed + excluded.neurons_consumed,
            usage_breakdown = JSON_SET(
                usage_breakdown,
                '$.markdown_output_tokens', CAST(JSON_EXTRACT(usage_breakdown, '$.markdown_output_tokens') AS INTEGER) + ?,
                '$.markdown_neurons',       CAST(JSON_EXTRACT(usage_breakdown, '$.markdown_neurons')       AS INTEGER) + ?,
                '$.llm_input_tokens',       CAST(JSON_EXTRACT(usage_breakdown, '$.llm_input_tokens')       AS INTEGER) + ?,
                '$.llm_input_neurons',      CAST(JSON_EXTRACT(usage_breakdown, '$.llm_input_neurons')      AS INTEGER) + ?,
                '$.llm_output_tokens',      CAST(JSON_EXTRACT(usage_breakdown, '$.llm_output_tokens')      AS INTEGER) + ?,
                '$.llm_output_neurons',     CAST(JSON_EXTRACT(usage_breakdown, '$.llm_output_neurons')     AS INTEGER) + ?
            )
        """
    ).bind(
        date_value, amount,
        md_out, md_neu, llm_in, llm_in_neu, llm_out, llm_out_neu,  # INSERT values
        md_out, md_neu, llm_in, llm_in_neu, llm_out, llm_out_neu,  # UPDATE deltas
    ).run()


