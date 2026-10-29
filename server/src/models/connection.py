"""Deprecated import path. Use :mod:`realtime.connection`."""

import sys

from realtime import connection as _connection

sys.modules[__name__] = _connection
