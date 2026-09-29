import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.persistence.device_store import DeviceStore, default_data_dir


class DefaultDataDirTests(unittest.TestCase):
    def test_explicit_data_dir_wins(self):
        with patch.dict(os.environ, {"AURALAN_DATA_DIR": "/tmp/auralan-state", "XDG_STATE_HOME": "/tmp/xdg"}, clear=True):
            self.assertEqual(default_data_dir(), Path("/tmp/auralan-state"))

    def test_xdg_state_home_is_used_for_user_processes(self):
        with patch.dict(os.environ, {"XDG_STATE_HOME": "/tmp/xdg-state"}, clear=True):
            self.assertEqual(default_data_dir(), Path("/tmp/xdg-state/auralan"))

    def test_home_state_directory_is_fallback(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "home", return_value=Path("/tmp/example-home")):
            self.assertEqual(default_data_dir(), Path("/tmp/example-home/.local/state/auralan"))

    def test_inventory_metadata_round_trips_and_partial_updates_preserve_fields(self):
        with TemporaryDirectory() as temp_dir:
            device_store = DeviceStore(Path(temp_dir))
            saved = device_store.update_metadata(
                "001122334455",
                alias="Office printer",
                category_override="printer",
                note="Upstairs",
                favorite=True,
            )
            self.assertEqual(saved["note"], "Upstairs")
            self.assertTrue(saved["favorite"])

            enriched = device_store.enrich(["001122334455"])["001122334455"]
            self.assertEqual(enriched["alias"], "Office printer")
            self.assertEqual(enriched["category_override"], "printer")
            self.assertEqual(enriched["note"], "Upstairs")
            self.assertEqual(enriched["favorite"], 1)
            self.assertIsNotNone(enriched["first_seen_at"])
            self.assertIsNotNone(enriched["last_seen_at"])

            device_store.update_metadata("001122334455", alias="Printer")
            preserved = device_store.enrich(["001122334455"])["001122334455"]
            self.assertEqual(preserved["alias"], "Printer")
            self.assertEqual(preserved["note"], "Upstairs")
            self.assertEqual(preserved["favorite"], 1)


if __name__ == "__main__":
    unittest.main()
