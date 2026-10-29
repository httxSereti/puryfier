"""Deprecated import path. Use :mod:`api.configuration`."""

import sys

from api import configuration as _module

sys.modules[__name__] = _module
