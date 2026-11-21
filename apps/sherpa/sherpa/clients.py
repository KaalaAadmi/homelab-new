"""One small client per app. Each turns the app's own API into Result objects.

Every client can search and add. None of them has code to delete or change settings:
that is deliberate, so neither the bot nor YETI (which talks to Sherpa's API) can remove
anything from the library.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from .models import Kind, RequestError, Requester, Result, Status

log = logging.getLogger(__name__)
TMDB_IMG = "https://image.tmdb.org/t/p/w500"
TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _year(date: str | None) -> int | None:
    m = re.match(r"(\d{4})", date or "")
    return int(m.group(1)) if m else None


def _cover(images: list[dict] | None, *types: str) -> str | None:
    for t in types or ("cover", "poster"):
        for img in images or []:
            if img.get("coverType") == t:
                url = img.get("remoteUrl") or img.get("url") or ""
                if url.startswith("http"):
                    return url
    return None


class _Http:
    name = "app"

    def __init__(self, base_url: str, headers: dict[str, str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.http = httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers or {},
                                      timeout=TIMEOUT, transport=transport)

    async def _call(self, method: str, path: str, **kw) -> Any:
        try:
            r = await self.http.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise RequestError(f"Couldn't reach {self.name}. Is it running?") from e
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            log.warning("%s %s %s -> %s %s", self.name, method, path, r.status_code, r.text[:300])
            raise RequestError(f"{self.name} said no ({r.status_code}): {self._error_text(r)}")
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            return r.text

    @staticmethod
    def _error_text(r: httpx.Response) -> str:
        try:
            body = r.json()
        except ValueError:
            return r.text[:200]
        if isinstance(body, dict):
            return str(body.get("message") or body.get("error") or body)[:200]
        if isinstance(body, list) and body and isinstance(body[0], dict):
            return str(body[0].get("errorMessage") or body[0])[:200]
        return str(body)[:200]

    async def close(self) -> None:
        await self.http.aclose()


# --------------------------------------------------------------------------- Seerr
class SeerrClient(_Http):
    """Films, series and anime. Requests go through Seerr so its own rules, per-person
    limits and "now available" notifications keep working."""
    name = "Seerr"

    def __init__(self, url: str, api_key: str, **kw):
        super().__init__(url, {"X-Api-Key": api_key}, **kw)

    async def search(self, query: str, kind: Kind, limit: int = 10) -> list[Result]:
        data = await self._call("GET", "/api/v1/search", params={"query": query, "page": 1}) or {}
        out: list[Result] = []
        for it in data.get("results", []):
            mt = it.get("mediaType")
            if mt not in ("movie", "tv"):
                continue
            is_anime = 16 in (it.get("genreIds") or []) and it.get("originalLanguage") in ("ja", "zh", "ko")
            if kind is Kind.MOVIE and mt != "movie":
                continue
            if kind is Kind.SERIES and mt != "tv":
                continue
            if kind is Kind.ANIME and not is_anime:
                continue
            status = (it.get("mediaInfo") or {}).get("status") or 1
            out.append(Result(
                kind=kind, ref=f"{mt}:{it['id']}",
                title=it.get("title") or it.get("name") or "?",
                year=_year(it.get("releaseDate") or it.get("firstAirDate")),
                subtitle="Film" if mt == "movie" else "Series",
                overview=(it.get("overview") or "")[:600],
                image=TMDB_IMG + it["posterPath"] if it.get("posterPath") else None,
                in_library=status >= 2, raw=it))
            if len(out) >= limit:
                break
        return out

    async def request(self, result: Result, who: Requester) -> str:
        mt, tmdb = result.ref.split(":")
        body: dict[str, Any] = {"mediaType": mt, "mediaId": int(tmdb)}
        if mt == "tv":
            body["seasons"] = "all"
        if who.seerr_user_id:
            body["userId"] = who.seerr_user_id
        try:
            req = await self._call("POST", "/api/v1/request", json=body) or {}
        except RequestError as e:
            if "409" in str(e) or "already" in str(e).lower():
                raise RequestError(f"{result.display} has already been requested.") from e
            raise
        if isinstance(req, dict) and req.get("status") == 1 and req.get("id"):
            # Pending: household requests are never held for approval, so approve it here.
            await self._call("POST", f"/api/v1/request/{req['id']}/approve")
        return result.ref

    async def media(self, ref: str) -> dict | None:
        mt, tmdb = ref.split(":")
        return await self._call("GET", f"/api/v1/{mt}/{tmdb}")

    async def status(self, ref: str) -> Status | None:
        info = ((await self.media(ref)) or {}).get("mediaInfo")
        if not info:
            return None
        return {5: Status.AVAILABLE, 4: Status.DOWNLOADING}.get(info.get("status"), Status.REQUESTED)

    async def recent_requests(self, take: int = 50) -> list[dict]:
        data = await self._call("GET", "/api/v1/request",
                                params={"take": take, "skip": 0, "sort": "added", "filter": "all"}) or {}
        return data.get("results", [])

    async def users(self) -> list[dict]:
        data = await self._call("GET", "/api/v1/user", params={"take": 100}) or {}
        return data.get("results", [])


# --------------------------------------------------------------------------- *arr base
class _Arr(_Http):
    api = "/api/v3"

    def __init__(self, url: str, api_key: str, **kw):
        super().__init__(url, {"X-Api-Key": api_key}, **kw)

    async def queue(self) -> list[dict]:
        data = await self._call("GET", f"{self.api}/queue",
                                params={"pageSize": 50, "includeUnknownSeriesItems": "false"}) or {}
        out = []
        for q in data.get("records", []):
            size, left = q.get("size") or 0, q.get("sizeleft") or 0
            out.append({"app": self.name, "title": q.get("title") or "?",
                        "progress": round(100 * (1 - left / size)) if size else 0,
                        "eta": q.get("timeleft") or "", "state": q.get("trackedDownloadState") or q.get("status")})
        return out


class RadarrClient(_Arr):
    name = "Radarr"

    async def size_for_tmdb(self, tmdb_id: int) -> int | None:
        movies = await self._call("GET", f"{self.api}/movie", params={"tmdbId": tmdb_id})
        if not movies:
            return None
        return int(movies[0].get("sizeOnDisk") or 0)


class SonarrClient(_Arr):
    name = "Sonarr"

    async def size_for_tvdb(self, tvdb_id: int) -> int | None:
        series = await self._call("GET", f"{self.api}/series", params={"tvdbId": tvdb_id})
        if not series:
            return None
        return int((series[0].get("statistics") or {}).get("sizeOnDisk") or 0)


class LidarrClient(_Arr):
    """Music. Lidarr works with albums and artists, not single tracks: a song request
    adds the album (or single) it is on."""
    name = "Lidarr"
    api = "/api/v1"

    def __init__(self, url: str, api_key: str, root_folder: str = "", **kw):
        super().__init__(url, api_key, **kw)
        self.root_folder = root_folder

    async def search(self, query: str, kind: Kind, limit: int = 10) -> list[Result]:
        albums = await self._call("GET", f"{self.api}/album/lookup", params={"term": query}) or []
        out = []
        for a in albums[:limit]:
            artist = a.get("artist") or {}
            out.append(Result(
                kind=Kind.MUSIC, ref=a.get("foreignAlbumId") or str(a.get("id")),
                title=a.get("title") or "?", year=_year(a.get("releaseDate")),
                subtitle=" · ".join(x for x in (artist.get("artistName"), a.get("albumType")) if x),
                overview=(a.get("overview") or "")[:600],
                image=_cover(a.get("images"), "cover") or _cover(artist.get("images"), "poster"),
                in_library=bool(a.get("id")) and bool(a.get("monitored")), raw=a))
        return out

    async def _defaults(self) -> dict[str, Any]:
        roots = await self._call("GET", f"{self.api}/rootfolder") or []
        qps = await self._call("GET", f"{self.api}/qualityprofile") or []
        mps = await self._call("GET", f"{self.api}/metadataprofile") or []
        if not roots or not qps or not mps:
            raise RequestError("Lidarr isn't set up yet: add a root folder and profiles first.")
        root = next((r for r in roots if r.get("path", "").rstrip("/") == self.root_folder.rstrip("/")), roots[0])
        return {"rootFolderPath": root["path"], "qualityProfileId": qps[0]["id"], "metadataProfileId": mps[0]["id"]}

    async def request(self, result: Result, who: Requester) -> str:
        a = result.raw
        if a.get("id"):                          # album already known (artist in library): monitor + search
            await self._call("PUT", f"{self.api}/album/monitor", json={"albumIds": [a["id"]], "monitored": True})
            await self._call("POST", f"{self.api}/command", json={"name": "AlbumSearch", "albumIds": [a["id"]]})
            return f"lidarr:{a['id']}"
        d = await self._defaults()
        artist = dict(a.get("artist") or {})
        artist.update(d, monitored=True, monitorNewItems="none",
                      addOptions={"monitor": "none", "searchForMissingAlbums": False})
        body = dict(a, artist=artist, monitored=True, addOptions={"searchForNewAlbum": True})
        added = await self._call("POST", f"{self.api}/album", json=body) or {}
        if not added.get("id"):
            raise RequestError("Lidarr didn't add the album.")
        return f"lidarr:{added['id']}"

    async def size(self, ref: str) -> int | None:
        album = await self._call("GET", f"{self.api}/album/{ref.split(':')[1]}")
        if not album:
            return None
        return int((album.get("statistics") or {}).get("sizeOnDisk") or 0)


class ChaptarrClient(_Arr):
    """Books (ebook or audiobook). Chaptarr is a Readarr fork; this uses Readarr's API."""
    name = "Chaptarr"
    api = "/api/v1"

    def __init__(self, url: str, api_key: str, ebook_root: str = "", audiobook_root: str = "", **kw):
        super().__init__(url, api_key, **kw)
        self.roots = {"ebook": ebook_root, "audiobook": audiobook_root}

    async def search(self, query: str, kind: Kind, limit: int = 10) -> list[Result]:
        books = await self._call("GET", f"{self.api}/book/lookup", params={"term": query}) or []
        out = []
        for b in books[:limit]:
            author = (b.get("author") or {}).get("authorName") or b.get("authorTitle") or ""
            out.append(Result(
                kind=Kind.BOOK, ref=b.get("foreignBookId") or str(b.get("id")),
                title=b.get("title") or "?", year=_year(b.get("releaseDate")), subtitle=author,
                overview=(b.get("overview") or "")[:600], image=_cover(b.get("images"), "cover"),
                in_library=bool(b.get("id")) and bool(b.get("monitored")), raw=b))
        return out

    async def _defaults(self, fmt: str) -> dict[str, Any]:
        roots = await self._call("GET", f"{self.api}/rootfolder") or []
        qps = await self._call("GET", f"{self.api}/qualityprofile") or []
        mps = await self._call("GET", f"{self.api}/metadataprofile") or []
        if not roots or not qps or not mps:
            raise RequestError("Chaptarr isn't set up yet: add root folders and profiles first.")
        want = self.roots.get(fmt, "").rstrip("/")
        root = next((r for r in roots if r.get("path", "").rstrip("/") == want), roots[0])
        audio = [q for q in qps if "audio" in q.get("name", "").lower()]
        other = [q for q in qps if q not in audio]
        qp = (audio or qps)[0] if fmt == "audiobook" else (other or qps)[0]
        return {"rootFolderPath": root["path"], "qualityProfileId": qp["id"], "metadataProfileId": mps[0]["id"]}

    async def request(self, result: Result, who: Requester, fmt: str = "ebook") -> str:
        b = result.raw
        if b.get("id"):
            await self._call("PUT", f"{self.api}/book/monitor", json={"bookIds": [b["id"]], "monitored": True})
            await self._call("POST", f"{self.api}/command", json={"name": "BookSearch", "bookIds": [b["id"]]})
            return f"chaptarr:{b['id']}"
        d = await self._defaults(fmt)
        author = dict(b.get("author") or {})
        author.update(d, monitored=True, addOptions={"monitor": "none", "searchForMissingBooks": False})
        body = dict(b, author=author, monitored=True, addOptions={"searchForNewBook": True})
        added = await self._call("POST", f"{self.api}/book", json=body) or {}
        if not added.get("id"):
            raise RequestError("Chaptarr didn't add the book.")
        return f"chaptarr:{added['id']}"

    async def size(self, ref: str) -> int | None:
        book = await self._call("GET", f"{self.api}/book/{ref.split(':')[1]}")
        if not book:
            return None
        return int((book.get("statistics") or {}).get("sizeOnDisk") or 0)


