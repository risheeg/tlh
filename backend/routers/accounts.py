"""
Router: /accounts — endpoints for creating user accounts.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.session import get_db
from domains.portfolio.accounts import (
    AccountNotFoundError,
    InvalidAccountTypeError,
    register_account as register_account_cmd,
    transfer_lots as transfer_lots_cmd,
)
from schemas.accounts import (
    AccountRegisterRequest,
    AccountResponse,
    TransferLotsRequest,
    TransferLotsResponse,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an account",
    description=(
        "Create an account for a user. If an account with the same (user_id, name) "
        "already exists, it is returned (idempotent)."
    ),
)
def register_account(payload: AccountRegisterRequest, db: Session = Depends(get_db)):
    try:
        return register_account_cmd(
            db,
            user_id=payload.user_id,
            name=payload.name,
            type=payload.type,
            institution=payload.institution,
        )
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/transfer-lots",
    response_model=TransferLotsResponse,
    status_code=status.HTTP_200_OK,
    summary="Transfer all lots via ACATS",
    description="Transfers all active lots from the origin account to the destination account via ACATS.",
)
def transfer_lots(payload: TransferLotsRequest, db: Session = Depends(get_db)):
    try:
        result = transfer_lots_cmd(
            db,
            user_id=payload.user_id,
            origin_account_id=payload.origin_account_id,
            destination_account_id=payload.destination_account_id,
        )
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidAccountTypeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return TransferLotsResponse(**result)
