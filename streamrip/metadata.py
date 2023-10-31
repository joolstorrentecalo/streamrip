"""Manages the information that will be embeded in the audio file."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional, Type, TypeVar

logger = logging.getLogger("streamrip")


def get_album_track_ids(source: str, resp) -> list[str]:
    tracklist = resp["tracks"]
    if source == "qobuz":
        tracklist = tracklist["items"]
    return [track["id"] for track in tracklist]


class Covers:
    CoverEntry = tuple[str, str | None, str | None]
    _covers: list[CoverEntry]

    def __init__(self):
        # ordered from largest to smallest
        self._covers = [
            ("original", None, None),
            ("large", None, None),
            ("small", None, None),
            ("thumbnail", None, None),
        ]

    def set_cover(self, size: str, url: str | None, path: str | None):
        i = self._indexof(size)
        self._covers[i] = (size, url, path)

    def set_cover_url(self, size: str, url: str):
        self.set_cover(size, url, None)

    @staticmethod
    def _indexof(size: str) -> int:
        if size == "original":
            return 0
        if size == "large":
            return 1
        if size == "small":
            return 2
        if size == "thumbnail":
            return 3
        raise Exception(f"Invalid {size = }")

    def empty(self) -> bool:
        return all(url is None for _, url, _ in self._covers)

    def set_largest_path(self, path: str):
        for size, url, _ in self._covers:
            if url is not None:
                self.set_cover(size, url, path)
                return
        raise Exception(f"No covers found in {self}")

    def set_path(self, size: str, path: str):
        i = self._indexof(size)
        size, url, _ = self._covers[i]
        self._covers[i] = (size, url, path)

    def largest(self) -> CoverEntry:
        for s, u, p in self._covers:
            if u is not None:
                return (s, u, p)

        raise Exception(f"No covers found in {self}")

    @classmethod
    def from_qobuz(cls, resp):
        img = resp["image"]

        c = cls()
        c.set_cover_url("original", "org".join(img["large"].rsplit("600", 1)))
        c.set_cover_url("large", img["large"])
        c.set_cover_url("small", img["small"])
        c.set_cover_url("thumbnail", img["thumbnail"])
        return c

    def get_size(self, size: str) -> CoverEntry:
        i = self._indexof(size)
        size, url, path = self._covers[i]
        if url is not None:
            return (size, url, path)
        if i + 1 < len(self._covers):
            for s, u, p in self._covers[i + 1 :]:
                if u is not None:
                    return (s, u, p)
        raise Exception(f"Cover not found for {size = }. Available: {self}")

    def __repr__(self):
        covers = "\n".join(map(repr, self._covers))
        return f"Covers({covers})"


PHON_COPYRIGHT = "\u2117"
COPYRIGHT = "\u00a9"


@dataclass(slots=True)
class TrackMetadata:
    info: TrackInfo

    title: str
    album: AlbumMetadata
    artist: str
    tracknumber: int
    discnumber: int
    composer: Optional[str]

    @classmethod
    def from_qobuz(cls, album: AlbumMetadata, resp: dict) -> TrackMetadata:
        with open("tests/qobuz_track_resp.json", "w") as f:
            json.dump(resp, f)
        title = typed(resp["title"].strip(), str)

        version = typed(resp.get("version"), str | None)
        work = typed(resp.get("work"), str | None)
        if version is not None and version not in title:
            title = f"{title} ({version})"
        if work is not None and work not in title:
            title = f"{work}: {title}"

        composer = typed(resp.get("composer", {}).get("name"), str | None)
        tracknumber = typed(resp.get("track_number", 1), int)
        discnumber = typed(resp.get("media_number", 1), int)
        artist = typed(safe_get(resp, "performer", "name"), str)
        track_id = str(resp["id"])
        bit_depth = typed(resp.get("maximum_bit_depth"), int | None)
        sampling_rate = typed(resp.get("maximum_sampling_rate"), int | float | None)
        # Is the info included?
        explicit = False

        info = TrackInfo(
            id=track_id,
            quality=album.info.quality,
            bit_depth=bit_depth,
            explicit=explicit,
            sampling_rate=sampling_rate,
            work=work,
        )
        return cls(
            info=info,
            title=title,
            album=album,
            artist=artist,
            tracknumber=tracknumber,
            discnumber=discnumber,
            composer=composer,
        )

    @classmethod
    def from_deezer(cls, album: AlbumMetadata, resp) -> TrackMetadata:
        raise NotImplemented

    @classmethod
    def from_soundcloud(cls, album: AlbumMetadata, resp) -> TrackMetadata:
        raise NotImplemented

    @classmethod
    def from_tidal(cls, album: AlbumMetadata, resp) -> TrackMetadata:
        raise NotImplemented

    @classmethod
    def from_resp(cls, album: AlbumMetadata, source, resp) -> TrackMetadata:
        if source == "qobuz":
            return cls.from_qobuz(album, resp)
        if source == "tidal":
            return cls.from_tidal(album, resp)
        if source == "soundcloud":
            return cls.from_soundcloud(album, resp)
        if source == "deezer":
            return cls.from_deezer(album, resp)
        raise Exception

    def format_track_path(self, format_string: str) -> str:
        # Available keys: "tracknumber", "artist", "albumartist", "composer", "title",
        # and "explicit", "albumcomposer"
        none_text = "Unknown"
        info = {
            "title": self.title,
            "tracknumber": self.tracknumber,
            "artist": self.artist,
            "albumartist": self.album.albumartist,
            "albumcomposer": self.album.albumcomposer or none_text,
            "composer": self.composer or none_text,
            "explicit": " (Explicit) " if self.info.explicit else "",
        }
        return format_string.format(**info)


@dataclass(slots=True)
class TrackInfo:
    id: str
    quality: int

    bit_depth: Optional[int] = None
    explicit: bool = False
    sampling_rate: Optional[int | float] = None
    work: Optional[str] = None


genre_clean = re.compile(r"([^\u2192\/]+)")


@dataclass(slots=True)
class AlbumMetadata:
    info: AlbumInfo

    album: str
    albumartist: str
    year: str
    genre: list[str]
    covers: Covers
    tracktotal: int

    disctotal: int = 1
    albumcomposer: Optional[str] = None
    comment: Optional[str] = None
    compilation: Optional[str] = None
    copyright: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    encoder: Optional[str] = None
    grouping: Optional[str] = None
    lyrics: Optional[str] = None
    purchase_date: Optional[str] = None

    def get_genres(self) -> str:
        return ", ".join(self.genre)

    def get_copyright(self) -> str | None:
        if self.copyright is None:
            return None
        # Add special chars
        _copyright = re.sub(r"(?i)\(P\)", PHON_COPYRIGHT, self.copyright)
        _copyright = re.sub(r"(?i)\(C\)", COPYRIGHT, _copyright)
        return _copyright

    def format_folder_path(self, formatter: str) -> str:
        # Available keys: "albumartist", "title", "year", "bit_depth", "sampling_rate",
        # "id", and "albumcomposer",
        none_str = "Unknown"
        info: dict[str, str | int | float] = {
            "albumartist": self.albumartist,
            "albumcomposer": self.albumcomposer or none_str,
            "bit_depth": self.info.bit_depth or none_str,
            "id": self.info.id,
            "sampling_rate": self.info.sampling_rate or none_str,
            "title": self.album,
            "year": self.year,
            "container": self.info.container,
        }
        return formatter.format(**info)

    @classmethod
    def from_qobuz(cls, resp: dict) -> AlbumMetadata:
        album = resp.get("title", "Unknown Album")
        tracktotal = resp.get("tracks_count", 1)
        genre = resp.get("genres_list") or resp.get("genre") or []
        genres = list(set(genre_clean.findall("/".join(genre))))
        date = resp.get("release_date_original") or resp.get("release_date")
        year = date[:4] if date is not None else "Unknown"

        _copyright = resp.get("copyright", "")

        if artists := resp.get("artists"):
            albumartist = ", ".join(a["name"] for a in artists)
        else:
            albumartist = typed(safe_get(resp, "artist", "name"), str)

        albumcomposer = typed(safe_get(resp, "composer", "name"), str | None)
        _label = resp.get("label")
        if isinstance(_label, dict):
            _label = _label["name"]
        label = typed(_label, str | None)
        description = typed(resp.get("description") or None, str | None)
        disctotal = typed(
            max(
                track.get("media_number", 1)
                for track in safe_get(resp, "tracks", "items", default=[{}])  # type: ignore
            )
            or 1,
            int,
        )
        explicit = typed(resp.get("parental_warning", False), bool)

        # Non-embedded information
        # version = resp.get("version")
        cover_urls = Covers.from_qobuz(resp)
        streamable = typed(resp.get("streamable", False), bool)
        assert streamable
        bit_depth = typed(resp.get("maximum_bit_depth"), int | None)
        sampling_rate = typed(resp.get("maximum_sampling_rate"), int | float | None)
        quality = get_quality_id(bit_depth, sampling_rate)
        # Make sure it is non-empty list
        booklets = typed(resp.get("goodies", None) or None, list | None)
        item_id = str(resp.get("qobuz_id"))

        if sampling_rate and bit_depth:
            container = "FLAC"
        else:
            container = "MP3"

        info = AlbumInfo(
            id=item_id,
            quality=quality,
            container=container,
            label=label,
            explicit=explicit,
            sampling_rate=sampling_rate,
            bit_depth=bit_depth,
            booklets=booklets,
        )
        return AlbumMetadata(
            info,
            album,
            albumartist,
            year,
            genre=genres,
            covers=cover_urls,
            albumcomposer=albumcomposer,
            comment=None,
            compilation=None,
            copyright=_copyright,
            date=date,
            description=description,
            disctotal=disctotal,
            encoder=None,
            grouping=None,
            lyrics=None,
            purchase_date=None,
            tracktotal=tracktotal,
        )

    @classmethod
    def from_deezer(cls, resp) -> AlbumMetadata:
        raise NotImplementedError

    @classmethod
    def from_soundcloud(cls, resp) -> AlbumMetadata:
        raise NotImplementedError

    @classmethod
    def from_tidal(cls, resp) -> AlbumMetadata:
        raise NotImplementedError

    @classmethod
    def from_resp(cls, resp: dict, source: str) -> AlbumMetadata:
        if source == "qobuz":
            return cls.from_qobuz(resp)
        if source == "tidal":
            return cls.from_tidal(resp)
        if source == "soundcloud":
            return cls.from_soundcloud(resp)
        if source == "deezer":
            return cls.from_deezer(resp)
        raise Exception("Invalid source")


@dataclass(slots=True)
class AlbumInfo:
    id: str
    quality: int
    container: str
    label: Optional[str] = None
    explicit: bool = False
    sampling_rate: Optional[int | float] = None
    bit_depth: Optional[int] = None
    booklets: list[dict] | None = None


def safe_get(d: dict, *keys, default=None) -> dict | str | int | list | None:
    """Nested __getitem__ calls with a default value.

    Use to avoid key not found errors.
    """
    _d = d
    for k in keys:
        _d = _d.get(k, {})
    if _d == {}:
        return default
    return _d


T = TypeVar("T")


def typed(thing, expected_type: Type[T]) -> T:
    assert isinstance(thing, expected_type)
    return thing


def get_quality_id(bit_depth: Optional[int], sampling_rate: Optional[int]) -> int:
    """Get the universal quality id from bit depth and sampling rate.

    :param bit_depth:
    :type bit_depth: Optional[int]
    :param sampling_rate: In kHz
    :type sampling_rate: Optional[int]
    """
    # XXX: Should `0` quality be supported?
    if bit_depth is None or sampling_rate is None:  # is lossy
        return 1

    if bit_depth == 16:
        return 2

    if bit_depth == 24:
        if sampling_rate <= 96:
            return 3

        return 4

    raise Exception(f"Invalid {bit_depth = }")
