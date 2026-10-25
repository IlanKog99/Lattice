import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lattice import codec, store
from lattice.models import Column, Grid
from tests import dummy_grid, foreign_blob


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "grid.dat"
        patcher = mock.patch.object(store, "DATA_FILE", self.data)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_file_is_empty_grid(self):
        self.assertEqual(store.load().to_dict(), Grid().to_dict())

    def test_save_writes_sealed_and_reloads(self):
        store.save(dummy_grid())
        raw = self.data.read_text(encoding="ascii")
        self.assertTrue(raw.startswith("DP1:"))
        self.assertNotIn("value-1", raw)
        self.assertEqual(store.load().to_dict(), dummy_grid().to_dict())
        self.assertFalse(self.data.with_name("grid.dat.tmp").exists())

    def test_legacy_file_migrates_on_load(self):
        legacy = codec.pack(json.dumps(dummy_grid().to_dict()))
        self.data.write_text(legacy, encoding="ascii")
        self.assertEqual(store.load().to_dict(), dummy_grid().to_dict())
        self.assertTrue(self.data.read_text(encoding="ascii").startswith("DP1:"))
        self.assertEqual(store.load().to_dict(), dummy_grid().to_dict())

    def test_foreign_sealed_file_raises_and_is_untouched(self):
        foreign = foreign_blob(dummy_grid())
        self.data.write_text(foreign, encoding="ascii")
        with self.assertRaises(store.ForeignStoreError):
            store.load()
        self.assertEqual(self.data.read_text(encoding="ascii"), foreign)

    def test_garbage_or_wrong_shape_raises_value_error_and_is_untouched(self):
        for blob in ("hello world", codec.pack("[1]")):
            with self.subTest(blob=blob):
                self.data.write_text(blob, encoding="ascii")
                with self.assertRaises(ValueError):
                    store.load()
                self.assertEqual(self.data.read_text(encoding="ascii"), blob)

    def test_failed_verification_keeps_old_file(self):
        store.save(dummy_grid())
        before = self.data.read_text(encoding="ascii")
        with mock.patch.object(codec, "open_blob", return_value="different"):
            with self.assertRaises(ValueError):
                store.save(Grid([Column("label")], []))
        self.assertEqual(self.data.read_text(encoding="ascii"), before)
        self.assertFalse(self.data.with_name("grid.dat.tmp").exists())

    def test_migration_save_failure_still_loads(self):
        legacy = codec.pack(json.dumps(dummy_grid().to_dict()))
        self.data.write_text(legacy, encoding="ascii")
        with mock.patch.object(store.os, "replace", side_effect=PermissionError("locked")):
            grid = store.load()
        self.assertEqual(grid.to_dict(), dummy_grid().to_dict())
        self.assertEqual(self.data.read_text(encoding="ascii"), legacy)
        self.assertFalse(self.data.with_name("grid.dat.tmp").exists())

    def test_bad_types_raise_value_error_and_is_untouched(self):
        bad = {"columns": [{"name": "label"}, {"name": "field-a"}], "rows": [{"cells": ["row-1", 7]}]}
        legacy = codec.pack(json.dumps(bad))
        self.data.write_text(legacy, encoding="ascii")
        with self.assertRaises(ValueError):
            store.load()
        self.assertEqual(self.data.read_text(encoding="ascii"), legacy)

    def test_migration_seal_valueerror_still_loads(self):
        legacy = codec.pack(json.dumps(dummy_grid().to_dict()))
        self.data.write_text(legacy, encoding="ascii")
        with mock.patch.object(codec, "seal", side_effect=ValueError("seal failed")):
            grid = store.load()
        self.assertEqual(grid.to_dict(), dummy_grid().to_dict())
        self.assertEqual(self.data.read_text(encoding="ascii"), legacy)

    def test_deeply_nested_json_raises_value_error(self):
        legacy = codec.pack("[" * 100000)
        self.data.write_text(legacy, encoding="ascii")
        with self.assertRaisesRegex(ValueError, "unreadable data file"):
            store.load()
        self.assertEqual(self.data.read_text(encoding="ascii"), legacy)


if __name__ == "__main__":
    unittest.main()
