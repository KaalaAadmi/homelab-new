import httpx
import pytest
import respx

from conftest import OWNER
from sherpa.models import Kind, RequestError, Requester, Result


def movie(ref="movie:603", title="The Matrix"):
    return Result(kind=Kind.MOVIE, ref=ref, title=title, year=1999)


@respx.mock
async def test_first_requester_owns_item_and_second_is_told(sherpa):
    respx.post("http://seerr/api/v1/request").respond(201, json={"id": 1, "status": 2})
    row = await sherpa.request(Kind.MOVIE, movie(), Requester(222, "Sam"))
    assert (row["requested_by"], row["requested_by_name"], row["app"], row["status"]) == (222, "Sam", "seerr",
                                                                                         "requested")
    with pytest.raises(RequestError, match="already requested by Sam"):
        await sherpa.request(Kind.MOVIE, movie(), Requester(OWNER, "Arnav"))


@respx.mock
async def test_sync_tracks_size_available_then_deleted(sherpa, settings):
    respx.post("http://seerr/api/v1/request").respond(201, json={"id": 1, "status": 2})
    respx.get("http://seerr/api/v1/request").respond(json={"results": []})
    await sherpa.request(Kind.MOVIE, movie(), Requester(222, "Sam"))

    media = respx.get("http://seerr/api/v1/movie/603")
    radarr = respx.get("http://radarr/api/v3/movie")
    media.respond(json={"mediaInfo": {"status": 3}})
    radarr.respond(json=[{"sizeOnDisk": 0}])
    assert await sherpa.sync() == []

    media.respond(json={"mediaInfo": {"status": 5}})
    radarr.respond(json=[{"sizeOnDisk": 8_000_000_000}])
    [ready] = await sherpa.sync()
    assert ready["status"] == "available" and ready["size_bytes"] == 8_000_000_000
    await sherpa.mark_announced(ready["id"])
    assert await sherpa.sync() == []          # announced once only

    radarr.respond(json=[])                   # removed from Radarr
    await sherpa.sync()
    row = await sherpa.db.get("seerr", "movie:603")
    assert row["status"] == "deleted" and row["deleted_at"] is not None

    # once deleted, someone else can ask for it again and they own the new copy
    row = await sherpa.request(Kind.MOVIE, movie(), Requester(OWNER, "Arnav"))
    assert row["requested_by"] == OWNER and row["status"] == "requested" and row["size_bytes"] == 0


@respx.mock
async def test_space_lists_other_peoples_items_first(sherpa):
    respx.post("http://seerr/api/v1/request").respond(201, json={"id": 1, "status": 2})
    for ref, who in (("movie:1", Requester(OWNER, "Arnav")), ("movie:2", Requester(222, "Sam")),
                     ("movie:3", Requester(333, "Priya"))):
        row = await sherpa.request(Kind.MOVIE, movie(ref, ref), who)
        await sherpa.db.update(row["id"], status="available", size_bytes={"movie:1": 50, "movie:2": 10,
                                                                          "movie:3": 20}[ref])
    sp = await sherpa.space()
    assert [c["app_ref"] for c in sp.candidates] == ["movie:2", "movie:3", "movie:1"]
    assert [c["is_owner"] for c in sp.candidates] == [False, False, True]
    assert {p["requested_by_name"]: p["bytes"] for p in sp.people} == {"Arnav": 50, "Sam": 10, "Priya": 20}


@respx.mock
async def test_seerr_web_requests_are_imported_with_linked_member(sherpa):
    await sherpa.db.link_seerr(333, "Priya", 9)
    respx.get("http://seerr/api/v1/request").respond(json={"results": [
        {"id": 5, "type": "tv", "createdAt": "2026-11-01T10:00:00.000Z",
         "media": {"mediaType": "tv", "tmdbId": 1429, "tvdbId": 267440}, "requestedBy": {"id": 9}},
        {"id": 6, "type": "movie", "media": {"mediaType": "movie", "tmdbId": 10}, "requestedBy": {"id": 2,
                                                                                               "displayName": "Guest"}},
    ]})
    respx.get("http://seerr/api/v1/tv/1429").respond(json={"name": "Attack on Titan", "firstAirDate": "2013-04-07",
                                                           "genres": [{"id": 16}], "originalLanguage": "ja"})
    respx.get("http://seerr/api/v1/movie/10").respond(json={"title": "Some Film", "releaseDate": "2020-01-01"})
    respx.get("http://sonarr/api/v3/series").respond(json=[])
    respx.get("http://radarr/api/v3/movie").respond(json=[])
    await sherpa.sync()
    aot = await sherpa.db.get("seerr", "tv:1429")
    assert (aot["kind"], aot["requested_by"], aot["requested_by_name"], aot["source"]) == ("anime", 333, "Priya",
                                                                                           "seerr")
    assert aot["requested_at"].year == 2026 and aot["details"]["tvdbId"] == 267440
    film = await sherpa.db.get("seerr", "movie:10")
    assert (film["kind"], film["requested_by"], film["requested_by_name"]) == ("movie", None, "Guest")


@respx.mock
async def test_manga_size_from_folder_and_deleted_when_removed(sherpa, settings, tmp_path):
    folder = tmp_path / "manga" / "mangas" / "MangaDex (EN)" / "Berserk" / "Chapter 1"
    folder.mkdir(parents=True)
    (folder / "001.jpg").write_bytes(b"x" * 1000)
    r = Result(kind=Kind.MANGA, ref="9", title="Berserk")
    sherpa.suwayomi._token = "T"
    gql = respx.post("http://suwayomi/api/graphql")
    gql.side_effect = [
        httpx.Response(200, json={"data": {"updateManga": {}}}),
        httpx.Response(200, json={"data": {"fetchChapters": {"chapters": []}}}),
        httpx.Response(200, json={"data": {"manga": {"id": 9, "title": "Berserk", "inLibrary": True}}}),
        httpx.Response(200, json={"data": {"manga": {"id": 9, "title": "Berserk", "inLibrary": False}}}),
    ]
    respx.get("http://seerr/api/v1/request").respond(json={"results": []})
    await sherpa.request(Kind.MANGA, r, Requester(222, "Sam"))
    [ready] = await sherpa.sync()
    assert ready["size_bytes"] == 1000
    await sherpa.sync()
    assert (await sherpa.db.get("suwayomi", "suwayomi:9"))["status"] == "deleted"


@respx.mock
async def test_search_marks_tracked_items(sherpa):
    respx.post("http://seerr/api/v1/request").respond(201, json={"id": 1, "status": 2})
    await sherpa.request(Kind.MOVIE, movie(), Requester(222, "Sam"))
    respx.get("http://seerr/api/v1/search").respond(json={"results": [
        {"mediaType": "movie", "id": 603, "title": "The Matrix"}, {"mediaType": "movie", "id": 604, "title": "Reloaded"}]})
    rs = await sherpa.search(Kind.MOVIE, "matrix")
    assert [r.in_library for r in rs] == [True, False]
    with pytest.raises(RequestError):
        await sherpa.search(Kind.MOVIE, " a ")
