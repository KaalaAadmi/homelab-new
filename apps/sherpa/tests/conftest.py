import os

import pytest

from sherpa.clients import (ChaptarrClient, LidarrClient, MylarClient, RadarrClient, SeerrClient, SonarrClient,
                            SuwayomiClient)
from sherpa.config import Settings
from sherpa.db import Store
from sherpa.service import Sherpa

DSN = os.environ.get("SHERPA_TEST_DSN", "postgresql://sherpa_test:test@127.0.0.1:5432/sherpa_test")
OWNER = 111


@pytest.fixture
async def store():
    s = await Store.connect(DSN)
    await s.pool.execute("TRUNCATE requests, members RESTART IDENTITY CASCADE")
    yield s
    await s.close()


@pytest.fixture
def settings(tmp_path):
    for d in ("comics", "manga"):
        (tmp_path / d).mkdir()
    return Settings(database_url=DSN, owner_discord_id=OWNER, media_dir=str(tmp_path), seerr_api_key="k",
                    max_results=10, api_token="secret-token")


@pytest.fixture
async def sherpa(store, settings):
    sh = Sherpa(settings, store,
                seerr=SeerrClient("http://seerr", "k"), radarr=RadarrClient("http://radarr", "k"),
                sonarr=SonarrClient("http://sonarr", "k"),
                lidarr=LidarrClient("http://lidarr", "k", "/data/media/music"),
                chaptarr=ChaptarrClient("http://chaptarr", "k", "/data/media/books", "/data/media/audiobooks"),
                mylar=MylarClient("http://mylar", "k"),
                suwayomi=SuwayomiClient("http://suwayomi", "u", "p"))
    yield sh
    for c in (sh.seerr, sh.radarr, sh.sonarr, sh.lidarr, sh.chaptarr, sh.mylar, sh.suwayomi):
        await c.close()
