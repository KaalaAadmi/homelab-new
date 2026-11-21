"""Settings, all from environment variables (see docker/sherpa/.env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int = 0) -> int:
    v = _env(name)
    return int(v) if v else default


@dataclass(frozen=True)
class Settings:
    # Discord
    discord_token: str = field(default_factory=lambda: _env("DISCORD_TOKEN"))
    guild_id: int = field(default_factory=lambda: _int("DISCORD_GUILD_ID"))
    household_role_id: int = field(default_factory=lambda: _int("DISCORD_HOUSEHOLD_ROLE_ID"))
    admin_role_id: int = field(default_factory=lambda: _int("DISCORD_ADMIN_ROLE_ID"))
    owner_discord_id: int = field(default_factory=lambda: _int("DISCORD_OWNER_ID"))
    announce_channel_id: int = field(default_factory=lambda: _int("DISCORD_ANNOUNCE_CHANNEL_ID"))

    # Database (the "sherpa" database on the shared Postgres)
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))

    # Apps
    seerr_url: str = field(default_factory=lambda: _env("SEERR_URL", "http://seerr:5055"))
    seerr_api_key: str = field(default_factory=lambda: _env("SEERR_API_KEY"))
    radarr_url: str = field(default_factory=lambda: _env("RADARR_URL", "http://radarr:7878"))
    radarr_api_key: str = field(default_factory=lambda: _env("RADARR_API_KEY"))
    sonarr_url: str = field(default_factory=lambda: _env("SONARR_URL", "http://sonarr:8989"))
    sonarr_api_key: str = field(default_factory=lambda: _env("SONARR_API_KEY"))
    lidarr_url: str = field(default_factory=lambda: _env("LIDARR_URL", "http://lidarr:8686"))
    lidarr_api_key: str = field(default_factory=lambda: _env("LIDARR_API_KEY"))
    lidarr_root_folder: str = field(default_factory=lambda: _env("LIDARR_ROOT_FOLDER", "/data/media/music"))
    chaptarr_url: str = field(default_factory=lambda: _env("CHAPTARR_URL", "http://chaptarr:8789"))
    chaptarr_api_key: str = field(default_factory=lambda: _env("CHAPTARR_API_KEY"))
    chaptarr_ebook_root: str = field(default_factory=lambda: _env("CHAPTARR_EBOOK_ROOT", "/data/media/books"))
    chaptarr_audiobook_root: str = field(default_factory=lambda: _env("CHAPTARR_AUDIOBOOK_ROOT", "/data/media/audiobooks"))
    mylar_url: str = field(default_factory=lambda: _env("MYLAR_URL", "http://mylar3:8090"))
    mylar_api_key: str = field(default_factory=lambda: _env("MYLAR_API_KEY"))
    suwayomi_url: str = field(default_factory=lambda: _env("SUWAYOMI_URL", "http://gluetun:4567"))
    suwayomi_user: str = field(default_factory=lambda: _env("SUWAYOMI_USER", "admin"))
    suwayomi_password: str = field(default_factory=lambda: _env("SUWAYOMI_PASSWORD"))
    suwayomi_source: str = field(default_factory=lambda: _env("SUWAYOMI_SOURCE"))

    # Files (read-only mount of ~/data/media, for sizes and free space)
    media_dir: str = field(default_factory=lambda: _env("MEDIA_DIR", "/data/media"))

    # Internal API for YETI
    api_token: str = field(default_factory=lambda: _env("SHERPA_API_TOKEN"))
    api_port: int = field(default_factory=lambda: _int("SHERPA_API_PORT", 8320))

    sync_minutes: int = field(default_factory=lambda: _int("SYNC_MINUTES", 15))
    max_results: int = field(default_factory=lambda: _int("MAX_RESULTS", 10))
