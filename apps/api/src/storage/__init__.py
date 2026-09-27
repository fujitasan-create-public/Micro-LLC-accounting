"""R2 の読み書き。repositories/ と同様に、バインディングに触れるのはこのパッケージだけ。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes | None: ...

    async def exists(self, key: str) -> bool: ...

    async def list(self, prefix: str) -> list[str]: ...


class LocalStorage:
    """ローカル開発用。R2 の代わりにフォルダへ保存する。上書きは禁止（バケットロックの代替）。"""

    def __init__(self, root: str | Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self._root / key).resolve()
        if self._root.resolve() not in p.parents:
            raise ValueError("invalid key")
        return p

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        if p.exists():
            raise FileExistsError(f"object already exists: {key}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    async def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def list(self, prefix: str) -> list[str]:
        base = self._root
        return sorted(
            str(p.relative_to(base)).replace("\\", "/")
            for p in base.rglob("*")
            if p.is_file() and str(p.relative_to(base)).replace("\\", "/").startswith(prefix)
        )


class R2Storage:
    """【要検証】Pyodide からの R2 呼び出し。"""

    def __init__(self, binding: Any):
        self._bucket = binding

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        from pyodide.ffi import to_js  # type: ignore[import-not-found]
        import js  # type: ignore[import-not-found]

        if await self.exists(key):
            raise FileExistsError(f"object already exists: {key}")
        body = js.Uint8Array.new(len(data))
        body.assign(data)
        opts = to_js({"httpMetadata": {"contentType": content_type}}, dict_converter=js.Object.fromEntries)
        await self._bucket.put(key, body, opts)

    async def get(self, key: str) -> bytes | None:
        obj = await self._bucket.get(key)
        if obj is None:
            return None
        buf = await obj.arrayBuffer()
        return bytes(buf.to_py())

    async def exists(self, key: str) -> bool:
        return (await self._bucket.head(key)) is not None

    async def list(self, prefix: str) -> list[str]:
        from pyodide.ffi import to_js  # type: ignore[import-not-found]
        import js  # type: ignore[import-not-found]

        keys: list[str] = []
        cursor = None
        while True:
            opts: dict[str, Any] = {"prefix": prefix}
            if cursor:
                opts["cursor"] = cursor
            res = await self._bucket.list(to_js(opts, dict_converter=js.Object.fromEntries))
            keys.extend(o.key for o in res.objects)
            if not res.truncated:
                break
            cursor = res.cursor
        return keys
