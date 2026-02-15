"""Stub for pyodide.ffi -- provides JsProxy and to_js fakes."""

from __future__ import annotations


class JsProxy:
    """Fake JsProxy that wraps a Python value."""

    def __init__(self, val=None):
        self._val = val

    def to_py(self):
        return self._val


def to_js(obj, *, dict_converter=None):
    """Fake to_js that returns the object as-is (no real JS conversion)."""
    return obj
