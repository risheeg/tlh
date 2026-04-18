from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from db.session import get_db
from services.prices import sync_stock_prices

router = APIRouter(prefix="/prices", tags=["prices"])

@router.post("/sync", status_code=status.HTTP_200_OK)
def trigger_price_sync(db: Session = Depends(get_db)):
    """
    Manually triggers the stock price synchronization with Google Sheets.
    """
    result = sync_stock_prices(db)
    return {
        "message": "Stock prices synchronized successfully",
        "details": result
    }
