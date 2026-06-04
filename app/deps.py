from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import SESSION_COOKIE, decode_access_token
from app.db import get_db
from app.models import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
    except Exception as exc:  # noqa: BLE001 - any decode failure is an auth failure
        raise HTTPException(status_code=401, detail="Invalid session") from exc

    user = db.query(User).filter(User.google_sub == payload.get("sub")).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user
