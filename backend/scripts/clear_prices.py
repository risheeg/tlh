import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.sheets import sheets_service

def clear_prices():
    print("[clear] Connecting to Price Tracking worksheet...")
    # Clear the entire worksheet
    sheets_service.price_worksheet.clear()
    # Add a header just in case
    sheets_service.price_worksheet.update('A1', [['Ticker', 'Price']])
    print("[clear] Price Tracking worksheet cleared successfully (Header re-added).")

if __name__ == "__main__":
    clear_prices()
