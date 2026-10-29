"""Deprecated import path. Use :mod:`domain.entities`."""

import sys

from domain import entities as _entities

sys.modules[__name__] = _entities
