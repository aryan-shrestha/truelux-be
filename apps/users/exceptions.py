from apps.core.exceptions import DomainError


class InvalidRefreshToken(DomainError):
    code = "invalid_refresh_token"
    message = "The refresh token is invalid, expired or already revoked."
