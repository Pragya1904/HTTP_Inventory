from fastapi import Request

READINESS_PING_TIMEOUT_DEFAULT = 30.0


def _readiness_ping_timeout_seconds(request: Request) -> float:
    """Read readiness DB ping timeout from app.state.settings or default."""
    settings = getattr(request.app.state, "settings", None)
    if settings is not None:
        return getattr(settings, "readiness_ping_timeout_seconds", READINESS_PING_TIMEOUT_DEFAULT)
    return READINESS_PING_TIMEOUT_DEFAULT

__all__ = ["_readiness_ping_timeout_seconds"]