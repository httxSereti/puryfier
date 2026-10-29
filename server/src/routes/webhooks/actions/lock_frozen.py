"""Deprecated import path. Use :mod:`workers.handlers`."""

import sys

from workers import handlers as _handlers

sys.modules[__name__] = _handlers
