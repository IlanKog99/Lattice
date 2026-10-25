import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lattice import codec, dpapi, store, vault_io
from tests import dummy_grid, foreign_blob


class VaultIOTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "out.lattice"

    def test_round_trip(self):
        vault_io.export_grid(dummy_grid(), self.path, "dummypass")
        raw = self.path.read_text(encoding="ascii")
        self.assertTrue(raw.startswith("LX1:"))
        self.assertNotIn("value-1", raw)
        self.assertTrue(vault_io.needs_passphrase(self.path))
        self.assertEqual(vault_io.import_grid(self.path, "dummypass").to_dict(), dummy_grid().to_dict())
        self.assertFalse(any(p.suffix == ".tmp" for p in self.tmp.iterdir()))

    def test_wrong_passphrase(self):
        vault_io.export_grid(dummy_grid(), self.path, "dummypass")
        with self.assertRaisesRegex(vault_io.VaultIOError, "Wrong passphrase"):
            vault_io.import_grid(self.path, "otherpass")

    def test_tampered_file(self):
        vault_io.export_grid(dummy_grid(), self.path, "dummypass")
        raw = self.path.read_text(encoding="ascii")
        flipped = raw[:-3] + ("0" if raw[-3] != "0" else "1") + raw[-2:]
        self.path.write_text(flipped, encoding="ascii")
        with self.assertRaisesRegex(vault_io.VaultIOError, "Wrong passphrase"):
            vault_io.import_grid(self.path, "dummypass")

    def test_missing_passphrase(self):
        vault_io.export_grid(dummy_grid(), self.path, "dummypass")
        with self.assertRaises(vault_io.VaultIOError):
            vault_io.import_grid(self.path, None)

    def test_empty_passphrase_refused_on_export(self):
        with self.assertRaises(vault_io.VaultIOError):
            vault_io.export_grid(dummy_grid(), self.path, "")
        self.assertFalse(self.path.exists())

    def test_legacy_file_imports_without_passphrase(self):
        self.path.write_text(codec.pack(json.dumps(dummy_grid().to_dict())), encoding="ascii")
        self.assertFalse(vault_io.needs_passphrase(self.path))
        self.assertEqual(vault_io.import_grid(self.path).to_dict(), dummy_grid().to_dict())

    def test_bad_types_refused(self):
        for bad in (
            {"columns": [{"name": "label"}, {"name": "field-a"}], "rows": [{"cells": ["row-1", 7]}]},
            {"columns": [{"name": "label"}, {"name": 5}], "rows": []},
            {"columns": [{"name": "label", "hidden": "no"}], "rows": []},
            {"columns": [{"name": "label"}], "rows": [{"cells": "row-1"}]},
            {"columns": [{"name": "label"}], "rows": [{"cells": ["row-1"], "hidden": 0}]},
            {"columns": [{"name": "label"}], "rows": [{"cells": [{"prefix": "", "formula": 5, "suffix": ""}]}]},
            {"columns": [{"name": "label"}], "rows": [{"cells": [{"prefix": "x"}]}]},
            {"columns": [{"name": "label"}], "rows": [{"cells": [{"formula": "abs(INPT)"}]}]},
            {"columns": [{"name": "label"}], "rows": [{"cells": [{"formula": ""}]}]},
            {"columns": [{"name": "label"}], "rows": [{"cells": [{"formula": "INPT", "prefix": 5}]}]},
            {"columns": [{"name": "label"}], "rows": [{"cells": [{"kind": "code", "seed": 5}]}]},
            {"columns": [{"name": "label"}], "rows": [{"cells": [{"kind": "x", "formula": 5}]}]},
        ):
            with self.subTest(bad=bad):
                self.path.write_text(codec.pack(json.dumps(bad)), encoding="ascii")
                with self.assertRaisesRegex(vault_io.VaultIOError, "Not a Lattice file"):
                    vault_io.import_grid(self.path)

    def test_valid_dict_cells_load(self):
        cells = [{"prefix": "a", "formula": "INPT+1", "suffix": "b"}, {"kind": "code", "seed": "JBSWY3DPEHPK3PXP"}]
        good = {"columns": [{"name": "a"}, {"name": "b"}], "rows": [{"cells": cells}]}
        self.path.write_text(codec.pack(json.dumps(good)), encoding="ascii")
        self.assertEqual(vault_io.import_grid(self.path).rows[0].cells, cells)

    def test_export_onto_live_grid_refused(self):
        data = self.tmp / "grid.dat"
        data.write_bytes(b"live")
        with mock.patch.object(store, "DATA_FILE", data):
            for target in (data, self.tmp / "." / "GRID.DAT"):
                with self.subTest(target=target):
                    with self.assertRaisesRegex(vault_io.VaultIOError, "that is the live grid"):
                        vault_io.export_grid(dummy_grid(), target, "dummypass")
        self.assertEqual(data.read_bytes(), b"live")

    def test_samefile_error_refuses(self):
        data = self.tmp / "grid.dat"
        data.write_bytes(b"live")
        with mock.patch.object(store, "DATA_FILE", data), \
                mock.patch("lattice.vault_io.os.path.samefile", side_effect=OSError("denied")):
            with self.assertRaisesRegex(vault_io.VaultIOError, "that is the live grid"):
                vault_io.export_grid(dummy_grid(), data, "dummypass")
        self.assertEqual(data.read_bytes(), b"live")

    def test_trailing_dot_space_of_absent_live_grid_refused(self):
        with mock.patch.object(store, "DATA_FILE", self.tmp / "grid.dat"):
            for name in ("grid.dat.", "grid.dat ", "grid.dat. ."):
                with self.subTest(name=name):
                    with self.assertRaisesRegex(vault_io.VaultIOError, "that is the live grid"):
                        vault_io.export_grid(dummy_grid(), str(self.tmp / name), "dummypass")
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_stream_name_refused(self):
        with self.assertRaisesRegex(vault_io.VaultIOError, "Choose a file name to export to"):
            vault_io.export_grid(dummy_grid(), self.tmp / "out.lattice:x", "dummypass")
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_nul_export_path_refused(self):
        with self.assertRaises(vault_io.VaultIOError):
            vault_io.export_grid(dummy_grid(), str(self.tmp / "a\x00b.lattice"), "dummypass")

    def test_own_sealed_store_copy_imports(self):
        with mock.patch.object(store, "DATA_FILE", self.tmp / "grid.dat"):
            store.save(dummy_grid())
        self.path.write_bytes((self.tmp / "grid.dat").read_bytes())
        self.assertFalse(vault_io.needs_passphrase(self.path))
        self.assertEqual(vault_io.import_grid(self.path).to_dict(), dummy_grid().to_dict())

    def test_foreign_sealed_file_refused(self):
        self.path.write_text(foreign_blob(dummy_grid()), encoding="ascii")
        with self.assertRaisesRegex(vault_io.VaultIOError, "another Windows user or PC"):
            vault_io.import_grid(self.path)

    def test_corrupt_sealed_file_refused(self):
        own_garbage = "DP1:" + base64.b85encode(dpapi.protect(b"not-packed")).decode("ascii")
        for blob in ("DP1:~~~~", own_garbage):
            with self.subTest(blob=blob):
                self.path.write_text(blob, encoding="ascii")
                with self.assertRaisesRegex(vault_io.VaultIOError, "Not a Lattice file"):
                    vault_io.import_grid(self.path)

    def test_nul_path_refused(self):
        with self.assertRaises(vault_io.VaultIOError):
            vault_io.import_grid(str(self.tmp / "a\x00b.lattice"))

    def test_nul_and_directory_paths_raise_value_error(self):
        """Screens catch only ValueError: no OSError may escape for these paths."""
        self.path.write_text("x", encoding="ascii")
        nul, folder = str(self.tmp / "a\x00b.lattice"), self.tmp / "adir"
        folder.mkdir()
        calls = (
            lambda p: vault_io.needs_passphrase(p),
            lambda p: vault_io.import_grid(p, "dummypass"),
            lambda p: vault_io.export_grid(dummy_grid(), p, "dummypass"),
        )
        with mock.patch.object(store, "DATA_FILE", self.tmp / "grid.dat"):
            for path in (nul, folder):
                for call in calls:
                    with self.subTest(path=path, call=call), self.assertRaises(ValueError):
                        call(path)
        self.assertEqual(list(folder.iterdir()), [])

    def test_not_a_lattice_file(self):
        self.path.write_text("hello world", encoding="ascii")
        with self.assertRaises(vault_io.VaultIOError):
            vault_io.import_grid(self.path)

    def test_missing_path(self):
        with self.assertRaises(vault_io.VaultIOError):
            vault_io.needs_passphrase(self.tmp / "nope.lattice")

    def test_unwritable_path(self):
        with self.assertRaises(vault_io.VaultIOError):
            vault_io.export_grid(dummy_grid(), self.tmp / "no-such-dir" / "out.lattice", "dummypass")

    def test_empty_path_refused(self):
        with self.assertRaises(vault_io.VaultIOError):
            vault_io.export_grid(dummy_grid(), "", "dummypass")

    def test_replace_failure_cleans_tmp(self):
        with mock.patch("lattice.vault_io.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(vault_io.VaultIOError):
                vault_io.export_grid(dummy_grid(), self.path, "dummypass")
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_deeply_nested_legacy_json_refused(self):
        self.path.write_text(codec.pack("[" * 100000), encoding="ascii")
        with self.assertRaises(vault_io.VaultIOError):
            vault_io.import_grid(self.path)

    def test_missing_cryptography_gives_install_hint(self):
        with mock.patch.dict("sys.modules", {"cryptography.hazmat.primitives.ciphers.aead": None}):
            with self.assertRaisesRegex(vault_io.VaultIOError, "pip install"):
                vault_io.export_grid(dummy_grid(), self.path, "dummypass")


if __name__ == "__main__":
    unittest.main()
