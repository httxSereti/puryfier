"""E2E tests for /api/session endpoints.

Regression tests for REVIEW.md critical #2: the emergency lock password was
silently dropped by the session response schema and never reached the UI.
"""

import httpx
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


@pytest.fixture()
def mock_chaster_api(monkeypatch):
    """Swap the shared Chaster httpx client for a MockTransport one returning
    the given payload, and capture the requests made to it."""
    import utils.chaster_api as chaster_api_module

    def _mock(payload: dict, status_code: int = 200) -> list[httpx.Request]:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(status_code, json=payload)

        mock_client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url=chaster_api_module.CHASTER_BASE_URL,
        )
        monkeypatch.setattr(chaster_api_module, "chaster_client", mock_client)
        return calls

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


class TestFetchSessionLinkToken:
    """REVIEW.md #8: only the wearer may see the link token — whoever holds
    it owns the Puryfi connection slot."""

    SESSION_ID = "session-1"

    def test_wearer_receives_link_token(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_lock_configuration(session_id=self.SESSION_ID, link_token="token-1")
        mock_chaster_api(make_chaster_response(role="wearer", session_id=self.SESSION_ID))

        response = client.get(f"/api/session/{self.SESSION_ID}")

        assert response.status_code == 200
        assert response.json()["link_token"] == "token-1"

    def test_keyholder_does_not_receive_link_token(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_lock_configuration(session_id=self.SESSION_ID, link_token="token-1")
        mock_chaster_api(make_chaster_response(role="keyholder", session_id=self.SESSION_ID))

        response = client.get(f"/api/session/{self.SESSION_ID}")

        assert response.status_code == 200
        assert response.json()["link_token"] is None


class TestCreateLinkToken:
    SESSION_ID = "session-1"

    def test_wearer_can_create_and_reuse_token(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seeded = seed_lock_configuration(
            session_id=self.SESSION_ID, link_token=None, lock_password="s3cret"
        )
        mock_chaster_api(make_chaster_response(role="wearer", session_id=self.SESSION_ID))

        created = client.post("/api/session/some-main-token/link-token")

        assert created.status_code == 200
        body = created.json()
        assert body["link_token"]  # generated
        assert body["lock_password"] is None  # never cleartext to the wearer flow

        # A second call returns the same token instead of regenerating it.
        reused = client.post("/api/session/some-main-token/link-token")
        assert reused.status_code == 200
        assert reused.json()["link_token"] == body["link_token"]

        assert seeded["_id"]  # sanity: document existed before the call

    def test_keyholder_is_forbidden(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_lock_configuration(session_id=self.SESSION_ID, link_token=None)
        mock_chaster_api(make_chaster_response(role="keyholder", session_id=self.SESSION_ID))

        response = client.post("/api/session/some-main-token/link-token")

        assert response.status_code == 403

    def test_unknown_session_returns_404(
        self, client, mock_chaster_api
    ):
        mock_chaster_api(make_chaster_response(role="wearer", session_id="no-such-session"))

        response = client.post("/api/session/some-main-token/link-token")

        assert response.status_code == 404

    def test_invalid_main_token_propagates_upstream_status(
        self, client, mock_chaster_api
    ):
        mock_chaster_api({"detail": "unauthorized"}, status_code=401)

        response = client.post("/api/session/bad-token/link-token")

        assert response.status_code == 401
