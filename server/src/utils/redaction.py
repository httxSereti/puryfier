"""Deprecated import path. Use :mod:`infra.redaction`."""

import sys

from infra import redaction as _module

sys.modules[__name__] = _module
