"""Who asked for what. One row per item, kept until the item is gone from the library.

The first person to request an item owns it (unique app + app_ref). That is what
/space uses to suggest other people's items before the owner's when space runs low.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncpg

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    discord_id     BIGINT PRIMARY KEY,
    name           TEXT NOT NULL,
    seerr_user_id  INTEGER UNIQUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS requests (
    id                 BIGSERIAL PRIMARY KEY,
    kind               TEXT NOT NULL,
    title              TEXT NOT NULL,
    year               INTEGER,
    app                TEXT NOT NULL,
    app_ref            TEXT NOT NULL,
    details            JSONB NOT NULL DEFAULT '{}'::jsonb,
    requested_by       BIGINT REFERENCES members(discord_id) ON DELETE SET NULL,
    requested_by_name  TEXT NOT NULL,
    source             TEXT NOT NULL DEFAULT 'discord',
    status             TEXT NOT NULL DEFAULT 'requested',
    size_bytes         BIGINT NOT NULL DEFAULT 0,
    requested_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    available_at       TIMESTAMPTZ,
    announced_at       TIMESTAMPTZ,
    deleted_at         TIMESTAMPTZ,
    last_checked_at    TIMESTAMPTZ,
    UNIQUE (app, app_ref)
);
CREATE INDEX IF NOT EXISTS requests_open ON requests (status) WHERE status <> 'deleted';
CREATE INDEX IF NOT EXISTS requests_by ON requests (requested_by);
"""


class Store:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "Store":
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5,
                                         init=lambda c: c.set_type_codec(
                                             "jsonb", encoder=_json_dumps, decoder=_json_loads, schema="pg_catalog"))
        async with pool.acquire() as c:
            await c.execute(SCHEMA)
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    # ------------------------------------------------------------------ members
    async def upsert_member(self, discord_id: int, name: str) -> None:
        await self.pool.execute(
            "INSERT INTO members (discord_id, name) VALUES ($1, $2) "
            "ON CONFLICT (discord_id) DO UPDATE SET name = EXCLUDED.name", discord_id, name)

    async def link_seerr(self, discord_id: int, name: str, seerr_user_id: int) -> None:
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("UPDATE members SET seerr_user_id = NULL WHERE seerr_user_id = $1 AND discord_id <> $2",
                            seerr_user_id, discord_id)
            await c.execute(
                "INSERT INTO members (discord_id, name, seerr_user_id) VALUES ($1, $2, $3) "
                "ON CONFLICT (discord_id) DO UPDATE SET name = EXCLUDED.name, seerr_user_id = EXCLUDED.seerr_user_id",
                discord_id, name, seerr_user_id)

    async def member(self, discord_id: int) -> asyncpg.Record | None:
        return await self.pool.fetchrow("SELECT * FROM members WHERE discord_id = $1", discord_id)

    async def member_by_seerr(self, seerr_user_id: int) -> asyncpg.Record | None:
        return await self.pool.fetchrow("SELECT * FROM members WHERE seerr_user_id = $1", seerr_user_id)

    # ------------------------------------------------------------------ requests
    async def add_request(self, *, kind: str, title: str, year: int | None, app: str, app_ref: str,
                          requested_by: int | None, requested_by_name: str, source: str,
                          details: dict[str, Any] | None = None, status: str = "requested",
                          requested_at: datetime | None = None) -> tuple[asyncpg.Record, bool]:
        """Record a request. Returns (row, created). If the item is already tracked the
        original requester keeps it, unless it had been deleted: then the new requester
        takes it over, as it is a fresh download."""
        row = await self.pool.fetchrow(
            """
            INSERT INTO requests (kind, title, year, app, app_ref, details, requested_by, requested_by_name,
                                  source, status, requested_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, COALESCE($11, now()))
            ON CONFLICT (app, app_ref) DO UPDATE SET
                requested_by = EXCLUDED.requested_by, requested_by_name = EXCLUDED.requested_by_name,
                source = EXCLUDED.source, status = EXCLUDED.status, requested_at = EXCLUDED.requested_at,
                details = EXCLUDED.details, available_at = NULL, announced_at = NULL, deleted_at = NULL,
                size_bytes = 0
            WHERE requests.status = 'deleted'
            RETURNING *
            """,
            kind, title, year, app, app_ref, details or {}, requested_by, requested_by_name, source, status,
            requested_at)
        if row is not None:
            return row, True
        existing = await self.pool.fetchrow("SELECT * FROM requests WHERE app = $1 AND app_ref = $2",
                                            app, app_ref)
        return existing, False

    async def get(self, app: str, app_ref: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow("SELECT * FROM requests WHERE app = $1 AND app_ref = $2", app, app_ref)

    async def open_requests(self) -> list[asyncpg.Record]:
        return await self.pool.fetch("SELECT * FROM requests WHERE status <> 'deleted' ORDER BY requested_at")

    async def update(self, request_id: int, **fields: Any) -> None:
        allowed = {"status", "size_bytes", "available_at", "announced_at", "deleted_at", "last_checked_at", "details"}
        cols = [k for k in fields if k in allowed]
        if not cols:
            return
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(cols))
        await self.pool.execute(f"UPDATE requests SET {sets} WHERE id = $1", request_id, *(fields[k] for k in cols))

    async def by_member(self, discord_id: int, include_deleted: bool = False, limit: int = 25) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            "SELECT * FROM requests WHERE requested_by = $1 AND ($2 OR status <> 'deleted') "
            "ORDER BY requested_at DESC LIMIT $3", discord_id, include_deleted, limit)

    async def recent(self, limit: int = 25) -> list[asyncpg.Record]:
        return await self.pool.fetch("SELECT * FROM requests ORDER BY requested_at DESC LIMIT $1", limit)

    async def usage(self) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            "SELECT requested_by, requested_by_name, count(*) AS items, COALESCE(sum(size_bytes), 0) AS bytes "
            "FROM requests WHERE status <> 'deleted' GROUP BY requested_by, requested_by_name ORDER BY bytes DESC")

    async def cleanup_candidates(self, keep_discord_id: int | None, limit: int = 15) -> list[asyncpg.Record]:
        """Items on disk that someone other than the owner asked for: oldest first,
        then largest. The owner's own items come last."""
        return await self.pool.fetch(
            """
            SELECT *, (requested_by IS NOT DISTINCT FROM $1) AS is_owner FROM requests
            WHERE status IN ('available', 'downloading') AND size_bytes > 0
            ORDER BY (requested_by IS NOT DISTINCT FROM $1), COALESCE(available_at, requested_at), size_bytes DESC
            LIMIT $2
            """, keep_discord_id, limit)


def _json_dumps(v: Any) -> str:
    import json
    return json.dumps(v, default=str)


def _json_loads(v: str) -> Any:
    import json
    return json.loads(v)
