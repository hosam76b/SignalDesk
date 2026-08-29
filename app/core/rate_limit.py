"""Rate limiting setup for brute-force protection on auth endpoints."""

import sys

from slowapi import Limiter
from slowapi.util import get_remote_address

from config import settings

# Disabled under pytest so test suites can exercise auth endpoints repeatedly.
limiter = Limiter(key_func=get_remote_address, enabled="pytest" not in sys.modules)
AUTH_RATE_LIMIT = settings.rate_limit_auth
