"""
Router: /ingest — thin HTTP adapter for lot/position uploads.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from db.session import get_db
from domains.portfolio.ingest import upload_lots, upload_positions
from schemas.portfolio import (
    AggregatePositionUploadRequest,
    AggregatePositionUploadResponse,
    LotUploadRequest,
    LotUploadResponse,
)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post(
    "/lots",
    response_model=LotUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload tax lots",
    description=(
        "Batch-upload individual tax lots for a user. "
        "Lots must belong to a **taxable** account. "
        "Lots with a duplicate `external_ref_id` are silently skipped (idempotent)."
    ),
)
def post_upload_lots(payload: LotUploadRequest, db: Session = Depends(get_db)):
    return upload_lots(db, payload)


@router.post(
    "/positions",
    response_model=AggregatePositionUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload aggregate positions",
    description=(
        "Batch-upload (upsert) aggregate stock positions for a user. "
        "If a position for the same (user, account, ticker) already exists it is "
        "updated in place; otherwise a new record is created."
    ),
)
def post_upload_positions(
    payload: AggregatePositionUploadRequest, db: Session = Depends(get_db)
):
    return upload_positions(db, payload)
