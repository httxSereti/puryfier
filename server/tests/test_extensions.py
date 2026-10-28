"""E2E tests for /api/session endpoints.

Regression tests for REVIEW.md critical #2: the emergency lock password was
silently dropped by the session response schema and never reached the UI.
"""

from concurrent.futures import ThreadPoolExecutor

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


def make_configuration_response(
    role: str, session_id: str, config: dict | None = None
) -> dict:
    """Shape returned by Chaster's GET /api/extensions/configurations/{token}."""
    return {
        "config": config or {},
        "role": role,
        "user": "wearer-1",
        "sessionId": session_id,
        "extensionSlug": "puryfi",
        "createdAt": "2026-01-01T00:00:00Z",
    }


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

    @pytest.mark.parametrize("role", ["wearer", "unknown", ""])
    def test_non_keyholder_never_receives_lock_password(
        self, client, seed_lock_configuration, mock_chaster_api, role
    ):
        seed_lock_configuration(session_id=self.SESSION_ID, lock_password="s3cret")
        mock_chaster_api(
            make_chaster_response(role=role, session_id=self.SESSION_ID)
        )

        response = client.get(f"/api/session/{self.SESSION_ID}")

        assert response.status_code == 200
        assert response.json()["lock_password"] is None

    def test_lock_password_null_when_unset(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_lock_configuration(session_id=self.SESSION_ID, lock_password=None)
        mock_chaster_api(make_chaster_response(role="keyholder", session_id=self.SESSION_ID))

        response = client.get(f"/api/session/{self.SESSION_ID}")

        assert response.status_code == 200
        assert response.json()["lock_password"] is None


class TestAtomicConfigurationCreation:
    """P0 #5: concurrent session/config requests must create at most one row."""

    SESSION_ID = "session-upsert"

    def test_repeated_fetch_reuses_the_same_configuration(
        self, client, seed_lock_configuration, mongo_db, mock_chaster_api
    ):
        seed_lock_configuration(
            session_id=self.SESSION_ID,
            link_token="existing-token",
            lock_password="s3cret",
        )
        seeded = mongo_db["users_lock_configurations"].find_one(
            {"session_id": self.SESSION_ID}
        )
        mock_chaster_api(
            make_chaster_response(role="wearer", session_id=self.SESSION_ID)
        )

        first = client.get("/api/session/main-token")
        second = client.get("/api/session/main-token")

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"] == str(seeded["_id"])
        assert first.json()["link_token"] == "existing-token"
        assert (
            mongo_db["users_lock_configurations"].count_documents(
                {"session_id": self.SESSION_ID}
            )
            == 1
        )

    def test_concurrent_fetches_create_exactly_one_configuration(
        self, client, mongo_db, mock_chaster_api
    ):
        mock_chaster_api(
            make_chaster_response(role="wearer", session_id=self.SESSION_ID)
        )

        with ThreadPoolExecutor(max_workers=8) as executor:
            responses = list(
                executor.map(lambda _: client.get("/api/session/main-token"), range(8))
            )

        assert all(response.status_code == 200 for response in responses)
        assert len({response.json()["id"] for response in responses}) == 1
        assert (
            mongo_db["users_lock_configurations"].count_documents(
                {"session_id": self.SESSION_ID}
            )
            == 1
        )


class TestConfigurationCreation:
    """The configuration route must create at most one row and not overwrite."""

    SESSION_ID = "session-config"

    def test_get_creates_configuration_when_missing(
        self, client, mongo_db, mock_chaster_api
    ):
        mock_chaster_api(
            make_configuration_response(
                role="wearer",
                session_id=self.SESSION_ID,
                config={"lock_on_freeze": True},
            )
        )

        response = client.get("/api/configuration/config-token")

        assert response.status_code == 200
        assert response.json()["has_session"] is True
        stored = mongo_db["users_lock_configurations"].find_one(
            {"session_id": self.SESSION_ID}
        )
        assert stored is not None
        assert stored["config"]["lock_on_freeze"] is True
        assert (
            mongo_db["users_lock_configurations"].count_documents(
                {"session_id": self.SESSION_ID}
            )
            == 1
        )

    def test_get_preserves_existing_configuration(
        self, client, seed_lock_configuration, mongo_db, mock_chaster_api
    ):
        seed_lock_configuration(
            session_id=self.SESSION_ID,
            link_token="existing-token",
        )
        mock_chaster_api(
            make_configuration_response(
                role="wearer",
                session_id=self.SESSION_ID,
                config={"lock_on_freeze": False},
            )
        )

        response = client.get("/api/configuration/config-token")

        assert response.status_code == 200
        assert response.json()["link_token"] == "existing-token"
        stored = mongo_db["users_lock_configurations"].find_one(
            {"session_id": self.SESSION_ID}
        )
        # Default seeded config is True; the upsert must not overwrite it.
        assert stored["config"]["lock_on_freeze"] is True


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


class TestTokenRedactionInErrors:
    """Error responses must never echo Chaster URLs containing tokens."""

    def test_session_error_does_not_leak_main_token(
        self, client, mock_chaster_api
    ):
        token = "super-secret-main-token"
        mock_chaster_api({"detail": "unauthorized"}, status_code=401)

        response = client.get(f"/api/session/{token}")

        assert response.status_code == 401
        assert token not in response.text

    def test_configuration_error_does_not_leak_configuration_token(
        self, client, mock_chaster_api
    ):
        token = "super-secret-config-token"
        mock_chaster_api({"detail": "unauthorized"}, status_code=401)

        response = client.get(f"/api/configuration/{token}")

        assert response.status_code == 401
        assert token not in response.text
