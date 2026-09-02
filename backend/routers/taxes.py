import uuid
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db.session import get_db
from models.models import User
from models.taxes import (
    CanonicalTaxType,
    PriorYearTaxRecord,
    TaxDocumentEvent,
    TaxDocumentType,
    TaxLedgerEntry,
)
from schemas.taxes import (
    PaystubIngestRequest,
    PriorYearTaxRecordInput,
    TaxDocumentEventResponse,
)
from services.taxes.calculator import compute_tax_projections_from_logs
from services.taxes.parser import parse_paystub_line_item, sanitize_raw_tax_payload

router = APIRouter(prefix="/taxes", tags=["taxes"])


@router.post(
    "/prior-year-record",
    status_code=status.HTTP_200_OK,
    summary="Save Form 1040 and State baselines from prior tax year for Safe Harbor",
)
def save_prior_year_tax_record(payload: PriorYearTaxRecordInput, db: Session = Depends(get_db)):
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    # Convert state records list to dictionary keyed by state code
    state_dict = {
        item.state_code.upper(): {
            "agi": item.agi,
            "total_tax": item.total_tax,
            "overpayment_applied": item.overpayment_applied,
        }
        for item in payload.state_records
    }

    record = (
        db.query(PriorYearTaxRecord)
        .filter(
            PriorYearTaxRecord.user_id == payload.user_id,
            PriorYearTaxRecord.tax_year == payload.tax_year
        )
        .first()
    )
    if not record:
        record = PriorYearTaxRecord(
            user_id=payload.user_id,
            tax_year=payload.tax_year,
            filing_status=payload.filing_status,
            fed_agi_line_11b=payload.fed_agi_line_11b,
            fed_total_tax_line_24=payload.fed_total_tax_line_24,
            fed_overpayment_applied_line_36=payload.fed_overpayment_applied_line_36,
            state_records=state_dict,
        )
        db.add(record)
    else:
        record.filing_status = payload.filing_status
        record.fed_agi_line_11b = payload.fed_agi_line_11b
        record.fed_total_tax_line_24 = payload.fed_total_tax_line_24
        record.fed_overpayment_applied_line_36 = payload.fed_overpayment_applied_line_36
        record.state_records = state_dict

    db.commit()
    return {
        "message": "Prior year baseline recorded successfully",
        "tax_year": payload.tax_year,
        "federal_total_tax": payload.fed_total_tax_line_24,
        "states_tracked": list(state_dict.keys()),
    }


@router.post(
    "/ingest/paystub",
    response_model=TaxDocumentEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append a paystub document event and map to canonical tax ledger entries",
)
def ingest_paystub(payload: PaystubIngestRequest, db: Session = Depends(get_db)):
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # 1. Create append-only document event with sanitized raw payload
    clean_payload = sanitize_raw_tax_payload(payload.raw_payload or {})
    doc_event = TaxDocumentEvent(
        user_id=payload.user_id,
        tax_year=payload.tax_year,
        doc_type=TaxDocumentType.PAYSTUB,
        issuer_name=payload.employer_name,
        check_date=payload.check_date,
        pay_period_start=payload.pay_period_start,
        pay_period_end=payload.pay_period_end,
        external_ref_id=payload.external_ref_id,
        raw_payload=clean_payload,
    )
    db.add(doc_event)
    db.flush()

    # 2. Parse and map each line item to CanonicalTaxType and Jurisdiction
    ledger_entries = []
    for item in payload.line_items:
        tag, auto_jur, auto_loc = parse_paystub_line_item(item.description)
        if not tag:
            continue
            
        jurisdiction = item.jurisdiction or auto_jur
        locality = item.locality or auto_loc
        
        entry = TaxLedgerEntry(
            document_event_id=doc_event.id,
            user_id=payload.user_id,
            tax_year=payload.tax_year,
            canonical_tag=tag,
            jurisdiction=jurisdiction,
            locality=locality,
            period_amount=item.period_amount,
            ytd_amount=item.ytd_amount,
            raw_description=item.description,
        )
        db.add(entry)
        ledger_entries.append(entry)

    db.commit()
    db.refresh(doc_event)
    return doc_event


@router.get(
    "/projection",
    summary="Replay append-only logs and compute Form 1040 and State tax projections",
)
def get_tax_projection(
    user_id: uuid.UUID = Query(...),
    tax_year: int = Query(2026),
    salt_cap_override: Optional[float] = Query(None, description="Custom SALT cap limit (default: $20,000 Single / $40,000 MFJ)"),
    mortgage_interest: float = Query(0.0, description="Annual mortgage interest (Schedule A)"),
    charitable_contributions: float = Query(0.0, description="Annual charitable gifts (Schedule A)"),
    property_taxes: float = Query(0.0, description="Annual real estate / property taxes"),
    harvested_losses_override: Optional[float] = Query(None, description="Harvested capital loss amount (capped at -$3,000 against ordinary income)"),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    result = compute_tax_projections_from_logs(
        db=db,
        user_id=user_id,
        tax_year=tax_year,
        salt_cap_override=salt_cap_override,
        mortgage_interest=mortgage_interest,
        charitable_contributions=charitable_contributions,
        property_taxes=property_taxes,
        harvested_losses_override=harvested_losses_override,
    )
    return result
