"""Deprecated import path. Use :mod:`infra.queue`."""

import sys

from infra import queue as _module

sys.modules[__name__] = _module
