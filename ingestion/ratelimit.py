"""The single global rate-limiter abstraction.

Some sources (public REST APIs) enforce a hard per-IP limit; exceeding it gets
the caller banned, not just throttled. So every connector's `fetch` routes
through ONE limiter instance, configured per source. This is the choke point:
one place decides whether a request may proceed right now.

`RateLimiter` is the pluggable seam. `TokenBucket` is the default: it refills
`rate` tokens per second up to `capacity`, and `acquire` blocks until a token is
available. The clock and sleep function are injected so tests drive time
deterministically with no real waiting, and so a distributed limiter (Redis,
etc.) can be dropped in later without touching any connector.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol


class RateLimiter(Protocol):
    """The choke point every fetch passes through."""

    def acquire(self, tokens: float = 1.0) -> None:
        """Block until `tokens` are available, then consume them."""
        ...

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Consume `tokens` and return True if available right now, else False
        without blocking."""
        ...


class TokenBucket:
    """Classic token bucket. Deterministic and testable via injected clock/sleep.

    rate     : tokens added per second.
    capacity : maximum tokens the bucket can hold (burst size).
    clock    : returns a monotonic seconds float. Injectable for tests.
    sleep    : blocking sleep(seconds). Injectable for tests.
    """

    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = rate
        self._capacity = capacity if capacity is not None else rate
        self._clock = clock
        self._sleep = sleep
        self._tokens = self._capacity
        self._last = clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def acquire(self, tokens: float = 1.0) -> None:
        if tokens > self._capacity:
            raise ValueError(
                f"cannot acquire {tokens} tokens; bucket capacity is {self._capacity}"
            )
        while not self.try_acquire(tokens):
            # Sleep exactly long enough for the shortfall to refill, then retry.
            self._refill()
            deficit = tokens - self._tokens
            self._sleep(max(deficit / self._rate, 0.0))
