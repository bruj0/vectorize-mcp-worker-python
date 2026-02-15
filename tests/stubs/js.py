"""Stub for the js module (Pyodide's JavaScript bridge).

Provides minimal fakes for ``js.Object``, ``js.Response``, ``js.Request``
so that binding modules can be imported in tests.
"""

from __future__ import annotations


class _ObjectStub:
    @staticmethod
    def fromEntries(entries):
        return dict(entries) if entries else {}


Object = _ObjectStub()


class Request:
    """Stub for js.Request used by multimodal binding."""

    @classmethod
    def new(cls, url, init=None):
        inst = cls()
        inst.url = url
        inst._init = init
        return inst


class Response:
    """Stub for js.Response used by multipart parser."""

    @classmethod
    def new(cls, body):
        inst = cls()
        inst.body = body
        return inst

    async def arrayBuffer(self):
        return self.body
