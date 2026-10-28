"""Tests for Cache-Control: no-store on sensitive endpoints (REVIEW.md #15)."""

from test_extensions import make_chaster_response, make_configuration_response


class TestNoStoreSensitiveResponses:
    def test_session_response_is_not_cacheable(self, client, mock_chaster_api):
        mock_chaster_api(
            make_chaster_response(role="wearer", session_id="cache-session")
        )

        response = client.get("/api/session/main-token")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"

    def test_session_error_is_not_cacheable(self, client, mock_chaster_api):
        mock_chaster_api({"detail": "unauthorized"}, status_code=401)

        response = client.get("/api/session/main-token")

        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"

    def test_link_token_response_is_not_cacheable(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_lock_configuration(
            session_id="cache-session", link_token="cache-token"
        )
        mock_chaster_api(
            make_chaster_response(role="wearer", session_id="cache-session")
        )

        response = client.post("/api/session/main-token/link-token")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"

    def test_configuration_response_is_not_cacheable(
        self, client, mock_chaster_api
    ):
        mock_chaster_api(
            make_configuration_response(
                role="wearer",
                session_id="cache-config-session",
                config={"lock_on_freeze": True},
            )
        )

        response = client.get("/api/configuration/config-token")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"

    def test_configuration_error_is_not_cacheable(self, client, mock_chaster_api):
        mock_chaster_api({"detail": "unauthorized"}, status_code=401)

        response = client.get("/api/configuration/config-token")

        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
