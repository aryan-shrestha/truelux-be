from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.logging import get_logger
from apps.users.exceptions import InvalidRefreshToken
from apps.users.models import User

logger = get_logger(__name__)


def revoke_refresh_token(*, user: User, refresh: str) -> None:
    """Raises InvalidRefreshToken for a malformed, expired, already revoked or
    someone else's refresh token."""
    try:
        token = RefreshToken(refresh)  # type: ignore[arg-type]  # stubs want Token | None
    except TokenError as exc:
        raise InvalidRefreshToken() from exc

    if str(token.payload.get(api_settings.USER_ID_CLAIM)) != str(user.pk):
        raise InvalidRefreshToken()

    token.blacklist()
    logger.info("auth.logged_out", user_id=str(user.pk))
