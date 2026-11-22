"""Update flow: launch only checks, the popup offers, /update installs."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lattice import app as app_mod
from lattice import screens, store, updater

UPDATE = {
    "version": "99.0.0",
    "notes": "• dummy change [not markup]",
    "url": updater.release_page("99.0.0"),
    "zipball_url": "https://example.invalid/zip",
}


def _never(*_a, **_k):
    raise AssertionError("must not download or install without /update")


class CheckTests(unittest.TestCase):
    def test_states(self):
        cases = [
            (None, "failed"),
            ({"tag_name": "v0.0.1", "zipball_url": "z", "body": ""}, "current"),
            ({"tag_name": "v99.0.0", "zipball_url": "z", "body": "* item"}, "available"),
        ]
        for release, expected in cases:
            with mock.patch.object(updater, "fetch_latest_release", return_value=release):
                state, update = updater.check_for_update()
            self.assertEqual(state, expected)
            self.assertEqual(update is not None, expected == "available")
        self.assertEqual(update["version"], "99.0.0")
        self.assertEqual(update["notes"], "• item")
        self.assertTrue(update["url"].startswith("https://github.com/"))


class UpdateFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.check = mock.Mock(return_value=("available", UPDATE))
        self.apply = mock.Mock(return_value=True)
        for patcher in (
            mock.patch.object(store, "DATA_FILE", tmp / "grid.dat"),
            mock.patch.object(app_mod.LatticeApp, "_whatsnew_seen", lambda self: True),
            mock.patch.object(updater, "STAGE_DELAY", 0),
            mock.patch.object(updater, "PROJECT_ROOT", tmp),
            mock.patch.object(updater, "prune_stale", lambda *a: None),
            mock.patch.object(updater, "check_for_update", self.check),
            mock.patch.object(updater, "apply_update", self.apply),
            mock.patch.object(updater, "download_zip", _never),
            mock.patch.object(updater, "overlay", _never),
            mock.patch.object(updater, "pip_install", _never),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def _settle(self, app, pilot):
        await app.workers.wait_for_complete()
        await pilot.pause()

    def _note(self, app):
        indicator = app.query_one("#update")
        return str(indicator.render()) if indicator.display else ""

    async def test_launch_offers_without_installing(self):
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            await self._settle(app, pilot)
            self.assertIsInstance(app.screen, screens.UpdateScreen)
            self.apply.assert_not_called()

    async def test_up_to_date_launch_is_silent(self):
        self.check.return_value = ("current", None)
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            await self._settle(app, pilot)
            self.assertNotIsInstance(app.screen, screens.UpdateScreen)
            self.assertEqual(self._note(app), "")

    async def test_remind_later_sets_note_and_reminds_daily(self):
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            await self._settle(app, pilot)
            await pilot.press("enter")  # default focus: Remind me later
            await pilot.pause()
            self.assertNotIsInstance(app.screen, screens.UpdateScreen)
            self.assertIn("run /update", self._note(app))
            app._daily_update_check()
            await self._settle(app, pilot)
            self.assertIsInstance(app.screen, screens.UpdateScreen)
            self.apply.assert_not_called()

    async def test_ignore_stays_quiet_until_next_launch(self):
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            await self._settle(app, pilot)
            await pilot.press("right", "enter")  # Ignore
            await pilot.pause()
            self.assertEqual(self._note(app), "")
            app._daily_update_check()
            await self._settle(app, pilot)
            self.assertNotIsInstance(app.screen, screens.UpdateScreen)
            self.assertEqual(self.check.call_count, 1)

    async def test_update_installs_and_relaunches(self):
        self.check.return_value = ("current", None)
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            await self._settle(app, pilot)
            self.check.return_value = ("available", UPDATE)
            app.run_command("/update")
            for _ in range(100):  # the relaunch exits the app, cancelling the worker
                if app.restart_requested:
                    break
                await asyncio.sleep(0.05)
        self.apply.assert_called_once()
        self.assertTrue(app.restart_requested)

    async def test_failed_install_does_not_relaunch(self):
        self.check.return_value = ("current", None)
        self.apply.return_value = False
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            await self._settle(app, pilot)
            self.check.return_value = ("available", UPDATE)
            app.run_command("/update")
            await self._settle(app, pilot)
            self.assertIn("update failed", self._note(app))
            self.assertFalse(app.restart_requested)
            self.assertFalse(app._update_busy)

    async def test_update_when_current_does_nothing(self):
        self.check.return_value = ("current", None)
        app = app_mod.LatticeApp()
        async with app.run_test() as pilot:
            await self._settle(app, pilot)
            app.run_command("/update")
            await self._settle(app, pilot)
            self.assertIn("up to date", self._note(app))
        self.apply.assert_not_called()
        self.assertFalse(app.restart_requested)


if __name__ == "__main__":
    unittest.main()
