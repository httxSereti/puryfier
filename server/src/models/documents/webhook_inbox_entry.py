"""Deprecated import path. Use :mod:`infra.documents.webhook_inbox_entry`."""

import sys

from infra.documents import webhook_inbox_entry as _module

sys.modules[__name__] = _module
