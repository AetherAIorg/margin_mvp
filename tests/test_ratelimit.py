"""The token-bucket rate limiter, driven with an injected clock (no real time)."""

import pytest

from ingestion import TokenBucket


class FakeClock:
    """Deterministic monotonic clock; `sleep` advances it so `acquire` refills."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def test_burst_up_to_capacity_then_blocks():
    clk = FakeClock()
    b = TokenBucket(rate=1, capacity=3, clock=clk.now, sleep=clk.sleep)
    assert b.try_acquire() is True
    assert b.try_acquire() is True
    assert b.try_acquire() is True
    assert b.try_acquire() is False  # capacity exhausted, no time passed


def test_refill_over_time():
    clk = FakeClock()
    b = TokenBucket(rate=2, capacity=2, clock=clk.now, sleep=clk.sleep)
    assert b.try_acquire(2) is True
    assert b.try_acquire() is False
    clk.t += 1.0  # 1s at rate 2 -> 2 tokens back
    assert b.try_acquire() is True
    assert b.try_acquire() is True


def test_acquire_blocks_until_refilled_then_proceeds():
    clk = FakeClock()
    b = TokenBucket(rate=10, capacity=1, clock=clk.now, sleep=clk.sleep)
    b.acquire()          # consumes the one token immediately
    b.acquire()          # must wait; fake sleep advances the clock
    assert clk.t == pytest.approx(0.1, abs=1e-9)  # 1 token / 10 per sec


def test_acquire_more_than_capacity_raises():
    b = TokenBucket(rate=1, capacity=1)
    with pytest.raises(ValueError):
        b.acquire(2)


def test_nonpositive_rate_rejected():
    with pytest.raises(ValueError):
        TokenBucket(rate=0)
