"""Tests for backend/premium_quotas.py."""

import asyncio
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import premium_quotas  # noqa: E402
from agent.core.session_persistence import NoopSessionStore, _reset_store_for_tests  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_store():
    premium_quotas._reset_for_tests()
    yield
    premium_quotas._reset_for_tests()


def test_daily_cap_only_applies_to_pro_plan():
    assert premium_quotas.daily_cap_for("pro") == premium_quotas.PREMIUM_PRO_DAILY
    assert premium_quotas.daily_cap_for("free") is None
    assert premium_quotas.daily_cap_for(None) is None
    assert premium_quotas.daily_cap_for("org") is None


@pytest.mark.asyncio
async def test_try_increment_and_read_back_same_day():
    assert await premium_quotas.get_premium_used_today("u1") == 0
    assert await premium_quotas.try_increment_premium("u1", 20) == 1
    assert await premium_quotas.try_increment_premium("u1", 20) == 2
    assert await premium_quotas.get_premium_used_today("u1") == 2


@pytest.mark.asyncio
async def test_independent_users_do_not_share_counts():
    await premium_quotas.try_increment_premium("alice", 20)
    await premium_quotas.try_increment_premium("alice", 20)
    await premium_quotas.try_increment_premium("bob", 20)
    assert await premium_quotas.get_premium_used_today("alice") == 2
    assert await premium_quotas.get_premium_used_today("bob") == 1


@pytest.mark.asyncio
async def test_stale_day_resets_before_next_read():
    await premium_quotas.try_increment_premium("u1", 20)
    premium_quotas._premium_counts["u1"] = ("2000-01-01", 99)
    assert await premium_quotas.get_premium_used_today("u1") == 0
    assert await premium_quotas.try_increment_premium("u1", 20) == 1


@pytest.mark.asyncio
async def test_concurrent_increments_under_lock_do_not_lose_writes():
    await asyncio.gather(
        *[premium_quotas.try_increment_premium("race", 100) for _ in range(50)]
    )
    assert await premium_quotas.get_premium_used_today("race") == 50


@pytest.mark.asyncio
async def test_try_increment_returns_none_at_cap():
    assert await premium_quotas.try_increment_premium("pro-user", 1) == 1
    assert await premium_quotas.try_increment_premium("pro-user", 1) is None
    assert await premium_quotas.get_premium_used_today("pro-user") == 1


@pytest.mark.asyncio
async def test_try_increment_rejects_zero_cap():
    assert await premium_quotas.try_increment_premium("u1", 0) is None
    assert await premium_quotas.get_premium_used_today("u1") == 0


@pytest.mark.asyncio
async def test_try_increment_delegates_cap_to_enabled_store():
    class StoreAtCap(NoopSessionStore):
        enabled = True

        async def try_increment_premium_quota(self, user_id: str, day: str, cap: int):
            assert user_id == "mongo-user"
            assert cap == 1
            return None

        async def get_premium_quota(self, user_id: str, day: str):
            return 1

    _reset_store_for_tests(StoreAtCap())

    assert await premium_quotas.try_increment_premium("mongo-user", 1) is None
    assert await premium_quotas.get_premium_used_today("mongo-user") == 1
    assert "mongo-user" not in premium_quotas._premium_counts
