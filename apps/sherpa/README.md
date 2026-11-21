# Sherpa

The household's media request bot for Discord, and the request service YETI calls.
Setup, Discord server layout and commands: see "Discord server and Sherpa" in the main README.

```
sherpa/
  config.py    settings from environment variables (docker/sherpa/.env)
  models.py    Kind (movie, series, anime, music, book, comic, manga), Result, Requester
  clients.py   one client per app: Seerr, Radarr, Sonarr, Lidarr, Chaptarr, Mylar3, Suwayomi
  db.py        who asked for what (Postgres database "sherpa")
  service.py   search, request, sync (status, sizes, deletions), downloads, space
  bot.py       Discord slash commands, menus, buttons, "it's ready" posts
  api.py       HTTP API for YETI (bearer token)
```

Rules the code keeps:
- Search, request and read only. No client has a delete or settings call.
- The first person to request an item owns it until it's deleted from the app.
- Household requests are never held for approval (Seerr requests left pending are approved).

Tests (need a local Postgres; the DSN is in tests/conftest.py, or set SHERPA_TEST_DSN):
```bash
pip install -r requirements-dev.txt
pytest
```