# --------------------------------------------------------------------------- Mylar3
class MylarClient(_Http):
    """Western comics, searched on ComicVine through Mylar3."""
    name = "Mylar3"

    def __init__(self, url: str, api_key: str, **kw):
        super().__init__(url, **kw)
        self.key = api_key

    async def _cmd(self, cmd: str, **params) -> Any:
        data = await self._call("GET", "/api", params={"apikey": self.key, "cmd": cmd, **params})
        if isinstance(data, dict) and "data" in data:
            if data.get("success") is False:
                raise RequestError(f"Mylar3: {data.get('error') or 'request failed'}")
            return data["data"]
        return data

    async def search(self, query: str, kind: Kind, limit: int = 10) -> list[Result]:
        items = await self._cmd("findComic", name=query) or []
        if isinstance(items, dict):
            items = items.get("results") or list(items.values())
        out = []
        for c in items[:limit]:
            if not isinstance(c, dict):
                continue
            issues = c.get("issues") or c.get("ComicIssues")
            sub = " · ".join(str(x) for x in (c.get("publisher"), f"{issues} issues" if issues else None) if x)
            img = c.get("comicimage") or c.get("ComicImage") or c.get("image")
            out.append(Result(
                kind=Kind.COMIC, ref=str(c.get("comicid") or c.get("ComicID") or c.get("id")),
                title=c.get("name") or c.get("ComicName") or "?",
                year=_year(str(c.get("comicyear") or c.get("ComicYear") or "")), subtitle=sub,
                overview=re.sub("<[^>]+>", "", c.get("deck") or c.get("description") or "")[:600],
                image=img if img and str(img).startswith("http") else None,
                in_library=str(c.get("haveit", "No")) not in ("No", "None", ""), raw=c))
        return out

    async def request(self, result: Result, who: Requester) -> str:
        await self._cmd("addComic", id=result.ref)
        return f"mylar:{result.ref}"

    async def location(self, ref: str) -> str | None:
        data = await self._cmd("getComic", id=ref.split(":")[1])
        comic = (data or {}).get("comic") if isinstance(data, dict) else None
        if isinstance(comic, list):
            comic = comic[0] if comic else None
        if not comic:
            return None                     # not in Mylar any more
        return comic.get("ComicLocation") or comic.get("location") or ""


