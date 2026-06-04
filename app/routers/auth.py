from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.google import GoogleAuthError, verify_google_id_token
from app.core.security import SESSION_COOKIE, create_access_token
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLoginIn(BaseModel):
    id_token: str


@router.post("/google", response_model=UserOut)
def google_login(body: GoogleLoginIn, response: Response, db: Session = Depends(get_db)) -> UserOut:
    try:
        claims = verify_google_id_token(body.id_token)
    except GoogleAuthError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {exc}") from exc

    sub = claims.get("sub")
    email = claims.get("email")
    if not sub or not email:
        raise HTTPException(status_code=401, detail="Token missing sub/email")

    user = db.query(User).filter(User.google_sub == sub).first()
    if user is None:
        user = User(google_sub=sub, email=email, name=claims.get("name"), avatar_url=claims.get("picture"))
        db.add(user)
    else:
        user.email = email
        user.name = claims.get("name")
        user.avatar_url = claims.get("picture")
    db.commit()
    db.refresh(user)

    settings = get_settings()
    token = create_access_token(subject=sub, claims={"email": email})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=settings.env != "local",
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    return UserOut.model_validate(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "logged_out"}
