"""Daily quota for Pro-only premium model sessions.

Tracks per-user premium model session starts against a daily Pro cap. MongoDB
is the source of truth when configured; the in-process dict remains the
fallback for local/dev/test runs.

Unit: first Pro-only premium model submit in a session, not raw messages.
Default/free model traffic is uncapped.
"""

import asyncio
import os
from datetime import UTC, datetime

from agent.core.session_persistence import (
    NoopSessionStore,
    get_session_store,
    _reset_store_for_tests,
)

PREMIUM_PRO_DAILY: int = int(os.environ.get("PREMIUM_PRO_DAILY", "20"))

# user_id -> (day_utc_iso, count_for_that_day)
_premium_counts: dict[str, tuple[str, int]] = {}
_lock = asyncio.Lock()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def daily_cap_for(plan: str | None) -> int | None:
    """Return the daily Pro-only premium session cap for the given plan."""
    return PREMIUM_PRO_DAILY if plan == "pro" else None


async def get_premium_used_today(user_id: str) -> int:
    """Return today's premium session count for the user."""
    store = get_session_store()
    if getattr(store, "enabled", False):
        db_count = await store.get_premium_quota(user_id, _today())
        return db_count or 0

    async with _lock:
        entry = _premium_counts.get(user_id)
        if entry is None:
            return 0
        day, count = entry
        if day != _today():
            _premium_counts.pop(user_id, None)
            return 0
        return count


async def try_increment_premium(user_id: str, cap: int) -> int | None:
    """Atomically bump today's count if below *cap*.

    Returns the new count, or ``None`` when the user is already at the cap.
    """
    if cap <= 0:
        return None

    store = get_session_store()
    if getattr(store, "enabled", False):
        return await store.try_increment_premium_quota(user_id, _today(), cap)

    async with _lock:
        today = _today()
        day, count = _premium_counts.get(user_id, (today, 0))
        if day != today:
            count = 0
        if count >= cap:
            return None
        count += 1
        _premium_counts[user_id] = (today, count)
        return count


def _reset_for_tests() -> None:
    """Test-only: clear the in-memory store."""
    _premium_counts.clear()
    _reset_store_for_tests(NoopSessionStore())
