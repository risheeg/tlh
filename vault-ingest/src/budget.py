from utils import js_to_py, usage_date


async def get_neurons_consumed(db, date_value: str | None = None) -> int:
    date_value = date_value or usage_date()
    row = await db.prepare(
        "SELECT neurons_consumed FROM neuron_usage WHERE usage_date = ?"
    ).bind(date_value).first()
    row = js_to_py(row)
    if not row:
        return 0
    return int(row.get("neurons_consumed") or 0)


async def has_budget(db, limit: int, date_value: str | None = None) -> bool:
    return await get_neurons_consumed(db, date_value) < limit


async def add_neurons_consumed(db, amount: int, date_value: str | None = None) -> None:
    date_value = date_value or usage_date()
    amount = max(0, int(amount))
    await db.prepare(
        """
        INSERT INTO neuron_usage (usage_date, neurons_consumed)
        VALUES (?, ?)
        ON CONFLICT(usage_date)
        DO UPDATE SET neurons_consumed = neurons_consumed + excluded.neurons_consumed
        """
    ).bind(date_value, amount).run()
