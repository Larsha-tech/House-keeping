"""Rate limiting via slowapi (in-memory; for multi-instance use a Redis backend)."""
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    strategy="fixed-window",
)
