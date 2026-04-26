"""JavaScript ↔ Python interop helpers for Pyodide on Cloudflare Workers."""

from js import Object
from pyodide.ffi import to_js


def js_to_py(value):
    if hasattr(value, "to_py"):
        return value.to_py()
    return value


def to_js_obj(value):
    """Convert a Python dict/list to a JS object using ``Object.fromEntries``."""
    return to_js(value, dict_converter=Object.fromEntries)
