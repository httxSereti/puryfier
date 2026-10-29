"""Deprecated import path. Use :mod:`domain.events`."""

import sys

from domain import events as _module

sys.modules[__name__] = _module
