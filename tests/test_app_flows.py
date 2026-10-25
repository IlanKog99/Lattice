import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lattice import app as app_mod
from lattice import codec, screens, store, vault_io
from lattice.models import Column, Grid
from tests import dummy_grid, foreign_blob


class AppFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)  # debug mode makes pilot tests very slow

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "grid.dat"
        self.out = self.tmp / "out.lattice"
        for patcher in (
            mock.patch.object(store, "DATA_FILE", self.data),
            mock.patch.object(app_mod.LatticeApp, "_check_for_update", lambda self: None),
            mock.patch.object(app_mod.LatticeApp, "_whatsnew_seen", lambda self: True),
            mock.patch.object(screens, "default_export_path", lambda: str(self.out)),
            mock.patch.object(screens, "default_import_path", lambda: str(self.out)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_foreign_store_is_read_only_and_untouched(self):
        blob = foreign_blob(dummy_grid())
        self.data.write_text(blob, encoding="ascii")
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            self.assertTrue(app.read_only)
            app.persist()
            await pilot.pause()
        self.assertEqual(self.data.read_text(encoding="ascii"), blob)

    async def test_bad_typed_store_is_read_only_and_untouched(self):
        bad = {"columns": [{"name": "label"}, {"name": "field-a"}], "rows": [{"cells": ["row-1", 7]}]}
        legacy = codec.pack(json.dumps(bad))
        self.data.write_text(legacy, encoding="ascii")
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            self.assertTrue(app.read_only)
            await pilot.pause()
        self.assertEqual(self.data.read_text(encoding="ascii"), legacy)

    async def test_export_mismatched_passphrase_writes_nothing(self):
        store.save(dummy_grid())
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            app.run_command("/export")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press(*"dummypass", "enter")
            await pilot.pause()
            await pilot.press(*"otherpass", "enter")
            await pilot.pause()
        self.assertFalse(self.out.exists())

    async def test_import_replaces_grid_and_undo_restores(self):
        empty = Grid([Column("label")], [])
        store.save(empty)
        vault_io.export_grid(dummy_grid(), self.out, "dummypass")
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            app.run_command("/import")
            await pilot.pause()
            await pilot.press("enter")  # accept the prefilled path
            await pilot.pause()
            await pilot.press(*"dummypass", "enter")
            await pilot.pause()
            await pilot.press("left", "enter")  # No -> Yes, confirm
            await pilot.pause()
            self.assertEqual(app.grid.to_dict(), dummy_grid().to_dict())
            self.assertEqual(store.load().to_dict(), dummy_grid().to_dict())
            app.undo()
            await pilot.pause()
            self.assertEqual(app.grid.to_dict(), empty.to_dict())


class HostileBase(unittest.IsolatedAsyncioTestCase):
    """Hostile read-only / export / import checks. Dummy data only."""

    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)  # debug mode makes pilot tests very slow

    def setUp(self):
        AppFlowTests.setUp(self)
        self.sub = self.tmp / "adir"
        self.sub.mkdir()

    def set_default(self, value):
        for name in ("default_export_path", "default_import_path"):
            p = mock.patch.object(screens, name, lambda v=value: v)
            p.start()
            self.addCleanup(p.stop)

    def foreign(self):
        self.blob = foreign_blob(dummy_grid())
        self.data.write_text(self.blob, encoding="ascii")

    def assert_dat(self):
        self.assertEqual(self.data.read_text(encoding="ascii"), self.blob)

    def status(self, app):
        return str(app.query_one("#status").content)

    def spy(self, app):
        """Record status messages: the 2.6 s reset timer can fire in a slow run."""
        seen, real = [], app.set_status
        app.set_status = lambda message=None: (seen.append(message or ""), real(message))[1]
        return seen

    async def load_dummy(self, app, pilot):
        """Put a grid in memory while the store stays read-only."""
        app.grid = dummy_grid()
        app.refresh_grid()
        await pilot.pause()


class ReadOnlyTests(HostileBase):
    async def test_ro_edit_clear_undo_write_nothing(self):
        self.foreign()
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            self.assertTrue(app.read_only)
            await self.load_dummy(app, pilot)
            await pilot.press("e")
            await pilot.pause()
            await pilot.press(*"xx", "enter")
            await pilot.pause()
            self.assertIn("xx", app.grid.rows[0].cells)  # edit really happened
            self.assert_dat()
            await pilot.press("delete")
            await pilot.pause()
            self.assertEqual(app.grid.rows[0].cells[1], "")
            self.assert_dat()
            await pilot.press("ctrl+z")
            await pilot.pause()
            self.assertEqual(app.grid.rows[0].cells[1], "xx")
            app.undo()
            await pilot.pause()
            self.assert_dat()

    async def test_ro_status_not_overwritten_by_success_text(self):
        self.foreign()
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            await self.load_dummy(app, pilot)
            await pilot.press("e")
            await pilot.pause()
            await pilot.press(*"xx", "enter")
            await pilot.pause()
            self.assertIn(app.read_only, self.status(app))

    async def test_init_permission_error_does_not_crash(self):
        with mock.patch.object(store, "load", side_effect=PermissionError("locked")):
            app = app_mod.LatticeApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertTrue(app.read_only)

    async def test_apply_import_over_foreign_saves_and_has_nothing_to_undo(self):
        self.foreign()
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            app.apply_import(dummy_grid())
            await pilot.pause()
            self.assertIsNone(app.read_only)
            self.assertNotIn("/undo", self.status(app))
            app.undo()
            await pilot.pause()
            self.assertIn("Nothing to undo", self.status(app))
            self.assertEqual(app.grid.to_dict(), dummy_grid().to_dict())
        self.assertEqual(store.load().to_dict(), dummy_grid().to_dict())

    async def test_apply_import_save_failure_changes_nothing(self):
        for exc in (OSError("disk"), ValueError("sealed store failed verification")):
            with self.subTest(exc=exc):
                self.foreign()
                app = app_mod.LatticeApp()
                async with app.run_test() as pilot:
                    seen = self.spy(app)
                    before = app.grid.to_dict()
                    with mock.patch.object(store, "save", side_effect=exc):
                        app.apply_import(dummy_grid())  # must not raise
                    await pilot.pause()
                    self.assertTrue(app.read_only, "read_only cleared though nothing saved")
                    self.assertEqual(app.grid.to_dict(), before)
                    self.assertTrue(any("Import not saved" in m for m in seen), seen)
                self.assert_dat()

    async def test_ro_undo_writes_nothing_and_shows_message(self):
        self.foreign()
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            await self.load_dummy(app, pilot)
            app.push_undo()
            app.grid.set_cell(0, 1, "xx")
            app.undo()
            await pilot.pause()
            self.assertEqual(app.grid.to_dict(), dummy_grid().to_dict())
            self.assertIn(app.read_only, self.status(app))
        self.assert_dat()


class ExportTests(HostileBase):
    def nothing_written(self):
        self.assertFalse(self.out.exists())
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir() if p.is_file()), ["grid.dat"])

    async def _run(self, keys_per_step):
        store.save(dummy_grid())
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            app.run_command("/export")
            await pilot.pause()
            for keys in keys_per_step:
                await pilot.press(*keys)
                await pilot.pause()
            await pilot.pause()
            self.assertEqual(app.grid.to_dict(), dummy_grid().to_dict())
            self.assertNotIsInstance(app.screen, screens.ExportScreen)

    async def test_export_writes_passphrase_file(self):
        (self.tmp / "a[").mkdir()  # typed "a[/x]y" = dir "a[" + file "x]y": valid on Windows, markup in status
        target = self.tmp / "a[" / "x]y.lattice"
        self.set_default(f"{self.tmp}/a[/x]y.lattice")
        store.save(dummy_grid())
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            seen = self.spy(app)
            app.run_command("/export")
            await pilot.pause()
            await pilot.press("enter")  # accept the prefilled path
            await pilot.pause()
            await pilot.press(*"dummypass", "enter")
            await pilot.pause()
            await pilot.press(*"dummypass", "enter")
            await pilot.pause()
            self.assertTrue(any(m.startswith("Exported") for m in seen), seen)
        self.assertTrue(vault_io.needs_passphrase(target))
        self.assertEqual(vault_io.import_grid(target, "dummypass").to_dict(), dummy_grid().to_dict())

    async def test_export_empty_path(self):
        self.set_default("")
        await self._run([["enter"]])
        self.nothing_written()

    async def test_export_directory_path(self):
        self.set_default(str(self.sub))
        await self._run([["enter"], [*"dummypass", "enter"], [*"dummypass", "enter"]])
        self.assertEqual(list(self.sub.iterdir()), [])
        self.assertFalse(self.out.exists())

    async def test_export_esc_at_each_step(self):
        await self._run([["escape"]])
        self.nothing_written()
        await self._run([["enter"], ["escape"]])
        self.nothing_written()
        await self._run([["enter"], [*"dummypass", "enter"], ["escape"]])
        self.nothing_written()


