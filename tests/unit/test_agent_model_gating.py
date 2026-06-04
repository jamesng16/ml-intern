"""Tests for paid-tier model handling in backend/routes/agent.py."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from routes import agent  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_quota_store():
    agent.user_quotas._reset_for_tests()
    yield
    agent.user_quotas._reset_for_tests()


def _paid_session(model: str = agent.DEFAULT_PAID_MODEL_ID):
    return SimpleNamespace(
        paid_counted=False,
        paid_counted_day=None,
        session=SimpleNamespace(
            config=SimpleNamespace(model_name=model),
            paid_user_billed=False,
        ),
    )


def test_paid_model_predicate_uses_router_ids_only():
    assert agent._is_paid_model(agent.DEFAULT_OPUS_MODEL_ID)
    assert agent._is_paid_model(agent.DEFAULT_GPT_MODEL_ID)
    assert not agent._is_paid_model(agent.DEFAULT_FREE_MODEL_ID)
    assert not agent._is_paid_model("unsupported/model")


def test_available_models_expose_free_and_paid_tiers():
    models = {model["id"]: model for model in agent.AVAILABLE_MODELS}

    assert len(models) == 6
    assert agent.DEFAULT_FREE_MODEL_ID in models
    assert agent.DEFAULT_OPUS_MODEL_ID in models
    assert agent.DEFAULT_GPT_MODEL_ID in models
    assert models[agent.DEFAULT_FREE_MODEL_ID]["tier"] == "free"
    assert models[agent.DEFAULT_FREE_MODEL_ID]["recommended"] is True
    assert models[agent.DEFAULT_OPUS_MODEL_ID]["tier"] == "paid"
    assert models[agent.DEFAULT_GPT_MODEL_ID]["tier"] == "paid"
    assert models[agent.DEFAULT_OPUS_MODEL_ID]["minimum_plan"] == "free"
    assert models[agent.DEFAULT_GPT_MODEL_ID]["minimum_plan"] == "free"


@pytest.mark.asyncio
async def test_default_session_model_is_plan_aware():
    free_model = await agent._model_override_for_new_session(
        None,
        None,
        {"user_id": "u1", "plan": "free"},
    )
    pro_model = await agent._model_override_for_new_session(
        None,
        None,
        {"user_id": "u2", "plan": "pro"},
    )

    assert free_model == agent.DEFAULT_FREE_MODEL_ID
    assert pro_model == agent.DEFAULT_PAID_MODEL_ID


@pytest.mark.asyncio
async def test_explicit_paid_session_allowed_for_any_authenticated_user():
    model = await agent._model_override_for_new_session(
        None,
        agent.DEFAULT_GPT_MODEL_ID,
        {"user_id": "u1", "plan": "free"},
    )

    assert model == agent.DEFAULT_GPT_MODEL_ID


@pytest.mark.asyncio
async def test_switching_to_paid_model_is_allowed_for_free_user(monkeypatch):
    updated = []

    async def fake_check_session_access(session_id, user, request=None):
        assert session_id == "s1"
        assert user["user_id"] == "u1"
        return SimpleNamespace(user_id="u1")

    async def fake_update_session_model(session_id, model_id):
        updated.append((session_id, model_id))

    monkeypatch.setattr(agent, "_check_session_access", fake_check_session_access)
    monkeypatch.setattr(
        agent.session_manager,
        "update_session_model",
        fake_update_session_model,
    )

    response = await agent.set_session_model(
        "s1",
        {"model": agent.DEFAULT_GPT_MODEL_ID},
        request=None,
        user={"user_id": "u1", "plan": "free"},
    )

    assert response == {"session_id": "s1", "model": agent.DEFAULT_GPT_MODEL_ID}
    assert updated == [("s1", agent.DEFAULT_GPT_MODEL_ID)]


@pytest.mark.asyncio
async def test_switching_to_unknown_model_id_is_rejected(monkeypatch):
    async def fake_check_session_access(session_id, user, request=None):
        return SimpleNamespace(user_id=user["user_id"])

    monkeypatch.setattr(agent, "_check_session_access", fake_check_session_access)

    with pytest.raises(HTTPException) as exc_info:
        await agent.set_session_model(
            "s1",
            {"model": "unsupported/model"},
            request=None,
            user={"user_id": "u1", "plan": "free"},
        )

    assert exc_info.value.status_code == 400
    assert "Unknown model" in exc_info.value.detail


@pytest.mark.asyncio
async def test_free_user_paid_model_is_user_billed_from_first_submit(monkeypatch):
    persisted = []

    async def fake_persist_session_snapshot(agent_session):
        persisted.append(agent_session)

    monkeypatch.setattr(
        agent.session_manager,
        "persist_session_snapshot",
        fake_persist_session_snapshot,
    )

    agent_session = _paid_session()

    await agent._enforce_paid_model_quota(
        {"user_id": "u1", "plan": "free"},
        agent_session,
    )

    assert agent_session.paid_counted is True
    assert agent_session.paid_counted_day == agent.user_quotas.current_quota_day()
    assert agent_session.session.paid_user_billed is True
    assert persisted == [agent_session]
    assert await agent.user_quotas.get_paid_used_today("u1") == 0


@pytest.mark.asyncio
async def test_paid_quota_counts_same_session_once_per_day(monkeypatch):
    async def fake_persist_session_snapshot(_agent_session):
        return None

    monkeypatch.setattr(
        agent.session_manager,
        "persist_session_snapshot",
        fake_persist_session_snapshot,
    )

    agent_session = _paid_session()

    await agent._enforce_paid_model_quota(
        {"user_id": "u1", "plan": "pro"},
        agent_session,
    )
    await agent._enforce_paid_model_quota(
        {"user_id": "u1", "plan": "pro"},
        agent_session,
    )

    assert agent_session.paid_counted is True
    assert agent_session.paid_counted_day == agent.user_quotas.current_quota_day()
    assert await agent.user_quotas.get_paid_used_today("u1") == 1


@pytest.mark.asyncio
async def test_paid_quota_counts_stale_session_again_today(monkeypatch):
    async def fake_persist_session_snapshot(_agent_session):
        return None

    monkeypatch.setattr(
        agent.session_manager,
        "persist_session_snapshot",
        fake_persist_session_snapshot,
    )

    agent_session = _paid_session()
    agent_session.paid_counted = True
    agent_session.paid_counted_day = "2000-01-01"
    agent_session.session.paid_user_billed = True

    await agent._enforce_paid_model_quota(
        {"user_id": "u1", "plan": "pro"},
        agent_session,
    )

    assert agent_session.paid_counted is True
    assert agent_session.paid_counted_day == agent.user_quotas.current_quota_day()
    assert agent_session.session.paid_user_billed is False
    assert await agent.user_quotas.get_paid_used_today("u1") == 1


@pytest.mark.asyncio
async def test_free_model_does_not_consume_paid_quota(monkeypatch):
    async def fail_if_persisted(_agent_session):
        raise AssertionError("free model should not consume paid-tier quota")

    monkeypatch.setattr(
        agent.session_manager,
        "persist_session_snapshot",
        fail_if_persisted,
    )

    agent_session = _paid_session(agent.DEFAULT_FREE_MODEL_ID)

    await agent._enforce_paid_model_quota(
        {"user_id": "u1", "plan": "free"},
        agent_session,
    )

    assert agent_session.paid_counted is False
    assert agent_session.paid_counted_day is None
    assert await agent.user_quotas.get_paid_used_today("u1") == 0


@pytest.mark.asyncio
async def test_pro_user_uses_paid_tier_quota(monkeypatch):
    async def fake_persist_session_snapshot(_agent_session):
        return None

    monkeypatch.setattr(
        agent.session_manager,
        "persist_session_snapshot",
        fake_persist_session_snapshot,
    )

    for index in range(2):
        agent_session = _paid_session()
        await agent._enforce_paid_model_quota(
            {"user_id": "pro-user", "plan": "pro"},
            agent_session,
        )
        assert agent_session.paid_counted is True
        assert agent_session.paid_counted_day == agent.user_quotas.current_quota_day()
        assert agent_session.session.paid_user_billed is False
        assert await agent.user_quotas.get_paid_used_today("pro-user") == index + 1


@pytest.mark.asyncio
async def test_pro_user_overflow_bills_user(monkeypatch):
    async def fake_persist(_agent_session):
        return None

    monkeypatch.setattr(agent.session_manager, "persist_session_snapshot", fake_persist)
    monkeypatch.setattr(agent.user_quotas, "daily_cap_for", lambda plan: 1)

    await agent._enforce_paid_model_quota(
        {"user_id": "p1", "plan": "pro"}, _paid_session()
    )
    over = _paid_session()
    await agent._enforce_paid_model_quota({"user_id": "p1", "plan": "pro"}, over)
    assert over.session.paid_user_billed is True


@pytest.mark.asyncio
async def test_restore_summary_enforces_paid_quota_before_seed(monkeypatch):
    events = []
    agent_session = _paid_session()

    class Request:
        headers = {}
        cookies = {}

    async def fake_create_session(**kwargs):
        events.append(("create", kwargs["model"]))
        return "s1"

    async def fake_check_session_access(
        session_id, user, request, preload_sandbox=True
    ):
        events.append(("check", session_id, preload_sandbox))
        return agent_session

    async def fake_enforce_quota(user, session):
        assert user["user_id"] == "u1"
        assert session is agent_session
        session.session.paid_user_billed = False
        events.append(("quota", session.session.config.model_name))

    async def fake_seed(session_id, messages):
        events.append(("seed", session_id, agent_session.session.paid_user_billed))
        return len(messages)

    monkeypatch.setattr(agent.session_manager, "create_session", fake_create_session)
    monkeypatch.setattr(agent, "_check_session_access", fake_check_session_access)
    monkeypatch.setattr(agent, "_enforce_paid_model_quota", fake_enforce_quota)
    monkeypatch.setattr(agent.session_manager, "seed_from_summary", fake_seed)

    response = await agent.restore_session_summary(
        Request(),
        {"messages": [{"role": "user", "content": "resume this"}]},
        {"user_id": "u1", "plan": "pro"},
    )

    assert response.session_id == "s1"
    assert events == [
        ("create", agent.DEFAULT_PAID_MODEL_ID),
        ("check", "s1", False),
        ("quota", agent.DEFAULT_PAID_MODEL_ID),
        ("seed", "s1", False),
    ]


@pytest.mark.asyncio
async def test_user_quota_response_uses_paid_fields(monkeypatch):
    async def fake_get_used_today(user_id):
        assert user_id == "u1"
        return 2

    monkeypatch.setattr(agent.user_quotas, "get_paid_used_today", fake_get_used_today)
    monkeypatch.setattr(agent.user_quotas, "daily_cap_for", lambda plan: 5)

    response = await agent.get_user_quota({"user_id": "u1", "plan": "pro"})

    assert response == {
        "plan": "pro",
        "paid_used_today": 2,
        "paid_daily_cap": 5,
        "paid_remaining": 3,
    }


@pytest.mark.asyncio
async def test_set_session_yolo_calls_manager_with_cap_presence(monkeypatch):
    async def fake_check_session_access(session_id, user, request=None):
        assert session_id == "s1"
        assert user["user_id"] == "u1"
        return object()

    calls = []

    async def fake_update_session_auto_approval(session_id, **kwargs):
        calls.append((session_id, kwargs))
        return {
            "enabled": kwargs["enabled"],
            "cost_cap_usd": 7.5,
            "estimated_spend_usd": 0.0,
            "remaining_usd": 7.5,
        }

    monkeypatch.setattr(agent, "_check_session_access", fake_check_session_access)
    monkeypatch.setattr(
        agent.session_manager,
        "update_session_auto_approval",
        fake_update_session_auto_approval,
    )

    response = await agent.set_session_yolo(
        "s1",
        agent.SessionYoloRequest(enabled=True, cost_cap_usd=7.5),
        {"user_id": "u1"},
    )

    assert response["enabled"] is True
    assert response["remaining_usd"] == 7.5
    assert calls == [
        (
            "s1",
            {
                "enabled": True,
                "cost_cap_usd": 7.5,
                "cap_provided": True,
            },
        )
    ]
