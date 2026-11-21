"""Shared types."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Kind(str, Enum):
    MOVIE = "movie"
    SERIES = "series"
    ANIME = "anime"
    MUSIC = "music"
    BOOK = "book"
    COMIC = "comic"
    MANGA = "manga"

    @property
    def label(self) -> str:
        return {
            "movie": "Film", "series": "Series", "anime": "Anime", "music": "Album",
            "book": "Book", "comic": "Comic", "manga": "Manga",
        }[self.value]

    @property
    def app(self) -> str:
        return {
            "movie": "seerr", "series": "seerr", "anime": "seerr", "music": "lidarr",
            "book": "chaptarr", "comic": "mylar", "manga": "suwayomi",
        }[self.value]


class Status(str, Enum):
    REQUESTED = "requested"       # sent to the app, nothing downloaded yet
    DOWNLOADING = "downloading"   # partly there
    AVAILABLE = "available"       # on disk
    FAILED = "failed"
    DELETED = "deleted"           # was on disk, now gone


@dataclass
class Result:
    """One search result, in the same shape whatever app it came from."""
    kind: Kind
    ref: str                      # the app's id for it, e.g. "movie:603" or a Lidarr foreignAlbumId
    title: str
    year: int | None = None
    subtitle: str = ""            # artist, author, publisher, source...
    overview: str = ""
    image: str | None = None      # a public image URL, if there is one
    in_library: bool = False      # already requested or downloaded
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def display(self) -> str:
        return f"{self.title} ({self.year})" if self.year else self.title


@dataclass
class Requester:
    discord_id: int | None
    name: str
    seerr_user_id: int | None = None
    source: str = "discord"       # discord, seerr, yeti


class RequestError(Exception):
    """Something the person should be told about, in plain words."""
