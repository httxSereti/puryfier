"""Deprecated import path. Use :mod:`infra.mongo`."""

import sys

from infra import mongo as _mongo

sys.modules[__name__] = _mongo
