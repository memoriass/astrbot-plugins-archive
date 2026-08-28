from __future__ import annotations

import unittest

from integrations.komga import KomgaClient, KomgaError


class StubKomgaClient(KomgaClient):
    def __init__(self) -> None:
        super().__init__({"base_url": "http://127.0.0.1:25600", "api_key": "secret"})
        self.calls: list[tuple[str, dict | None]] = []
        self.responses: list[object] = []

    async def _get(self, path: str, params: dict | None = None):
        self.calls.append((path, params))
        return self.responses.pop(0)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_endpoints_and_safe_shapes(self) -> None:
        client = StubKomgaClient()
        client.responses = [
            [{"id": "lib-1", "name": "Manga", "root": "/books", "secret": {"x": 1}}],
            {"content": [{"id": "book-1", "seriesId": "series-1", "metadata": {"title": "Vol.1"}}]},
            {"content": [{"id": "series-1", "metadata": {"title": "Frieren"}, "booksCount": 3}]},
            {"id": "series-1", "metadata": {"title": "Frieren", "summary": "summary"}},
            {"content": [{"id": "book-2", "metadata": {"title": "Vol.2"}}]},
            {"content": [{"id": "book-3", "metadata": {"title": "Vol.3"}}]},
            {"content": [{"id": "collection-1", "name": "Favorites"}]},
            {"content": [{"id": "readlist-1", "name": "Queue"}]},
        ]

        self.assertEqual((await client.list_libraries())[0]["name"], "Manga")
        self.assertEqual((await client.list_recent(5))[0]["series_id"], "series-1")
        self.assertEqual((await client.search_series("Frieren", 6))[0]["books_count"], 3)
        self.assertEqual((await client.series_detail("series-1"))["summary"], "summary")
        self.assertEqual((await client.list_books("series-1", 7))[0]["name"], "Vol.2")
        self.assertEqual((await client.on_deck(8))[0]["name"], "Vol.3")
        self.assertEqual((await client.collections(9))[0]["name"], "Favorites")
        self.assertEqual((await client.readlists(10))[0]["name"], "Queue")

        self.assertEqual(client.calls[0], ("/api/v1/libraries", None))
        self.assertEqual(client.calls[3], ("/api/v1/series/series-1", None))
        self.assertEqual(client.calls[5][0], "/api/v1/books/ondeck")

    async def test_client_exposes_no_write_methods(self) -> None:
        client = StubKomgaClient()
        for name in ("scan_library", "analyze_library", "refresh_library_metadata", "refresh_series_metadata"):
            self.assertFalse(hasattr(client, name), name)

    def test_url_policy_rejects_public_and_embedded_credentials(self) -> None:
        with self.assertRaises(KomgaError):
            KomgaClient({"base_url": "https://example.com", "api_key": "x"})
        with self.assertRaises(KomgaError):
            KomgaClient({"base_url": "http://user:pass@127.0.0.1:25600", "api_key": "x"})
        client = KomgaClient(
            {"base_url": "https://example.com", "api_key": "x", "allow_public_url": True},
        )
        self.assertEqual(client.base_url, "https://example.com")


if __name__ == "__main__":
    unittest.main()

