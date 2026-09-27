"""Cloudflare Python Workers のエントリポイント。

ASGI への橋渡しは Workers ランタイム同梱の asgi モジュールで行い、
FastAPI 側では request.scope["env"] から D1・R2 のバインディングを取り出す（common.get_db など）。
wrangler dev（workerd）で fetch・scheduled の両方を動作確認済み。
"""

from workers import WorkerEntrypoint  # type: ignore[import-not-found]

from app_factory import create_app

app = create_app()


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi  # type: ignore[import-not-found]

        return await asgi.fetch(app, request.js_object, self.env)

    async def scheduled(self, controller, env=None, ctx=None):
        """毎日の定期実行: 計上日が来た定型仕訳（家賃の引落しなど）を自動で計上する。"""
        from common import today
        from db import D1Database
        from services.recurring import auto_post

        await auto_post(D1Database((env or self.env).DB), today())
