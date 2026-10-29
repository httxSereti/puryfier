"""Tests for server-side configuration validation (REVIEW.md P1 #6)."""

import json

import pytest
from test_extensions import make_configuration_response

from schemas import ChasterExtensionConfigSchema

SESSION_ID = "config-validation-session"

VALID_CONFIG = {
    "lock_on_freeze": True,
    "unlock_on_unfreeze": True,
    "censorPicsConfig": {
        "limit_count": 5,
        "added_duration": 300,
        "enabled": True,
    },
}


class TestConfigurationValidation:
    def test_valid_config_is_sent_to_chaster_and_stored(
        self, client, seed_lock_configuration, mock_chaster_api, mongo_db
    ):
        seed_lock_configuration(session_id=SESSION_ID, link_token="token-1")
        calls = mock_chaster_api({"sessionId": SESSION_ID})

        response = client.put(
            "/api/configuration/config-token", json=VALID_CONFIG
        )

        assert response.status_code == 200
        assert len(calls) == 1
        assert json.loads(calls[0].content) == {"config": VALID_CONFIG}
        stored = mongo_db["users_lock_configurations"].find_one(
            {"session_id": SESSION_ID}
        )
        assert stored is not None
        assert stored["config"] == VALID_CONFIG

    def test_local_config_uses_validated_payload_when_chaster_omits_it(
        self, client, seed_lock_configuration, mock_chaster_api, mongo_db
    ):
        """A successful Chaster save without `config` must not cause a 500."""
        seed_lock_configuration(session_id=SESSION_ID, link_token="token-1")
        mock_chaster_api({"sessionId": SESSION_ID})

        response = client.put(
            "/api/configuration/config-token", json=VALID_CONFIG
        )

        assert response.status_code == 200
        stored = mongo_db["users_lock_configurations"].find_one(
            {"session_id": SESSION_ID}
        )
        assert stored["config"] == VALID_CONFIG

    @pytest.mark.parametrize(
        "config",
        [
            {**VALID_CONFIG, "censorPicsConfig": {"limit_count": 0}},
            {**VALID_CONFIG, "censorPicsConfig": {"limit_count": -1}},
            {**VALID_CONFIG, "censorPicsConfig": {"limit_count": 10_001}},
            {**VALID_CONFIG, "censorPicsConfig": {"added_duration": 0}},
            {**VALID_CONFIG, "censorPicsConfig": {"added_duration": -1}},
            {**VALID_CONFIG, "censorPicsConfig": {"added_duration": 604_801}},
            {**VALID_CONFIG, "censorPicsConfig": {"limit_count": "many"}},
        ],
        ids=[
            "limit-zero",
            "limit-negative",
            "limit-too-high",
            "duration-zero",
            "duration-negative",
            "duration-too-high",
            "limit-not-an-int",
        ],
    )
    def test_invalid_config_is_rejected_before_chaster(
        self, client, mock_chaster_api, config
    ):
        calls = mock_chaster_api({"sessionId": SESSION_ID})

        response = client.put("/api/configuration/config-token", json=config)

        assert response.status_code == 422
        assert calls == []

    def test_invalid_config_from_chaster_is_rejected(
        self, client, mock_chaster_api
    ):
        mock_chaster_api(
            make_configuration_response(
                role="wearer",
                session_id=SESSION_ID,
                config={"censorPicsConfig": {"limit_count": 0}},
            )
        )

        response = client.get("/api/configuration/config-token")

        assert response.status_code == 502

    def test_schema_bounds_are_exposed_to_pydantic(self):
        with pytest.raises(ValueError):
            ChasterExtensionConfigSchema(
                censorPicsConfig={"limit_count": 0, "added_duration": 1}
            )
        with pytest.raises(ValueError):
            ChasterExtensionConfigSchema(
                censorPicsConfig={"limit_count": 1, "added_duration": 604_801}
            )
