"""Tax domain write paths: prior-year baselines and paystub ingest."""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from models.core import User
from models.taxes import (
    PriorYearTaxRecord,
    TaxDocumentEvent,
    TaxDocumentType,
    TaxLedgerEntry,
)
from .parser import parse_paystub_line_item, sanitize_raw_tax_payload


class TaxUserNotFoundError(ValueError):
    """Raised when the target user does not exist."""


def save_prior_year_record(
    db: Session,
    *,
    user_id: UUID,
    tax_year: int,
    filing_status: str,
    fed_agi_line_11b: float,
    fed_total_tax_line_24: float,
    fed_overpayment_applied_line_36: float = 0.0,
    state_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Upsert Form 1040 / state baselines used for safe-harbor projections."""
    user = db.get(User, user_id)
    if not user:
        raise TaxUserNotFoundError("User not found")

    state_dict: dict[str, dict[str, float]] = {}
    for item in state_records or []:
        code = str(item["state_code"]).upper()
        state_dict[code] = {
            "agi": float(item["agi"]),
            "total_tax": float(item["total_tax"]),
            "overpayment_applied": float(item.get("overpayment_applied") or 0.0),
        }

    record = (
        db.query(PriorYearTaxRecord)
        .filter(
            PriorYearTaxRecord.user_id == user_id,
            PriorYearTaxRecord.tax_year == tax_year,
        )
        .first()
    )
    if not record:
        record = PriorYearTaxRecord(
            user_id=user_id,
            tax_year=tax_year,
            filing_status=filing_status,
            fed_agi_line_11b=fed_agi_line_11b,
            fed_total_tax_line_24=fed_total_tax_line_24,
            fed_overpayment_applied_line_36=fed_overpayment_applied_line_36,
            state_records=state_dict,
        )
        db.add(record)
    else:
        record.filing_status = filing_status
        record.fed_agi_line_11b = fed_agi_line_11b
        record.fed_total_tax_line_24 = fed_total_tax_line_24
        record.fed_overpayment_applied_line_36 = fed_overpayment_applied_line_36
        record.state_records = state_dict

    db.commit()
    return {
        "message": "Prior year baseline recorded successfully",
        "tax_year": tax_year,
        "federal_total_tax": fed_total_tax_line_24,
        "states_tracked": list(state_dict.keys()),
    }


def ingest_paystub(
    db: Session,
    *,
    user_id: UUID,
    tax_year: int,
    employer_name: str,
    check_date: date,
    line_items: list[Any],
    pay_period_start: date | None = None,
    pay_period_end: date | None = None,
    external_ref_id: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> TaxDocumentEvent:
    """Append a paystub document event and mapped tax ledger entries."""
    user = db.get(User, user_id)
    if not user:
        raise TaxUserNotFoundError("User not found")

    clean_payload = sanitize_raw_tax_payload(raw_payload or {})
    doc_event = TaxDocumentEvent(
        user_id=user_id,
        tax_year=tax_year,
        doc_type=TaxDocumentType.PAYSTUB,
        issuer_name=employer_name,
        check_date=check_date,
        pay_period_start=pay_period_start,
        pay_period_end=pay_period_end,
        external_ref_id=external_ref_id,
        raw_payload=clean_payload,
    )
    db.add(doc_event)
    db.flush()

    for item in line_items:
        description = item.description if hasattr(item, "description") else item["description"]
        amount = item.amount if hasattr(item, "amount") else item.get("amount", 0.0)
        item_jurisdiction = (
            item.jurisdiction if hasattr(item, "jurisdiction") else item.get("jurisdiction")
        )
        item_locality = item.locality if hasattr(item, "locality") else item.get("locality")

        tag, auto_jur, auto_loc = parse_paystub_line_item(description)
        if not tag:
            continue

        entry = TaxLedgerEntry(
            document_event_id=doc_event.id,
            user_id=user_id,
            tax_year=tax_year,
            canonical_tag=tag,
            jurisdiction=item_jurisdiction or auto_jur,
            locality=item_locality or auto_loc,
            amount=amount,
            raw_description=description,
        )
        db.add(entry)

    db.commit()
    db.refresh(doc_event)
    return doc_event
