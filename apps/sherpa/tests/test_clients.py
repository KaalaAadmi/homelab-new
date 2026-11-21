import json

import httpx
import pytest
import respx

from sherpa.clients import ChaptarrClient, LidarrClient, MylarClient, SeerrClient, SuwayomiClient
from sherpa.models import Kind, RequestError, Requester

SEERR_SEARCH = {"results": [
    {"mediaType": "movie", "id": 603, "title": "The Matrix", "releaseDate": "1999-03-31", "posterPath": "/m.jpg",
     "genreIds": [28], "originalLanguage": "en"},
    {"mediaType": "tv", "id": 1429, "name": "Attack on Titan", "firstAirDate": "2013-04-07", "genreIds": [16, 10759],
     "originalLanguage": "ja", "mediaInfo": {"status": 5}},
    {"mediaType": "tv", "id": 1399, "name": "Game of Thrones", "firstAirDate": "2011-04-17", "genreIds": [18],
     "originalLanguage": "en"},
    {"mediaType": "person", "id": 6384, "name": "Keanu Reeves"},
]}


@respx.mock
async def test_seerr_search_splits_by_kind():
    respx.get("http://seerr/api/v1/search").respond(json=SEERR_SEARCH)
    c = SeerrClient("http://seerr", "k")
    movies = await c.search("x", Kind.MOVIE)
    series = await c.search("x", Kind.SERIES)
    anime = await c.search("x", Kind.ANIME)
    assert [r.ref for r in movies] == ["movie:603"]
    assert movies[0].image == "https://image.tmdb.org/t/p/w500/m.jpg" and movies[0].year == 1999
    assert [r.ref for r in series] == ["tv:1429", "tv:1399"]
    assert [r.title for r in anime] == ["Attack on Titan"] and anime[0].in_library
    assert respx.calls[0].request.headers["X-Api-Key"] == "k"
    await c.close()


@respx.mock
async def test_seerr_request_as_linked_user_and_approves_pending():
    post = respx.post("http://seerr/api/v1/request").respond(201, json={"id": 77, "status": 1})
    approve = respx.post("http://seerr/api/v1/request/77/approve").respond(200, json={"id": 77, "status": 2})
    respx.get("http://seerr/api/v1/search").respond(json=SEERR_SEARCH)
    c = SeerrClient("http://seerr", "k")
    r = (await c.search("x", Kind.SERIES))[1]
    ref = await c.request(r, Requester(5, "Sam", seerr_user_id=9))
    assert ref == "tv:1399"
    assert json.loads(post.calls[0].request.content) == {"mediaType": "tv", "mediaId": 1399, "seasons": "all",
                                                         "userId": 9}
    assert approve.called
    await c.close()


@respx.mock
async def test_seerr_conflict_is_plain_message():
    respx.post("http://seerr/api/v1/request").respond(409, json={"message": "Request for this media already exists."})
    respx.get("http://seerr/api/v1/search").respond(json=SEERR_SEARCH)
    c = SeerrClient("http://seerr", "k")
    r = (await c.search("x", Kind.MOVIE))[0]
    with pytest.raises(RequestError, match="already been requested"):
        await c.request(r, Requester(5, "Sam"))
    await c.close()


@respx.mock
async def test_unreachable_app_is_plain_message():
    respx.get("http://seerr/api/v1/search").mock(side_effect=httpx.ConnectError("boom"))
    c = SeerrClient("http://seerr", "k")
    with pytest.raises(RequestError, match="Couldn't reach Seerr"):
        await c.search("x", Kind.MOVIE)
    await c.close()


LIDARR_ALBUM = {"foreignAlbumId": "abc", "title": "Random Access Memories", "releaseDate": "2013-05-17",
                "albumType": "Album", "images": [{"coverType": "cover", "remoteUrl": "https://img/c.jpg"}],
                "artist": {"artistName": "Daft Punk", "foreignArtistId": "dp"}}


@respx.mock
async def test_lidarr_adds_new_album_without_whole_discography():
    respx.get("http://lidarr/api/v1/album/lookup").respond(json=[LIDARR_ALBUM])
    respx.get("http://lidarr/api/v1/rootfolder").respond(json=[{"path": "/other"}, {"path": "/data/media/music/"}])
    respx.get("http://lidarr/api/v1/qualityprofile").respond(json=[{"id": 3, "name": "Lossless"}])
    respx.get("http://lidarr/api/v1/metadataprofile").respond(json=[{"id": 4, "name": "Standard"}])
    add = respx.post("http://lidarr/api/v1/album").respond(201, json={"id": 42})
    c = LidarrClient("http://lidarr", "k", "/data/media/music")
    [r] = await c.search("daft", Kind.MUSIC)
    assert r.subtitle == "Daft Punk · Album" and r.image == "https://img/c.jpg"
    assert await c.request(r, Requester(1, "A")) == "lidarr:42"
    body = json.loads(add.calls[0].request.content)
    assert body["monitored"] and body["addOptions"] == {"searchForNewAlbum": True}
    assert body["artist"]["rootFolderPath"] == "/data/media/music/"
    assert body["artist"]["addOptions"]["monitor"] == "none"
    assert body["artist"]["qualityProfileId"] == 3 and body["artist"]["metadataProfileId"] == 4
    await c.close()


