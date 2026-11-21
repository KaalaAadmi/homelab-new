import respx
from aiohttp.test_utils import TestClient, TestServer

from conftest import OWNER
from sherpa.api import Api


async def client(sherpa):
    c = TestClient(TestServer(Api(sherpa, "secret-token", OWNER).app()))
    await c.start_server()
    return c


async def test_needs_token(sherpa):
    c = await client(sherpa)
    assert (await c.get("/health")).status == 200
    assert (await c.get("/v1/space")).status == 401
    assert (await c.get("/v1/space", headers={"Authorization": "Bearer nope"})).status == 401
    assert (await c.get("/v1/space", headers={"Authorization": "Bearer secret-token"})).status == 200
    assert (await c.delete("/v1/request", headers={"Authorization": "Bearer secret-token"})).status == 405
    await c.close()


@respx.mock
async def test_search_then_request_on_behalf(sherpa):
    respx.get("http://seerr/api/v1/search").respond(json={"results": [
        {"mediaType": "movie", "id": 603, "title": "The Matrix", "releaseDate": "1999-03-31"}]})
    respx.post("http://seerr/api/v1/request").respond(201, json={"id": 1, "status": 2})
    c = await client(sherpa)
    h = {"Authorization": "Bearer secret-token"}
    r = await c.get("/v1/search", params={"kind": "movie", "q": "matrix"}, headers=h)
    [res] = (await r.json())["results"]
    assert res["ref"] == "movie:603" and "raw" not in res
    r = await c.post("/v1/request", json={"kind": "movie", "ref": "movie:603"}, headers=h)
    assert r.status == 201
    body = (await r.json())["request"]
    assert (body["requested_by"], body["source"]) == (OWNER, "yeti")
    r = await c.post("/v1/request", json={"kind": "movie", "ref": "movie:603"}, headers=h)
    assert r.status == 422 and "already requested" in (await r.json())["error"]
    r = await c.post("/v1/request", json={"kind": "nope", "ref": "x"}, headers=h)
    assert r.status == 400
    await c.close()
