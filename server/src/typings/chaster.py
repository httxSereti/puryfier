"""Deprecated import path. Use :mod:`infra.chaster_types`."""

import sys

from infra import chaster_types as _module

sys.modules[__name__] = _module
