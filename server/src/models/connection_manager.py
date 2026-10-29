"""Deprecated import path. Use :mod:`realtime.registry`."""

import sys

from realtime import registry as _registry

sys.modules[__name__] = _registry
