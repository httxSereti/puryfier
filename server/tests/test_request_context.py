import logging

from utils.request_context import REQUEST_ID_HEADER


def _http_request_fields(caplog) -> dict:
    for record in reversed(caplog.records):
        if isinstance(record.msg, dict) and record.msg.get("event") == "http.request":
            return record.msg
    raise AssertionError("http.request log not found")


def test_request_id_is_generated(client):
    response = client.get("/api/unknown")
    assert response.status_code == 404

    request_id = response.headers[REQUEST_ID_HEADER]
    assert len(request_id) == 12


def test_incoming_request_id_is_reused(client):
    response = client.get(
        "/api/unknown",
        headers={REQUEST_ID_HEADER: "support-ticket-42"},
    )
    assert response.headers[REQUEST_ID_HEADER] == "support-ticket-42"


def test_invalid_request_id_is_replaced(client):
    response = client.get(
        "/api/unknown",
        headers={REQUEST_ID_HEADER: "not valid, header injection"},
    )
    assert response.headers[REQUEST_ID_HEADER] != "not valid, header injection"
    assert len(response.headers[REQUEST_ID_HEADER]) == 12


def test_token_paths_are_redacted_in_logs(client, caplog):
    with caplog.at_level(logging.INFO, logger="utils.request_context"):
        client.get("/api/session/super-secret-token/unknown")

    fields = _http_request_fields(caplog)
    assert "super-secret-token" not in str(fields)
    assert fields["path"].startswith("/api/session/<token:")
