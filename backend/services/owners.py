"""Owner account seed and helpers."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import OWNER_DEFAULT_PASSWORD, OWNER_USERNAME
from backend.models import Owner
from backend.owner_auth import hash_password

logger = logging.getLogger(__name__)


def seed_owner(session: Session) -> None:
    """Create bootstrap admin if no owners exist."""
    existing = session.scalars(select(Owner).limit(1)).first()
    if existing is not None:
        return
    if not OWNER_DEFAULT_PASSWORD:
        logger.warning("OWNER_DEFAULT_PASSWORD empty; skipping owner seed")
        return
    username = OWNER_USERNAME
    session.add(
        Owner(
            username=username,
            password_hash=hash_password(OWNER_DEFAULT_PASSWORD),
            email=None,
            email_verified=False,
            setup_completed=False,
        )
    )
    logger.info("Seeded owner username=%s (setup required on first login)", username)
