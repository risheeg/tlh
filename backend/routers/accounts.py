"""
Router: /accounts — endpoints for creating user accounts.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.session import get_db
from models.models import Account, User
from schemas.schemas import AccountRegisterRequest, AccountResponse

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
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = (
        db.query(Account)
        .filter(Account.user_id == payload.user_id, Account.name == payload.name)
        .first()
    )
    if existing:
        return existing

    account = Account(
        user_id=payload.user_id,
        name=payload.name,
        type=payload.type,
        institution=payload.institution,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account

