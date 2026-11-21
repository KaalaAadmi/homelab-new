"""What Sherpa can do, independent of Discord. The bot and the YETI API both call this."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .clients import (ChaptarrClient, LidarrClient, MylarClient, RadarrClient, SeerrClient, SonarrClient,
                      SuwayomiClient)
from .config import Settings
from .db import Store
from .models import Kind, RequestError, Requester, Result, Status

log = logging.getLogger(__name__)
ANIME_LANGS = {"ja", "zh", "ko"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def human_size(n: int | float) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def dir_size(path: str) -> int:
    total = 0
    stack = [path]
    while stack:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def find_dirs(root: str, title: str, max_depth: int = 3) -> list[str]:
    """Folders under root whose name matches title, ignoring case and punctuation."""
    want, found = _norm(title), []
    if not want:
        return found
    stack = [(root, 0)]
    while stack:
        p, depth = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    if not e.is_dir(follow_symlinks=False):
                        continue
                    name = _norm(re.sub(r"\(\d{4}\)", "", e.name))
                    if name == want:
                        found.append(e.path)
                    elif depth + 1 < max_depth:
                        stack.append((e.path, depth + 1))
        except OSError:
            continue
    return found


@dataclass
class Space:
    total: int
    used: int
    free: int
    people: list[dict[str, Any]]
    candidates: list[dict[str, Any]]


class Sherpa:
    def __init__(self, settings: Settings, store: Store, *, seerr: SeerrClient, radarr: RadarrClient,
                 sonarr: SonarrClient, lidarr: LidarrClient, chaptarr: ChaptarrClient, mylar: MylarClient,
                 suwayomi: SuwayomiClient):
        self.s, self.db = settings, store
        self.seerr, self.radarr, self.sonarr = seerr, radarr, sonarr
        self.lidarr, self.chaptarr, self.mylar, self.suwayomi = lidarr, chaptarr, mylar, suwayomi
        self._lock = asyncio.Lock()

    @classmethod
    async def create(cls, s: Settings) -> "Sherpa":
        store = await Store.connect(s.database_url)
        return cls(s, store,
                   seerr=SeerrClient(s.seerr_url, s.seerr_api_key),
                   radarr=RadarrClient(s.radarr_url, s.radarr_api_key),
                   sonarr=SonarrClient(s.sonarr_url, s.sonarr_api_key),
                   lidarr=LidarrClient(s.lidarr_url, s.lidarr_api_key, s.lidarr_root_folder),
                   chaptarr=ChaptarrClient(s.chaptarr_url, s.chaptarr_api_key, s.chaptarr_ebook_root,
                                           s.chaptarr_audiobook_root),
                   mylar=MylarClient(s.mylar_url, s.mylar_api_key),
                   suwayomi=SuwayomiClient(s.suwayomi_url, s.suwayomi_user, s.suwayomi_password, s.suwayomi_source))

    async def close(self) -> None:
        for c in (self.seerr, self.radarr, self.sonarr, self.lidarr, self.chaptarr, self.mylar, self.suwayomi):
            await c.close()
        await self.db.close()

    def client_for(self, kind: Kind):
        return {"seerr": self.seerr, "lidarr": self.lidarr, "chaptarr": self.chaptarr,
                "mylar": self.mylar, "suwayomi": self.suwayomi}[kind.app]

    # ------------------------------------------------------------------ search and request
    async def search(self, kind: Kind, query: str) -> list[Result]:
        query = query.strip()
        if len(query) < 2:
            raise RequestError("Type at least two letters to search.")
        results = await self.client_for(kind).search(query, kind, self.s.max_results)
        for r in results:                # mark things Sherpa already tracks as taken
            if not r.in_library:
                ref = self.tracked_ref(kind, r)
                row = await self.db.get(kind.app, ref) if ref else None
                r.in_library = bool(row) and row["status"] != Status.DELETED.value
        return results

    @staticmethod
    def tracked_ref(kind: Kind, r: Result) -> str | None:
        """The app_ref a request for this result is stored under, when it can be known
        before requesting (Lidarr and Chaptarr only give an id once the item is added)."""
        if kind.app == "seerr":
            return r.ref
        if kind.app in ("mylar", "suwayomi"):
            return f"{kind.app}:{r.ref}"
        return f"{kind.app}:{r.raw['id']}" if r.raw.get("id") else None

    async def resolve(self, who: Requester) -> Requester:
        if who.discord_id is None:
            return who
        await self.db.upsert_member(who.discord_id, who.name)
        m = await self.db.member(who.discord_id)
        who.seerr_user_id = m["seerr_user_id"] if m else None
        return who

    async def request(self, kind: Kind, result: Result, who: Requester, fmt: str = "ebook") -> dict[str, Any]:
        """Send a request to the right app and record who asked. Household requests are
        never held for approval."""
        who = await self.resolve(who)
        ref = self.tracked_ref(kind, result)
        existing = await self.db.get(kind.app, ref) if ref else None
        if existing and existing["status"] != Status.DELETED.value:
            raise RequestError(f"{result.display} was already requested by {existing['requested_by_name']}.")
        async with self._lock:
            if kind is Kind.BOOK:
                ref = await self.chaptarr.request(result, who, fmt)
            elif kind.app == "seerr":
                ref = await self.seerr.request(result, who)
            else:
                ref = await self.client_for(kind).request(result, who)
        details: dict[str, Any] = {"subtitle": result.subtitle, "image": result.image}
        if kind is Kind.BOOK:
            details["format"] = fmt
        row, created = await self.db.add_request(
            kind=kind.value, title=result.title, year=result.year, app=kind.app, app_ref=ref,
            requested_by=who.discord_id, requested_by_name=who.name, source=who.source, details=details)
        out = dict(row)
        out["already_tracked"] = not created
        return out

    # ------------------------------------------------------------------ sync
    async def sync(self) -> list[dict[str, Any]]:
        """Bring in requests made in Seerr's own web page, refresh status and size of
        everything open, and return the rows that just became available."""
        try:
            await self._import_seerr()
        except RequestError as e:
            log.warning("Seerr import skipped: %s", e)
        newly: list[dict[str, Any]] = []
        for row in await self.db.open_requests():
            try:
                status, size = await self._check(row)
            except RequestError as e:
                log.info("check %s %s: %s", row["app"], row["app_ref"], e)
                continue
            except Exception:                       # one bad item must not stop the sync
                log.exception("check %s %s failed", row["app"], row["app_ref"])
                continue
            fields: dict[str, Any] = {"last_checked_at": now()}
            if status is not None and status.value != row["status"]:
                fields["status"] = status.value
                if status is Status.AVAILABLE and not row["available_at"]:
                    fields["available_at"] = now()
                if status is Status.DELETED:
                    fields["deleted_at"] = now()
            if size is not None:
                fields["size_bytes"] = size
            await self.db.update(row["id"], **fields)
            if status is Status.AVAILABLE and not row["announced_at"]:
                newly.append({**dict(row), **fields})
        return newly

    async def mark_announced(self, request_id: int) -> None:
        await self.db.update(request_id, announced_at=now())

    async def _import_seerr(self) -> None:
        for req in await self.seerr.recent_requests():
            media = req.get("media") or {}
            mt, tmdb = media.get("mediaType") or req.get("type"), media.get("tmdbId")
            if mt not in ("movie", "tv") or not tmdb:
                continue
            ref = f"{mt}:{tmdb}"
            if await self.db.get("seerr", ref):
                continue
            by = req.get("requestedBy") or {}
            member = await self.db.member_by_seerr(by["id"]) if by.get("id") else None
            info = await self.seerr.media(ref) or {}
            genres = {g.get("id") for g in info.get("genres") or []}
            kind = Kind.MOVIE if mt == "movie" else (
                Kind.ANIME if 16 in genres and info.get("originalLanguage") in ANIME_LANGS else Kind.SERIES)
            created = req.get("createdAt")
            await self.db.add_request(
                kind=kind.value, title=info.get("title") or info.get("name") or f"TMDB {tmdb}",
                year=int((info.get("releaseDate") or info.get("firstAirDate") or "0")[:4] or 0) or None,
                app="seerr", app_ref=ref, details={"tvdbId": media.get("tvdbId")},
                requested_by=member["discord_id"] if member else None,
                requested_by_name=member["name"] if member else (by.get("displayName") or "Seerr user"),
                source="seerr", requested_at=datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None)

    async def _check(self, row) -> tuple[Status | None, int | None]:
        app, ref, was = row["app"], row["app_ref"], Status(row["status"])
        had_it = was in (Status.AVAILABLE, Status.DOWNLOADING)   # it was on disk, at least partly

        if app == "seerr":
            mt, tmdb = ref.split(":")
            info = await self.seerr.media(ref) or {}
            mi = info.get("mediaInfo") or {}
            if mt == "movie":
                size = await self.radarr.size_for_tmdb(int(tmdb))
            else:
                tvdb = mi.get("tvdbId") or (row["details"] or {}).get("tvdbId")
                size = await self.sonarr.size_for_tvdb(int(tvdb)) if tvdb else None
            st = {5: Status.AVAILABLE, 4: Status.DOWNLOADING}.get(mi.get("status"))
            if size is None or (size == 0 and was is Status.AVAILABLE):
                return (Status.DELETED if had_it else None), None
            if st is None:
                st = Status.AVAILABLE if size > 0 and had_it else (Status.DOWNLOADING if size > 0 else None)
            return st, size

        if app in ("lidarr", "chaptarr"):
            client = self.lidarr if app == "lidarr" else self.chaptarr
            size = await client.size(ref)
            if size is None or (size == 0 and was is Status.AVAILABLE):
                return Status.DELETED, None
            return (Status.AVAILABLE if size > 0 else None), size

        if app == "mylar":
            loc = await self.mylar.location(ref)
            if loc is None:
                return Status.DELETED, None
            size = await asyncio.to_thread(self._comic_size, loc, row["title"])
            return (Status.AVAILABLE if size > 0 else None), size

        if app == "suwayomi":
            m = await self.suwayomi.manga(ref)
            if not m or not m.get("inLibrary"):
                return Status.DELETED, None
            size = await asyncio.to_thread(self._manga_size, m.get("title") or row["title"])
            return (Status.AVAILABLE if size > 0 else None), size

        return None, None

    def _comic_size(self, location: str, title: str) -> int:
        base = os.path.basename(location.rstrip("/"))
        root = os.path.join(self.s.media_dir, "comics")
        direct = os.path.join(root, base)
        if base and os.path.isdir(direct):
            return dir_size(direct)
        return sum(dir_size(p) for p in find_dirs(root, base or title, 2))

    def _manga_size(self, title: str) -> int:
        return sum(dir_size(p) for p in find_dirs(os.path.join(self.s.media_dir, "manga"), title, 4))

    # ------------------------------------------------------------------ reading
    async def downloads(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for client in (self.radarr, self.sonarr, self.lidarr, self.chaptarr, self.suwayomi):
            try:
                out.extend(await client.queue())
            except RequestError as e:
                log.info("queue %s: %s", client.name, e)
        return out

    async def mine(self, discord_id: int) -> list[dict[str, Any]]:
        return [dict(r) for r in await self.db.by_member(discord_id)]

    async def space(self) -> Space:
        try:
            du = shutil.disk_usage(self.s.media_dir)
            total, used, free = du.total, du.used, du.free
        except OSError:
            total = used = free = 0
        people = [dict(r) for r in await self.db.usage()]
        cands = [dict(r) for r in await self.db.cleanup_candidates(self.s.owner_discord_id or None)]
        return Space(total, used, free, people, cands)
