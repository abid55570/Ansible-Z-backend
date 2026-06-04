from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import get_settings

_VALID_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleAuthError(Exception):
    """Raised when a Google ID token cannot be verified."""


def verify_google_id_token(token: str) -> dict:
    """Verify a Google ID token and return its claims, or raise GoogleAuthError."""
    settings = get_settings()
    try:
        claims = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.google_client_id or None,
        )
    except Exception as exc:  # noqa: BLE001 - normalise any verification failure
        raise GoogleAuthError(str(exc)) from exc

    if claims.get("iss") not in _VALID_ISSUERS:
        raise GoogleAuthError("Invalid token issuer")
    return claims
