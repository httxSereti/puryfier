"""Liveness endpoint tests."""

import pytest


@pytest.mark.parametrize("path", ["/health", "/healthz"])
def test_health_endpoint_reports_ok(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
