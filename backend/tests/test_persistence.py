import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.persistence.device_store import default_data_dir


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


if __name__ == "__main__":
    unittest.main()
