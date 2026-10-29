"""Deprecated import path. Use :mod:`infra.request_context`."""

import sys

from infra import request_context as _module

sys.modules[__name__] = _module
