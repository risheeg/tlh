import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db.session import get_db
from domains.taxes.projection import compute_tax_projections_from_logs
from domains.taxes.service import (
    TaxUserNotFoundError,
    ingest_paystub,
    save_prior_year_record,
)
from models.core import User
from schemas.taxes import (
    PaystubIngestRequest,
    PriorYearTaxRecordInput,
    TaxDocumentEventResponse,
)

router = APIRouter(prefix="/taxes", tags=["taxes"])


@router.post(
    "/prior-year-record",
    status_code=status.HTTP_200_OK,
    summary="Save Form 1040 and State baselines from prior tax year for Safe Harbor",
)
def save_prior_year_tax_record(payload: PriorYearTaxRecordInput, db: Session = Depends(get_db)):
    try:
        return save_prior_year_record(
            db,
            user_id=payload.user_id,
            tax_year=payload.tax_year,
            filing_status=payload.filing_status,
            fed_agi_line_11b=payload.fed_agi_line_11b,
            fed_total_tax_line_24=payload.fed_total_tax_line_24,
            fed_overpayment_applied_line_36=payload.fed_overpayment_applied_line_36,
            state_records=[item.model_dump() for item in payload.state_records],
        )
    except TaxUserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/ingest/paystub",
    response_model=TaxDocumentEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append a paystub document event and map to canonical tax ledger entries",
)
def ingest_paystub_endpoint(payload: PaystubIngestRequest, db: Session = Depends(get_db)):
    try:
        return ingest_paystub(
            db,
            user_id=payload.user_id,
            tax_year=payload.tax_year,
            employer_name=payload.employer_name,
            check_date=payload.check_date,
            line_items=payload.line_items,
            pay_period_start=payload.pay_period_start,
            pay_period_end=payload.pay_period_end,
            external_ref_id=payload.external_ref_id,
            raw_payload=payload.raw_payload or {},
        )
    except TaxUserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/projection",
    summary="Replay append-only logs and compute Form 1040 and State tax projections",
)
def get_tax_projection(
    user_id: uuid.UUID = Query(...),
    tax_year: int = Query(2026),
    salt_cap_override: Optional[float] = Query(
        None, description="Custom SALT cap limit (default: $20,000 Single / $40,000 MFJ)"
    ),
    mortgage_interest: float = Query(0.0, description="Annual mortgage interest (Schedule A)"),
    charitable_contributions: float = Query(
        0.0, description="Annual charitable gifts (Schedule A)"
    ),
    property_taxes: float = Query(0.0, description="Annual real estate / property taxes"),
    harvested_losses_override: Optional[float] = Query(
        None,
        description="Harvested capital loss amount (capped at -$3,000 against ordinary income)",
    ),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return compute_tax_projections_from_logs(
        db=db,
        user_id=user_id,
        tax_year=tax_year,
        salt_cap_override=salt_cap_override,
        mortgage_interest=mortgage_interest,
        charitable_contributions=charitable_contributions,
        property_taxes=property_taxes,
        harvested_losses_override=harvested_losses_override,
    )