# --------------------------------------------------------------------------- Suwayomi
class SuwayomiClient(_Http):
    """Manga. Adds the series to Suwayomi's library and queues its chapters; new chapters
    then download by themselves (Suwayomi setting: download new chapters)."""
    name = "Suwayomi"

    def __init__(self, url: str, user: str, password: str, source: str = "", **kw):
        super().__init__(url, **kw)
        self.user, self.password, self.source_pref = user, password, source
        self._token: str | None = None
        self._source_id: str | None = None

    async def _login(self) -> None:
        q = "mutation($u:String!,$p:String!){login(input:{username:$u,password:$p}){accessToken}}"
        r = await self._call("POST", "/api/graphql", json={"query": q, "variables": {"u": self.user, "p": self.password}})
        token = (((r or {}).get("data") or {}).get("login") or {}).get("accessToken")
        if not token:
            raise RequestError("Couldn't log in to Suwayomi: check SUWAYOMI_USER and SUWAYOMI_PASSWORD.")
        self._token = token

    async def gql(self, query: str, variables: dict | None = None, retry: bool = True) -> dict:
        if not self._token:
            await self._login()
        try:
            r = await self._call("POST", "/api/graphql", json={"query": query, "variables": variables or {}},
                                 headers={"Authorization": f"Bearer {self._token}"})
        except RequestError as e:
            if retry and "401" in str(e):
                self._token = None
                return await self.gql(query, variables, retry=False)
            raise
        if isinstance(r, dict) and r.get("errors"):
            msg = r["errors"][0].get("message", "error")
            if retry and "auth" in msg.lower():
                self._token = None
                return await self.gql(query, variables, retry=False)
            raise RequestError(f"Suwayomi: {msg}")
        return (r or {}).get("data") or {}

    async def source_id(self) -> str:
        if self._source_id:
            return self._source_id
        data = await self.gql("{sources{nodes{id name displayName lang}}}")
        nodes = [n for n in data.get("sources", {}).get("nodes", []) if str(n.get("id")) != "0"]
        if not nodes:
            raise RequestError("Suwayomi has no sources installed yet. Add an extension in Suwayomi first.")
        pref = self.source_pref.lower()
        pick = next((n for n in nodes if pref and pref in (n.get("displayName") or n.get("name") or "").lower()), nodes[0])
        self._source_id = str(pick["id"])
        return self._source_id

    async def search(self, query: str, kind: Kind, limit: int = 10) -> list[Result]:
        q = ("mutation($s:LongString!,$q:String){fetchSourceManga(input:{source:$s,type:SEARCH,page:1,query:$q})"
             "{mangas{id title author description genre inLibrary thumbnailUrl source{displayName}}}}")
        data = await self.gql(q, {"s": await self.source_id(), "q": query})
        out = []
        for m in (data.get("fetchSourceManga") or {}).get("mangas", [])[:limit]:
            thumb = m.get("thumbnailUrl") or ""
            out.append(Result(
                kind=Kind.MANGA, ref=str(m["id"]), title=m.get("title") or "?",
                subtitle=" · ".join(x for x in (m.get("author"), (m.get("source") or {}).get("displayName")) if x),
                overview=(m.get("description") or "")[:600],
                image=thumb if thumb.startswith("http") else None,     # Suwayomi's own image URLs need a login
                in_library=bool(m.get("inLibrary")), raw=m))
        return out

    async def request(self, result: Result, who: Requester) -> str:
        mid = int(result.ref)
        await self.gql("mutation($id:Int!){updateManga(input:{id:$id,patch:{inLibrary:true}}){manga{id}}}", {"id": mid})
        data = await self.gql("mutation($id:Int!){fetchChapters(input:{mangaId:$id}){chapters{id isDownloaded}}}", {"id": mid})
        ids = [c["id"] for c in (data.get("fetchChapters") or {}).get("chapters", []) if not c.get("isDownloaded")]
        if ids:
            await self.gql("mutation($ids:[Int!]!){enqueueChapterDownloads(input:{ids:$ids}){downloadStatus{state}}}",
                           {"ids": ids})
        return f"suwayomi:{mid}"

    async def manga(self, ref: str) -> dict | None:
        data = await self.gql("query($id:Int!){manga(id:$id){id title inLibrary}}", {"id": int(ref.split(":")[1])})
        return data.get("manga")

    async def queue(self) -> list[dict]:
        data = await self.gql("{downloadStatus{state queue{progress state manga{title} chapter{name}}}}")
        return [{"app": "Suwayomi", "title": f"{q['manga']['title']}: {q['chapter']['name']}",
                 "progress": round(100 * (q.get("progress") or 0)), "eta": "", "state": q.get("state")}
                for q in (data.get("downloadStatus") or {}).get("queue", [])]
