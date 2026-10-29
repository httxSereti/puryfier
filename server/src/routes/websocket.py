"""Deprecated import path. Use :mod:`api.realtime`."""

import sys

from api import realtime as _module

sys.modules[__name__] = _module
