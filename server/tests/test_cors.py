"""Tests for the CORS configuration (REVIEW.md #14).

Only the known frontend origin (FRONT_URL) may call the API with credentials.
"""

import os

FRONT_URL = os.getenv("FRONT_URL", "http://localhost:5173")


class TestCors:
    def test_frontend_origin_is_allowed(self, client):
        response = client.options(
            "/api/session/some-token",
            headers={
                "Origin": FRONT_URL,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == FRONT_URL
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_unknown_origin_is_not_allowed(self, client):
        response = client.options(
            "/api/session/some-token",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in response.headers
