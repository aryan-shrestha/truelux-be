from django.contrib.auth.base_user import AbstractBaseUser


def is_active_staff(user: AbstractBaseUser | None) -> bool:
    """SimpleJWT's USER_AUTHENTICATION_RULE: only active staff get or refresh tokens.

    SimpleJWT answers a failed rule with the same 401 as a wrong password, so the API
    never reveals that an account exists but lacks staff rights.
    """
    return bool(user is not None and user.is_active and getattr(user, "is_staff", False))
