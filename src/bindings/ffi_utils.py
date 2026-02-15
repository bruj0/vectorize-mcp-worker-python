"""Shared JS FFI utilities for Cloudflare binding wrappers.

Centralizes the Python-to-JS and JS-to-Python conversion patterns
used by all binding modules.
"""

from __future__ import annotations

from js import Object
from pyodide.ffi import JsProxy, to_js as _to_js


def to_js(obj: dict | list) -> JsProxy:
    """Convert a Python dict/list to a JS Object/Array.

    Uses Object.fromEntries for dicts so they become proper JS Objects
    (not Map), which is what Cloudflare bindings expect.
    """
    return _to_js(obj, dict_converter=Object.fromEntries)


def js_to_dict(js_obj: JsProxy) -> dict:
    """Convert a JsProxy object to a Python dict."""
    return js_obj.to_py()


def js_to_list(js_array: JsProxy) -> list:
    """Convert a JsProxy array to a Python list."""
    return js_array.to_py()
