"""Deprecated import path. Use :mod:`infra.documents.queued_message`."""

import sys

from infra.documents import queued_message as _module

sys.modules[__name__] = _module
