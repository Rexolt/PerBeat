from datetime import datetime
from time import time

from app.lib.playlistlib import get_first_4_images
from app.models.playlist import Playlist
from app.models.track import Track

from app.store.tracks import TrackStore
from app.store.albums import AlbumStore
from app.store.artists import ArtistStore

from app.serializers.track import serialize_track
from app.serializers.album import album_serializer
from app.serializers.artist import serialize_for_card

from itertools import groupby

from app.utils import flatten
from app.utils.dates import (
    create_new_date,
    date_string_to_time_passed,
    timestamp_to_time_passed,
)

older_albums = set()
older_artists = set()


def calc_based_on_percent(items: list[str], total: int):
    """
    Checks if items is more than 85% of total items. Returns a boolean and the most common item.
    """
    most_common = max(items, key=items.count)
    most_common_count = items.count(most_common)

    return most_common_count / total >= 0.7, most_common, most_common_count


def check_is_album_folder(tracks: list[Track]):
    albumhashes = [t.albumhash for t in tracks]
    return calc_based_on_percent(albumhashes, len(tracks))


def check_is_artist_folder(tracks: list[Track]):
    # INFO: flatten artist hashes using "-" as a separator
    artisthashes = flatten([t.artisthashes for t in tracks])
    return calc_based_on_percent(artisthashes, len(tracks))


def check_is_track_folder(tracks: list[Track]):
    # INFO: is more of a playlist
    if len(tracks) >= 3:
        return False

    return [create_track(t) for t in tracks]


# def check_is_new_artist(hashes: set[str], artisthash: str, timestamp: int):
#     """
#     Checks if an artist already exists in the library.
#     """
#     return artisthash not in hashes


# def check_is_new_album(albumhash: str, timestamp: int):
#     """
#     Checks if an album already exists in the library.
#     """
#     tracks = filter(
#         lambda t: t.last_mod < timestamp and t.albumhash == albumhash, TrackStore.tracks
#     )

#     return next(tracks, None) is None


def create_track(t: Track):
    """
    Creates a recently added track entry.
    """
    track = serialize_track(t, to_remove={"created_date"})
    track["help_text"] = "NEW TRACK"

    return {
        "type": "track",
        "item": track,
    }


# INFO: Keys: folder, tracks, time (timestamp)
# group_type = dict[str, str | list[Track] | float]


def check_folder_type(group_: dict):
    # check if all tracks in group have the same albumhash
    # if so, return "album"
    key: str = group_["folder"]
    tracks: list[Track] = group_["tracks"]
    time: float = group_["time"]
    existing_artist_hashes: set[str] = set(ArtistStore.artistmap.keys())
    existing_album_hashes: set[str] = set(AlbumStore.albummap.keys())

    if len(tracks) == 1:
        entry = create_track(tracks[0])
        entry["item"]["time"] = timestamp_to_time_passed(time)
        return entry

    is_album, albumhash, _ = check_is_album_folder(tracks)
    if is_album:
        # album = AlbumTable.get_album_by_albumhash(albumhash)
        entry = AlbumStore.albummap.get(albumhash)

        if entry is None:
            return None

        album = album_serializer(
            entry.album,
            to_remove={
                "genres",
                "og_title",
                "date",
                "duration",
                "count",
                "albumartists_hashes",
                "base_title",
            },
        )
        album["help_text"] = (
            "NEW ALBUM" if albumhash in existing_album_hashes else "NEW TRACKS"
        )
        album["time"] = timestamp_to_time_passed(time)

        return {
            "type": "album",
            "item": album,
        }

    is_artist, artisthash, trackcount = check_is_artist_folder(tracks)
    if is_artist:
        entry = ArtistStore.artistmap.get(artisthash)

        if entry is None:
            return None

        artist = serialize_for_card(entry.artist)
        artist["trackcount"] = trackcount
        artist["help_text"] = (
            "NEW ARTIST" if artisthash not in existing_artist_hashes else "NEW MUSIC"
        )
        artist["time"] = timestamp_to_time_passed(time)

        return {
            "type": "artist",
            "item": artist,
        }

    is_track_folder = check_is_track_folder(tracks)

    return (
        is_track_folder
        if is_track_folder
        else {
            "type": "folder",
            "item": {
                "path": key,
                "count": len(tracks),
                "help_text": "NEW MUSIC",
                "time": timestamp_to_time_passed(time),
            },
        }
    )


def group_track_by_folders(tracks: list[Track], groups: dict[str, list[Track]]):
    """
    Groups tracks by folder and returns a list of groups sorted by last modified date.

    Uses generator expressions to avoid creating intermediate lists.
    """
    # INFO: sort tracks by folder name, then group by folder name
    tracks = sorted(tracks, key=lambda t: t.folder)
    thisgroup = groupby(tracks, lambda t: t.folder)

    for folder, thistracks in thisgroup:
        groups.setdefault(folder, []).extend(thistracks)

    return groups


def get_recently_added_items(limit: int = 7):
    # tracks = sorted(TrackStore.tracks, key=lambda t: t.created_date)
    now = time()
    tracks = get_recently_added_tracks(start=0, limit=None)
    then = time()

    print(f"Time taken to get tracks: {then - now}")
    groups = group_track_by_folders(tracks, {})
    # print(groups)
    # last_trackcount: int = len(tracks)

    # while len(groups.keys()) < limit and last_trackcount > 0:
    #     distracks = get_recently_added_tracks(start=len(tracks), limit=100)
    #     last_trackcount = len(distracks)

    #     tracks.extend(distracks)
    #     groups = group_track_by_folders(tracks, groups)

    grouplist = []

    # INFO: sort tracks by last modified date in descending order to get the most recent last modified date
    for folder, trackgroup in groups.items():
        trackgroup.sort(key=lambda t: t.last_mod, reverse=True)
        grouplist.append(
            {
                "folder": folder,
                "len": len(trackgroup),
                "tracks": trackgroup,
                "time": trackgroup[0].last_mod,
            }
        )

    # sort groups by last modified date
    grouplist = sorted(grouplist, key=lambda group: group["time"], reverse=True)

    recent_items = []

    for group in grouplist:
        item = check_folder_type(group)

        if item not in recent_items:
            if not item:
                continue

            (
                recent_items.append(item)
                if type(item) == dict
                else recent_items.extend(item)
            )

        if len(recent_items) >= limit:
            break

    return recent_items


def get_recently_added_playlist(limit: int = 100):
    playlist = Playlist(
        id="recentlyadded",
        name="Recently Added",
        image=None,
        last_updated="Now",
        settings={},
        trackhashes=[],
    )

    tracks = get_recently_added_tracks(limit=limit)

    try:
        # Create date to show as last updated
        date = datetime.fromtimestamp(tracks[0].last_mod)
    except IndexError:
        return playlist, []

    playlist._last_updated = date_string_to_time_passed(create_new_date(date))
    images = get_first_4_images(tracks=tracks)
    playlist.images = images
    playlist.duration = sum(t.duration for t in tracks)
    playlist.count = len(tracks)

    return playlist, tracks


def get_recently_added_tracks(start: int = 0, limit: int | None = 100):
    return TrackStore.get_recently_added(start, limit)
