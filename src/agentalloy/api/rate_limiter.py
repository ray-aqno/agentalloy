"""Rate limiting via SlowAPI for the FastAPI routers.

Sprint 1: operational hardening.

Rate limits:
- /compose endpoints: 10/second, 100/minute
- /retrieve endpoints: 20/second, 200/minute

Rate limits are keyed on the client IP address (X-Forwarded-For header
when behind a proxy, else request.client.host).

The ``limiter`` instance is registered in app.py via ``app.state.limiter``
and applied to endpoints using the ``@limiter.limit()`` decorator.
"""

from __future__ import annotations

import logging
from typing import Any

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=[])


def _rate_limit_exceeded_handler(request: Any, exc: Exception) -> None:
    """Called by SlowAPI when a rate limit is exceeded.

    The default SlowAPI behaviour returns a 429 JSON response automatically;
    this handler is only invoked for side-effects (logging).
    """
    logger.warning(
        "rate limit exceeded for %s %s (client=%s): %s",
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
        exc,
    )


limiter.error_handler = _rate_limit_exceeded_handler
