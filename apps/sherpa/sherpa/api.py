"""Sherpa's small HTTP API, for YETI. Same abilities as the Discord commands: search,
request, read. There is no endpoint that deletes or changes settings.

Every call except /health needs  Authorization: Bearer $SHERPA_API_TOKEN.
"""
from __future__ import annotations

import hmac
import logging
import time
from dataclasses import asdict
from typing import Any

from aiohttp import web

from .models import Kind, RequestError, Requester, Result
from .service import Sherpa

log = logging.getLogger(__name__)
CACHE_SECONDS = 1800


def result_json(r: Result) -> dict[str, Any]:
    d = asdict(r)
    d.pop("raw", None)
    d["kind"] = r.kind.value
    d["display"] = r.display
    return d


def row_json(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


class Api:
    def __init__(self, sherpa: Sherpa, token: str, owner_discord_id: int | None = None):
        self.sherpa, self.token, self.owner = sherpa, token, owner_discord_id
        self._cache: dict[tuple[str, str], tuple[float, Result]] = {}

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self.auth, self.errors])
        app.add_routes([
            web.get("/health", self.health),
            web.get("/v1/search", self.search),
            web.post("/v1/request", self.request),
            web.get("/v1/requests", self.requests),
            web.get("/v1/downloads", self.downloads),
            web.get("/v1/space", self.space),
        ])
        return app

    @web.middleware
    async def auth(self, request: web.Request, handler):
        if request.path == "/health":
            return await handler(request)
        given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not self.token or not hmac.compare_digest(given.encode(), self.token.encode()):
            return web.json_response({"error": "unauthorised"}, status=401)
        return await handler(request)

    @web.middleware
    async def errors(self, request: web.Request, handler):
        try:
            return await handler(request)
        except RequestError as e:
            return web.json_response({"error": str(e)}, status=422)
        except (KeyError, ValueError) as e:
            return web.json_response({"error": f"bad request: {e}"}, status=400)

    def _remember(self, results: list[Result]) -> None:
        cutoff = time.monotonic() - CACHE_SECONDS
        self._cache = {k: v for k, v in self._cache.items() if v[0] > cutoff}
        for r in results:
            self._cache[(r.kind.value, r.ref)] = (time.monotonic(), r)

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def search(self, request: web.Request) -> web.Response:
        kind = Kind(request.query["kind"])
        results = await self.sherpa.search(kind, request.query["q"])
        self._remember(results)
        return web.json_response({"results": [result_json(r) for r in results]})

    async def request(self, request: web.Request) -> web.Response:
        """Body: {"kind": "movie", "ref": "<from search>", "query": "<optional, to search again>",
                  "format": "ebook|audiobook", "for": {"discord_id": 123, "name": "Sam"}}
        Without "for", the request is Arnav's (made through YETI)."""
        body = await request.json()
        kind = Kind(body["kind"])
        ref = str(body["ref"])
        hit = self._cache.get((kind.value, ref))
        result = hit[1] if hit else None
        if result is None and body.get("query"):
            found = await self.sherpa.search(kind, body["query"])
            self._remember(found)
            result = next((r for r in found if r.ref == ref), None)
        if result is None:
            raise RequestError("Search first, then request one of the results (or pass the same query again).")
        target = body.get("for") or {}
        who = Requester(discord_id=int(target["discord_id"]) if target.get("discord_id") else self.owner,
                        name=target.get("name") or "Arnav", source="yeti")
        row = await self.sherpa.request(kind, result, who, body.get("format") or "ebook")
        return web.json_response({"request": row_json(row)}, status=201)

    async def requests(self, request: web.Request) -> web.Response:
        if request.query.get("discord_id"):
            rows = await self.sherpa.mine(int(request.query["discord_id"]))
        else:
            rows = [dict(r) for r in await self.sherpa.db.recent(int(request.query.get("limit", 25)))]
        return web.json_response({"requests": [row_json(r) for r in rows]})

    async def downloads(self, request: web.Request) -> web.Response:
        return web.json_response({"downloads": await self.sherpa.downloads()})

    async def space(self, request: web.Request) -> web.Response:
        sp = await self.sherpa.space()
        return web.json_response({
            "total_bytes": sp.total, "used_bytes": sp.used, "free_bytes": sp.free,
            "people": [row_json(p) for p in sp.people],
            "delete_first": [row_json(c) for c in sp.candidates],
        })


async def start_api(sherpa: Sherpa, token: str, port: int, owner: int | None) -> web.AppRunner | None:
    if not token:
        log.warning("SHERPA_API_TOKEN is empty: the YETI API is switched off")
        return None
    runner = web.AppRunner(Api(sherpa, token, owner).app(), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("YETI API listening on :%s", port)
    return runner
