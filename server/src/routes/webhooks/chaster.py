"""Deprecated import path. Use :mod:`api.webhooks`."""

import sys

from api import webhooks as _module

sys.modules[__name__] = _module
