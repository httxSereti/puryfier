"""Deprecated import path. Use :mod:`infra.documents.user_lock_configuration`."""

import sys

from infra.documents import user_lock_configuration as _module

sys.modules[__name__] = _module
