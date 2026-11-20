"""Catalog pagination with synthetic responses only."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.apple_collection_catalog import collect


def track(identifier, disc=1, number=1, kind="songs"):
    return {"id": str(identifier), "type": kind,
            "attributes": {"name": "Generated track", "discNumber": disc,
                           "trackNumber": number, "durationInMillis": 1000}}


def api(rows, *, next_uri=None, pages=()):
    relation = {"data": rows, "href": "/synthetic/tracks"}
    if next_uri:
        relation["next"] = next_uri
    response = {"data": [{"attributes": {"name": "Generated collection"},
                           "relationships": {"tracks": relation}}]}
    return SimpleNamespace(get_album=AsyncMock(return_value=response),
                           get_playlist=AsyncMock(return_value=response),
                           get_extended_api_data=AsyncMock(side_effect=pages))


class CatalogTests(unittest.TestCase):
    def test_album_pages_are_sorted_and_duplicate_ids_removed(self):
        client = api([track(2, 2), track(1, 1, 2)], next_uri="page-2",
                     pages=[{"data": [track(3, 1, 1), track(1, 1, 2)]}])
        result = asyncio.run(collect(client, "https://music.apple.com/us/album/example/42"))
        self.assertEqual([t["id"] for t in result["tracks"]], ["3", "1", "2"])
        self.assertEqual(result["total_catalog_rows"], 4)
        client.get_extended_api_data.assert_awaited_once_with("page-2", "/synthetic/tracks")

    def test_playlist_preserves_order_and_counts_unsupported_rows(self):
        client = api([track(9), track(2), track(3, kind="music-videos")])
        result = asyncio.run(collect(client, "https://music.apple.com/gb/playlist/example/pl.test"))
        self.assertEqual([t["id"] for t in result["tracks"]], ["9", "2"])
        self.assertEqual(result["unsupported"], 1)
        self.assertEqual(result["tracks"][0]["url"], "https://music.apple.com/gb/song/9")
        client.get_album.assert_not_awaited()

    def test_repeated_page_is_rejected(self):
        client = api([track(1)], next_uri="page-2", pages=[{"data": [], "next": "page-2"}])
        with self.assertRaisesRegex(ValueError, "catalog_pagination_invalid"):
            asyncio.run(collect(client, "https://music.apple.com/us/album/example/42"))

    def test_empty_collection_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "collection_has_no_tracks"):
            asyncio.run(collect(api([]), "https://music.apple.com/us/album/example/42"))

    def test_collection_size_is_bounded(self):
        client = api([track(n) for n in range(1, 2002)])
        with self.assertRaisesRegex(ValueError, "collection_too_large"):
            asyncio.run(collect(client, "https://music.apple.com/us/album/example/42"))


if __name__ == "__main__":
    unittest.main()