@respx.mock
async def test_lidarr_existing_album_is_monitored_and_searched():
    respx.get("http://lidarr/api/v1/album/lookup").respond(json=[dict(LIDARR_ALBUM, id=7, monitored=False)])
    mon = respx.put("http://lidarr/api/v1/album/monitor").respond(202, json=[])
    cmd = respx.post("http://lidarr/api/v1/command").respond(201, json={"id": 1})
    c = LidarrClient("http://lidarr", "k")
    [r] = await c.search("daft", Kind.MUSIC)
    assert not r.in_library
    assert await c.request(r, Requester(1, "A")) == "lidarr:7"
    assert json.loads(mon.calls[0].request.content) == {"albumIds": [7], "monitored": True}
    assert json.loads(cmd.calls[0].request.content) == {"name": "AlbumSearch", "albumIds": [7]}
    await c.close()


@respx.mock
async def test_chaptarr_audiobook_uses_audiobook_folder_and_profile():
    respx.get("http://chaptarr/api/v1/book/lookup").respond(json=[
        {"foreignBookId": "b1", "title": "Dune", "releaseDate": "1965-08-01", "author": {"authorName": "Frank Herbert"}}])
    respx.get("http://chaptarr/api/v1/rootfolder").respond(json=[{"path": "/data/media/books"},
                                                                 {"path": "/data/media/audiobooks"}])
    respx.get("http://chaptarr/api/v1/qualityprofile").respond(json=[{"id": 1, "name": "eBook"},
                                                                     {"id": 2, "name": "Audiobook"}])
    respx.get("http://chaptarr/api/v1/metadataprofile").respond(json=[{"id": 1}])
    add = respx.post("http://chaptarr/api/v1/book").respond(201, json={"id": 5})
    c = ChaptarrClient("http://chaptarr", "k", "/data/media/books", "/data/media/audiobooks")
    [r] = await c.search("dune", Kind.BOOK)
    assert r.subtitle == "Frank Herbert"
    assert await c.request(r, Requester(1, "A"), "audiobook") == "chaptarr:5"
    a = json.loads(add.calls[0].request.content)["author"]
    assert a["rootFolderPath"] == "/data/media/audiobooks" and a["qualityProfileId"] == 2
    assert await c.request(r, Requester(1, "A"), "ebook") == "chaptarr:5"
    a = json.loads(add.calls[1].request.content)["author"]
    assert a["rootFolderPath"] == "/data/media/books" and a["qualityProfileId"] == 1
    await c.close()


@respx.mock
async def test_mylar_search_and_add():
    route = respx.get("http://mylar/api")
    route.side_effect = [
        httpx.Response(200, json={"success": True, "data": [
            {"comicid": "4050-1", "name": "Saga", "comicyear": "2012", "publisher": "Image", "issues": 66,
             "comicimage": "https://cv/saga.jpg", "deck": "<p>Space opera</p>", "haveit": "No"}]}),
        httpx.Response(200, json={"success": True, "data": {}}),
    ]
    c = MylarClient("http://mylar", "key")
    [r] = await c.search("saga", Kind.COMIC)
    assert (r.ref, r.year, r.subtitle, r.overview) == ("4050-1", 2012, "Image · 66 issues", "Space opera")
    assert await c.request(r, Requester(1, "A")) == "mylar:4050-1"
    assert route.calls[1].request.url.params["cmd"] == "addComic"
    assert route.calls[1].request.url.params["id"] == "4050-1"
    await c.close()


@respx.mock
async def test_suwayomi_login_search_and_queue_chapters():
    calls = []

    def gql(request):
        body = json.loads(request.content)
        calls.append((body["query"], body.get("variables"), request.headers.get("Authorization")))
        q = body["query"]
        if "login" in q:
            return httpx.Response(200, json={"data": {"login": {"accessToken": "T"}}})
        if "sources" in q:
            return httpx.Response(200, json={"data": {"sources": {"nodes": [
                {"id": "0", "name": "Local"}, {"id": "123", "displayName": "MangaDex (EN)"}]}}})
        if "fetchSourceManga" in q:
            return httpx.Response(200, json={"data": {"fetchSourceManga": {"mangas": [
                {"id": 9, "title": "Berserk", "author": "Miura", "inLibrary": False,
                 "thumbnailUrl": "/api/v1/manga/9/thumbnail", "source": {"displayName": "MangaDex (EN)"}}]}}})
        if "updateManga" in q:
            return httpx.Response(200, json={"data": {"updateManga": {"manga": {"id": 9}}}})
        if "fetchChapters" in q:
            return httpx.Response(200, json={"data": {"fetchChapters": {"chapters": [
                {"id": 1, "isDownloaded": True}, {"id": 2, "isDownloaded": False}, {"id": 3, "isDownloaded": False}]}}})
        if "enqueueChapterDownloads" in q:
            return httpx.Response(200, json={"data": {"enqueueChapterDownloads": {"downloadStatus": {"state": "STARTED"}}}})
        return httpx.Response(200, json={"errors": [{"message": "unexpected"}]})

    respx.post("http://suwayomi/api/graphql").mock(side_effect=gql)
    c = SuwayomiClient("http://suwayomi", "u", "p")
    [r] = await c.search("berserk", Kind.MANGA)
    assert r.image is None and r.subtitle == "Miura · MangaDex (EN)"
    assert await c.request(r, Requester(1, "A")) == "suwayomi:9"
    assert calls[0][2] is None and all(a == "Bearer T" for _, _, a in calls[1:])
    assert calls[2][1] == {"s": "123", "q": "berserk"}
    assert calls[-1][1] == {"ids": [2, 3]}
    await c.close()
