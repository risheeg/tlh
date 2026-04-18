import json
import sys
from pathlib import Path
from datetime import date

def validate_lots(file_path):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File {file_path} not found.")
        return False

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format: {e}")
        return False

    if "user_id" not in data:
        print("Error: Missing 'user_id' in root object.")
        return False
    
    if "lots" not in data or not isinstance(data["lots"], list):
        print("Error: Missing or invalid 'lots' list.")
        return False

    required_fields = {
        "account_id": str,
        "ticker": str,
        "quantity": str,
        "original_purchase_price": str,
        "current_adjusted_basis": str,
        "purchase_date": str,
        "status": str,
    }

    from collections import defaultdict
    ticker_stats = defaultdict(lambda: {"count": 0, "quantity": 0.0})

    errors = 0
    for i, lot in enumerate(data["lots"]):
        lot_id = lot.get("external_ref_id", f"index {i}")
        for field, expected_type in required_fields.items():
            if field not in lot:
                print(f"Error [Lot {lot_id}]: Missing field '{field}'")
                errors += 1
    
        # Validate date format
        if "purchase_date" in lot:
            try:
                date.fromisoformat(lot["purchase_date"])
            except ValueError:
                print(f"Error [Lot {lot_id}]: Invalid date format '{lot['purchase_date']}'. Expected YYYY-MM-DD.")
                errors += 1
        
        # Collect stats
        if "ticker" in lot and "quantity" in lot:
            ticker = lot["ticker"]
            try:
                qty = float(lot["quantity"])
                ticker_stats[ticker]["count"] += 1
                ticker_stats[ticker]["quantity"] += qty
            except ValueError:
                pass # Already handled by type check if we added one, but good to be safe

    if errors > 0:
        print(f"\nValidation failed with {errors} errors.")
        return False
    
    print(f"✓ Successfully validated {len(data['lots'])} lots in {file_path}\n")
    print(f"{'Ticker':<10} | {'Lots':<6} | {'Total Quantity':<15}")
    print("-" * 35)
    for ticker in sorted(ticker_stats.keys()):
        stats = ticker_stats[ticker]
        print(f"{ticker:<10} | {stats['count']:<6} | {stats['quantity']:<15.6f}")
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 validate_lots.py <path_to_lots_json>")
        sys.exit(1)
    
    success = validate_lots(sys.argv[1])
    sys.exit(0 if success else 1)
