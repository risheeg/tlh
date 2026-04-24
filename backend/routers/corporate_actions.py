"""
Router: /corporate-actions — endpoints for stock splits and other actions.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.session import get_db
from schemas.schemas import (
    StockSplitApplyResponse,
    StockSplitCreate,
    StockSplitPreviewResponse,
)
from services.corporate_actions import (
    StockSplitRatioConflictError,
    apply_stock_split,
    preview_stock_split,
)

router = APIRouter(prefix="/corporate-actions", tags=["corporate-actions"])


@router.post(
    "/stock-splits/preview",
    response_model=StockSplitPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview a stock split",
)
def preview_split(payload: StockSplitCreate, db: Session = Depends(get_db)):
    try:
        return preview_stock_split(db, payload)
    except StockSplitRatioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/stock-splits/apply",
    response_model=StockSplitApplyResponse,
    status_code=status.HTTP_200_OK,
    summary="Apply a stock split to stored holdings",
)
def apply_split(payload: StockSplitCreate, db: Session = Depends(get_db)):
    try:
        return apply_stock_split(db, payload)
    except StockSplitRatioConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
