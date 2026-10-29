"""Deprecated import path. Use :mod:`realtime.watchers`."""

import sys

from realtime import watchers as _watchers

sys.modules[__name__] = _watchers
