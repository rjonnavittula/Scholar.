import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.media_store as media_store


class TestMediaStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.patcher = patch.object(media_store, "MEDIA_ROOT", self.tmpdir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_media_writes_a_file_and_returns_a_media_route_url(self):
        url = media_store.save_media(7, "image/png", b"\x89PNG-fake-bytes")
        self.assertTrue(url.startswith("/learn/tutor/media/"))
        filename = url.rsplit("/", 1)[-1]
        self.assertTrue(filename.endswith(".png"))
        self.assertTrue(filename.startswith("7_"))
        self.assertTrue((self.tmpdir / filename).is_file())

    def test_read_media_round_trips_saved_bytes(self):
        url = media_store.save_media(1, "image/png", b"hello-bytes")
        filename = url.rsplit("/", 1)[-1]
        self.assertEqual(media_store.read_media(filename), b"hello-bytes")

    def test_read_media_returns_none_for_missing_file(self):
        self.assertIsNone(media_store.read_media("does-not-exist.png"))

    def test_read_media_rejects_path_traversal_attempts(self):
        self.assertIsNone(media_store.read_media("../../etc/passwd"))
        self.assertIsNone(media_store.read_media("..\\..\\secrets.txt"))
        self.assertIsNone(media_store.read_media("sub/dir.png"))
        self.assertIsNone(media_store.read_media(".."))

    def test_media_content_type_maps_known_extensions(self):
        self.assertEqual(media_store.media_content_type("abc.png"), "image/png")
        self.assertEqual(media_store.media_content_type("abc.bin"), "application/octet-stream")

    def test_delete_media_for_track_removes_only_that_tracks_files(self):
        url_a1 = media_store.save_media(3, "image/png", b"a1")
        url_a2 = media_store.save_media(3, "video/mp4", b"a2")
        url_b = media_store.save_media(35, "image/png", b"b")  # prefix "3" is a substring, must not match

        removed = media_store.delete_media_for_track(3)

        self.assertEqual(removed, 2)
        self.assertIsNone(media_store.read_media(url_a1.rsplit("/", 1)[-1]))
        self.assertIsNone(media_store.read_media(url_a2.rsplit("/", 1)[-1]))
        self.assertIsNotNone(media_store.read_media(url_b.rsplit("/", 1)[-1]))

    def test_delete_media_for_track_is_a_noop_when_nothing_to_delete(self):
        self.assertEqual(media_store.delete_media_for_track(999), 0)


if __name__ == "__main__":
    unittest.main()
