import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.sheets import sheets_service

def purge_sheet():
    print("[purge] Connecting to Google Sheets...")
    # Clear the entire worksheet
    sheets_service.worksheet.clear()
    # Add a header just in case
    sheets_service.worksheet.update('A1', [['Ticker', 'Price']])
    print("[purge] Spreadsheet purged successfully (Header re-added).")

if __name__ == "__main__":
    purge_sheet()