class ImportTests(HostileBase):
    def make_vault(self):
        vault_io.export_grid(dummy_grid(), self.out, "dummypass")

    async def _run(self, keys_per_step, expect_import=False):
        empty = Grid([Column("label")], [])
        store.save(empty)
        before = self.data.read_text(encoding="ascii")
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            app.run_command("/import")
            await pilot.pause()
            for keys in keys_per_step:
                await pilot.press(*keys)
                await pilot.pause()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, (screens.ImportScreen, screens.ConfirmScreen))
            if expect_import:
                self.assertEqual(app.grid.to_dict(), dummy_grid().to_dict())
            else:
                self.assertEqual(app.grid.to_dict(), empty.to_dict())
                self.assertEqual(self.data.read_text(encoding="ascii"), before)

    async def test_import_nonexistent_file(self):
        self.set_default(f"{self.tmp}/nope[/x].lattice")  # markup in the error must not crash
        await self._run([["enter"]])

    async def test_import_legacy_file_has_no_passphrase_step(self):
        self.out.write_text(codec.pack(json.dumps(dummy_grid().to_dict())), encoding="ascii")
        self.assertFalse(vault_io.needs_passphrase(self.out))
        await self._run([["enter"], ["left", "enter"]], expect_import=True)
        self.assertEqual(store.load().to_dict(), dummy_grid().to_dict())

    async def test_import_bad_types_changes_nothing(self):
        bad = {"columns": [{"name": "label"}, {"name": "field-a"}], "rows": [{"cells": ["row-1", 7]}]}
        self.out.write_text(codec.pack(json.dumps(bad)), encoding="ascii")
        await self._run([["enter"]])

    async def test_import_esc_at_each_step_and_no(self):
        self.make_vault()
        await self._run([["escape"]])
        await self._run([["enter"], ["escape"]])
        await self._run([["enter"], [*"dummypass", "enter"], ["escape"]])
        await self._run([["enter"], [*"dummypass", "enter"], ["enter"]])  # default No


