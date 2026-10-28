"""Regression tests for the Beanie index declarations (REVIEW.md critical #4).

`Annotated[str, Indexed(...)] | None` puts the annotation inside the Optional
and Beanie silently creates no index. Indexes must be declared in
`Settings.indexes`.
"""

import pytest
from pymongo.errors import DuplicateKeyError

from models.documents.user_lock_configuration import UserLockConfiguration


class TestUserLockConfigurationIndexes:
    def test_indexes_are_created_at_startup(self, client, mongo_db):
        indexes = mongo_db["users_lock_configurations"].index_information()

        assert indexes["session_id_1"]["unique"] is True
        assert dict(indexes["lock_id_1"]["key"]) == {"lock_id": 1}
        assert "unique" not in indexes["lock_id_1"]
        assert indexes["link_token_1"]["unique"] is True

    def test_link_token_index_is_partial_on_strings(self):
        """A partial index permits many configurations without a link token."""
        declared = {
            index.document["name"]: index.document
            for index in UserLockConfiguration.Settings.indexes
        }

        assert declared["link_token_1"]["partialFilterExpression"] == {
            "link_token": {"$type": "string"}
        }
        # mongomock does not implement partialFilterExpression, so the
        # declaration above is the meaningful assertion in tests.

    def test_session_id_is_unique(self, client, seed_lock_configuration):
        seed_lock_configuration(session_id="session-1", link_token="token-1")

        with pytest.raises(DuplicateKeyError):
            seed_lock_configuration(session_id="session-1", link_token="token-2")

    def test_link_token_is_unique_when_set(self, client, seed_lock_configuration):
        seed_lock_configuration(session_id="session-1", link_token="token-1")

        with pytest.raises(DuplicateKeyError):
            seed_lock_configuration(session_id="session-2", link_token="token-1")

    def test_lock_id_is_not_unique(
        self, client, seed_lock_configuration, mongo_db
    ):
        seed_lock_configuration(
            session_id="session-1", link_token="token-1", lock_id="lock-1"
        )
        seed_lock_configuration(
            session_id="session-2", link_token="token-2", lock_id="lock-1"
        )

        assert mongo_db["users_lock_configurations"].count_documents({}) == 2
