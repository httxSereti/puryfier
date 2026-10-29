"""Deprecated import path. Use :mod:`workers.handlers`.

This compatibility module forwards attribute reads *and writes* to
``workers.handlers`` so existing tests that monkeypatch a handler keep working
while the worker imports the canonical module.
"""

import sys
import types
from pathlib import Path

from workers import handlers as _handlers


class _CompatModule(types.ModuleType):
    def __getattr__(self, name: str):
        return getattr(_handlers, name)

    def __setattr__(self, name: str, value) -> None:
        if name.startswith("__") and name.endswith("__"):
            super().__setattr__(name, value)
        else:
            setattr(_handlers, name, value)


_module = _CompatModule(__name__, __doc__)
_module.__path__ = [str(Path(__file__).parent)]
sys.modules[__name__] = _module
