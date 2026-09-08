"""Router: /settings — per-user product configuration."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.session import get_db
from schemas.settings import (
    UserSettingsPut,
    UserSettingsResponse,
    UserSettingsUpdate,
)
from shared.user_settings import (
    get_or_create_user_settings,
    patch_user_settings,
    put_user_settings,
    settings_to_response,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/{user_id}", response_model=UserSettingsResponse)
def get_settings(user_id: uuid.UUID, db: Session = Depends(get_db)):
    settings = get_or_create_user_settings(db, user_id)
    return settings_to_response(settings)


@router.put("/{user_id}", response_model=UserSettingsResponse)
def replace_settings(
    user_id: uuid.UUID, payload: UserSettingsPut, db: Session = Depends(get_db)
):
    settings = put_user_settings(db, user_id, payload)
    return settings_to_response(settings)


@router.patch("/{user_id}", response_model=UserSettingsResponse)
def update_settings(
    user_id: uuid.UUID, payload: UserSettingsUpdate, db: Session = Depends(get_db)
):
    settings = patch_user_settings(db, user_id, payload)
    return settings_to_response(settings)
