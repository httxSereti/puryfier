"""Deprecated import path. Use :mod:`api.session`."""

import sys

from api import session as _module

sys.modules[__name__] = _module
