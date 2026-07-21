"""E2E tests for /api/session endpoints.

Regression tests for REVIEW.md critical #2: the emergency lock password was
silently dropped by the session response schema and never reached the UI.
"""

import pytest


def make_chaster_response(role: str, session_id: str, lock_id: str = "lock-1") -> dict:
    """Shape returned by Chaster's GET /api/extensions/auth/sessions/{token}."""
    return {
        "role": role,
        "session": {
            "sessionId": session_id,
            "lock": {
                "_id": lock_id,
                "keyholder": {"_id": "keyholder-1"},
                "user": {"_id": "wearer-1"},
            },
            "config": {},
        },
    }


class FakeChasterApiResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture()
def mock_chaster_api(monkeypatch):
    """Stub the Chaster Auth API called via `requests` in routes.extensions."""
    import routes.extensions as extensions_module

    def _mock(payload: dict):
        def fake_get(*args, **kwargs):
            return FakeChasterApiResponse(payload)

        # requests is imported at module level in routes.extensions
        monkeypatch.setattr(extensions_module.requests, "get", fake_get)

    return _mock


class TestFetchSessionLockPassword:
    SESSION_ID = "session-1"

    def test_keyholder_receives_cleartext_lock_password(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        """Round-trip: lock_password must survive schema serialization."""
        seed_lock_configuration(session_id=self.SESSION_ID, lock_password="s3cret")
        mock_chaster_api(make_chaster_response(role="keyholder", session_id=self.SESSION_ID))

        response = client.get(f"/api/session/{self.SESSION_ID}")

        assert response.status_code == 200
        body = response.json()
        assert body["lock_password"] == "s3cret"
        assert body["role"] == "keyholder"

    def test_wearer_receives_hidden_lock_password(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_lock_configuration(session_id=self.SESSION_ID, lock_password="s3cret")
        mock_chaster_api(make_chaster_response(role="wearer", session_id=self.SESSION_ID))

        response = client.get(f"/api/session/{self.SESSION_ID}")

        assert response.status_code == 200
        assert response.json()["lock_password"] == "HIDDEN"

    def test_lock_password_null_when_unset(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_lock_configuration(session_id=self.SESSION_ID, lock_password=None)
        mock_chaster_api(make_chaster_response(role="keyholder", session_id=self.SESSION_ID))

        response = client.get(f"/api/session/{self.SESSION_ID}")

        assert response.status_code == 200
        assert response.json()["lock_password"] is None


class TestCreateLinkToken:
    def test_response_does_not_leak_cleartext_password(
        self, client, seed_lock_configuration
    ):
        """The link-token endpoint cannot role-gate, so it must never return
        the cleartext password (the wearer flow calls it)."""
        seeded = seed_lock_configuration(lock_password="s3cret")

        response = client.post(f"/api/session/{seeded['_id']}/link-token")

        assert response.status_code == 200
        body = response.json()
        assert body["link_token"]  # generated
        assert body["lock_password"] is None

    def test_unknown_session_returns_404(self, client):
        response = client.post("/api/session/000000000000000000000000/link-token")
        assert response.status_code == 404
