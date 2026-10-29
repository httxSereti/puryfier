"""Deprecated import path. Use :mod:`infra.logging`."""

import sys

from infra import logging as _logging

sys.modules[__name__] = _logging
