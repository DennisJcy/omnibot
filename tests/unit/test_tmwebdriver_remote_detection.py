from unittest.mock import Mock

from omnibot.TMWebDriver import TMWebDriver


def test_remote_bridge_requires_health_endpoint(monkeypatch):
    response = Mock(ok=False, status_code=404)
    monkeypatch.setattr("omnibot.TMWebDriver.requests.get", Mock(return_value=response))

    assert TMWebDriver._is_compatible_remote_bridge("127.0.0.1", 18765) is False


def test_remote_bridge_accepts_health_endpoint(monkeypatch):
    response = Mock(ok=True, status_code=200)
    monkeypatch.setattr("omnibot.TMWebDriver.requests.get", Mock(return_value=response))

    assert TMWebDriver._is_compatible_remote_bridge("127.0.0.1", 18765) is True
