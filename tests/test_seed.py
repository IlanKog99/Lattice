import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lattice import seed, store


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "grid.dat"
        self.src = self.tmp / "table.txt"
        self.src.write_text("Col A: || Col B: ||\n------||------||\nrow-1 || value-1 ||\n", encoding="utf-8")
        patcher = mock.patch.object(store, "DATA_FILE", self.data)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_refuses_existing_store_without_force(self):
        self.data.write_bytes(b"existing")
        self.assertEqual(seed.main([str(self.src)]), 1)
        self.assertEqual(self.data.read_bytes(), b"existing")

    def test_force_overwrites_existing_store(self):
        self.data.write_bytes(b"existing")
        self.assertEqual(seed.main([str(self.src), "--force"]), 0)
        self.assertEqual(store.load().rows[0].cells, ["row-1", "value-1"])


    def test_save_error_returns_1(self):
        self.data.mkdir()
        self.assertEqual(seed.main([str(self.src), "--force"]), 1)
        self.assertTrue(self.data.is_dir())

if __name__ == "__main__":
    unittest.main()
