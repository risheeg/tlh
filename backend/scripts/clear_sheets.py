import argparse
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

def clear_snapshots():
    print("[clear] Connecting to Portfolio Snapshot worksheet...")
    # Clear the entire worksheet
    sheets_service.snapshot_worksheet.clear()
    print("[clear] Portfolio Snapshot worksheet cleared successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clear Google Sheets data.")
    parser.add_argument(
        "target", 
        choices=["prices", "snapshots", "all"], 
        nargs="?", 
        default="all",
        help="The worksheet to clear (default: all)"
    )
    
    args = parser.parse_args()
    
    if args.target in ["prices", "all"]:
        clear_prices()
    
    if args.target in ["snapshots", "all"]:
        clear_snapshots()
