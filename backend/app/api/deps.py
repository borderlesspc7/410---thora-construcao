from fastapi import HTTPException, Request

from app.config import DEBUG, ENVIRONMENT
from app.infrastructure.auth.firebase_auth import verify_bearer_token


async def get_current_user_id(request: Request) -> str:
    anonymous_user_id = request.headers.get("X-Anonymous-User", "").strip()
    auth_header = request.headers.get("Authorization", "").strip()

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        uid = verify_bearer_token(token)
        if uid:
            return uid

    if anonymous_user_id:
        return anonymous_user_id

    if ENVIRONMENT == "development" or DEBUG:
        return "dev-user-local"

    raise HTTPException(status_code=401, detail="Não autenticado")
