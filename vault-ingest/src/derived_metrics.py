"""Functions to calculate mathematical metrics derived directly from extracted records."""

def derive_transaction_metrics(category: str, subcategory: str, ft: list) -> dict:
    """Derive transaction sums and counts mathematically from the list of extracted transactions."""
    metrics = {}
    metrics["transaction_count"] = len(ft)
    
    if subcategory in ["statement_bank", "statement_credit_card", "statement_venmo", "statement_hsa"]:
        pos_count = 0
        neg_count = 0
        pos_sum = 0.0
        neg_sum = 0.0
        for tx in ft:
            if not isinstance(tx, dict):
                continue
            amt = tx.get("amount")
            typ = tx.get("type")
            if isinstance(amt, (int, float)):
                if typ == "credit" or (typ is None and amt > 0):
                    pos_count += 1
                    pos_sum += abs(amt)
                elif typ == "debit" or (typ is None and amt < 0):
                    neg_count += 1
                    neg_sum += abs(amt)
        
        metrics["positive_transactions_count"] = pos_count
        metrics["negative_transactions_count"] = neg_count
        metrics["positive_transactions_sum"] = round(pos_sum, 2)
        metrics["negative_transactions_sum"] = round(neg_sum, 2)
        
    return metrics