class Fix2Tests(HostileBase):
    """review-7: save errors, read-only export/import, markup in status."""

    async def test_save_error_on_undo_shows_not_saved(self):
        for exc in (OSError("disk full"), ValueError("sealed store failed verification")):
            store.save(dummy_grid())
            app = app_mod.LatticeApp()
            async with app.run_test() as pilot:
                seen = self.spy(app)
                app.push_undo()
                with mock.patch.object(store, "save", side_effect=exc):
                    app.undo()
                    await pilot.pause()
                self.assertTrue(any("Not saved" in m for m in seen), seen)
                self.assertFalse(any("Undid" in m for m in seen), seen)

    async def test_export_refused_when_read_only(self):
        self.foreign()
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            seen = self.spy(app)
            app.run_command("/export")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, screens.ExportScreen)
            self.assertTrue(any("Nothing to export" in m for m in seen), seen)
        self.assertFalse(self.out.exists())
        self.assert_dat()

    async def test_import_over_read_only_question_says_cannot_undo(self):
        self.foreign()
        vault_io.export_grid(dummy_grid(), self.out, "dummypass")
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            app.run_command("/import")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press(*"dummypass", "enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, screens.ConfirmScreen)
            self.assertIn("grid.dat", app.screen._question)
            self.assertIn("can't be undone", app.screen._question)
            await pilot.press("enter")  # No
            await pilot.pause()
        self.assert_dat()


if __name__ == "__main__":
    unittest.main()
