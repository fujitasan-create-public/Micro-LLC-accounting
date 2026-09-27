"""Cloudflare Python Workers のエントリポイント。

ASGI への橋渡しは Workers ランタイム同梱の asgi モジュールで行い、
FastAPI 側では request.scope["env"] から D1・R2 のバインディングを取り出す（common.get_db など）。
【要検証】ランタイムのバージョンにより asgi のエントリポイントの書き方が異なる。
"""

from workers import WorkerEntrypoint  # type: ignore[import-not-found]

from app_factory import create_app

app = create_app()


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi  # type: ignore[import-not-found]

        return await asgi.fetch(app, request.js_object, self.env)
