"""Deprecated import path. Use :mod:`infra.chaster`."""

import sys

from infra import chaster as _module

sys.modules[__name__] = _module
