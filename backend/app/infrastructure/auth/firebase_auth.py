from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.config import FIREBASE_CREDENTIALS, FIREBASE_DISABLED

logger = logging.getLogger(__name__)

_firebase_initialized = False


def _init_firebase() -> bool:
    global _firebase_initialized
    if _firebase_initialized:
        return True
    if FIREBASE_DISABLED:
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _firebase_initialized = True
            return True

        cred_path = Path(__file__).resolve().parents[2] / "firebase_credentials.json"
        if FIREBASE_CREDENTIALS:
            info = json.loads(FIREBASE_CREDENTIALS)
            cred = credentials.Certificate(info)
        elif cred_path.is_file():
            cred = credentials.Certificate(str(cred_path))
        else:
            return False

        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("Firebase Admin inicializado")
        return True
    except Exception as exc:
        logger.warning("Firebase Admin indisponível: %s", exc)
        return False


def verify_bearer_token(token: str) -> str | None:
    """Valida JWT Firebase e retorna UID. Sem fallback inseguro."""
    token = token.strip()
    if not token:
        return None
    if not _init_firebase():
        return None
    try:
        from firebase_admin import auth as firebase_auth

        decoded = firebase_auth.verify_id_token(token)
        uid = decoded.get("uid")
        return str(uid) if uid else None
    except Exception as exc:
        logger.debug("verify_id_token falhou: %s", exc)
        return None
