import pytest

from api.models import NotificationChannel, NotificationConfig
from api.notifications import get_manager, reset_manager_for_tests
from api.state_store import LocalFileStateStore, reset_state_store_for_tests


@pytest.fixture
def clean_notifications(tmp_path, monkeypatch):
    reset_state_store_for_tests()
    reset_manager_for_tests()
    store = LocalFileStateStore(tmp_path / "state.json")
    monkeypatch.setattr("api.notifications.get_state_store", lambda: store)
    manager = get_manager()
    manager._store = store
    manager.put_config(NotificationConfig())
    yield manager
    reset_manager_for_tests()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_disabled_by_default(clean_notifications):
    result = await clean_notifications.send("title", "body")
    assert result["sent"] is False
    assert result["reason"] == "disabled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_no_enabled_channels(clean_notifications):
    clean_notifications.put_config(
        NotificationConfig(
            enabled=True,
            channels=[NotificationChannel(id="c1", type="webhook", name="x", enabled=False)],
        )
    )
    result = await clean_notifications.send("title", "body")
    assert result["sent"] is False
    assert result["reason"] == "no_enabled_channels"


@pytest.mark.unit
def test_status_reflects_enabled_channel(clean_notifications):
    clean_notifications.put_config(
        NotificationConfig(
            enabled=True,
            channels=[NotificationChannel(id="c1", type="webhook", name="x", enabled=True)],
        )
    )
    status = clean_notifications.status()
    assert status.enabled is True
    assert status.channel_count == 1
    assert status.channel_types == ["webhook"]


@pytest.mark.unit
def test_config_persists_to_state_store(clean_notifications, tmp_path):
    clean_notifications.put_config(
        NotificationConfig(
            enabled=True,
            channels=[
                NotificationChannel(
                    id="c1",
                    type="telegram",
                    name="tg",
                    enabled=True,
                    config={"bot_token": "x", "chat_id": "123"},
                )
            ],
        )
    )
    # Fresh manager against same store should reload config.
    reset_manager_for_tests()
    store = LocalFileStateStore(tmp_path / "state.json")
    fresh = get_manager()
    fresh._store = store
    cfg = fresh.get_config()
    assert cfg.enabled is True
    assert len(cfg.channels) == 1
    assert cfg.channels[0].type == "telegram"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dedupe_blocks_repeat_messages(clean_notifications):
    clean_notifications.put_config(
        NotificationConfig(
            enabled=True,
            dedupe_minutes=5,
            channels=[NotificationChannel(id="c1", type="webhook", name="x", enabled=True)],
        )
    )
    await clean_notifications.send("title", "body")
    result = await clean_notifications.send("title", "body")
    assert result["sent"] is False
    assert result["reason"] == "deduped"
