"""Tests for the message queue service (REVIEW.md #9)."""

import asyncio

from services.queue import MAX_QUEUED_PER_TOKEN, fetch_queued_messages, queue_message


def run(coro):
    return asyncio.run(coro)


class TestQueueCap:
    def test_queue_is_capped_per_token(self, client):
        """The queue must not grow unboundedly for users who never reconnect."""

        async def scenario():
            for i in range(MAX_QUEUED_PER_TOKEN + 10):
                await queue_message("tok-cap", "setState", {"n": i})

            queued = await fetch_queued_messages("tok-cap")
            assert len(queued) == MAX_QUEUED_PER_TOKEN
            # Overflow drops the OLDEST messages: the newest state survives.
            assert queued[0].payload == {"n": 10}
            assert queued[-1].payload == {"n": MAX_QUEUED_PER_TOKEN + 9}

        run(scenario())

    def test_cap_is_per_token(self, client):
        async def scenario():
            for _ in range(MAX_QUEUED_PER_TOKEN):
                await queue_message("tok-a", "setState", {})
            await queue_message("tok-b", "setState", {})

            assert len(await fetch_queued_messages("tok-a")) == MAX_QUEUED_PER_TOKEN
            assert len(await fetch_queued_messages("tok-b")) == 1

        run(scenario())


class TestFetchDoesNotDelete:
    def test_fetch_queued_messages_preserves_entries(self, client):
        """Delete-after-send: fetching alone must never lose messages."""

        async def scenario():
            await queue_message("tok-keep", "setState", {"path": "enabled", "value": True})
            first = await fetch_queued_messages("tok-keep")
            second = await fetch_queued_messages("tok-keep")
            assert len(first) == len(second) == 1

        run(scenario())

    def test_fetch_returns_insertion_order(self, client):
        async def scenario():
            await queue_message("tok-order", "enterLockPassword", {"secret": "x"})
            await queue_message("tok-order", "setState", {"path": "enabled", "value": False})

            queued = await fetch_queued_messages("tok-order")
            assert [m.msg_type for m in queued] == ["enterLockPassword", "setState"]

        run(scenario())
