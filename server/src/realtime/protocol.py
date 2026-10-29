"""Puryfi WebSocket protocol constants and msgpack codec."""

from typing import Any

import msgpack

manifest = {
    "name": "Puryfier",
    "version": "0.3.0",
    "description": "Link Chaster with Puryfi",
    "author": "Sereti",
    "website": "https://paa.ge/sereti",
}

intents = [
    "readUserState",  # read username
    "writeLockConfigurationState",  # lock puryfi
    "writeEnabledState",  # enable/disable puryfi
    "readMediaProcesses",  # read media processes
]


def encode(message: dict[str, Any]) -> bytes:
    packed = msgpack.packb(message)
    if not isinstance(packed, bytes):
        raise TypeError("msgpack returned a non-bytes payload")
    return packed


def decode(data: bytes) -> dict[str, Any]:
    return msgpack.unpackb(data)
