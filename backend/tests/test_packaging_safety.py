import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class PackagingSafetyContractTests(unittest.TestCase):
    def test_clean_install_stages_before_touching_application_prefix(self):
        source = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

        dependency_install = source.index('pip install -r "$STAGE_DIR/backend/requirements.txt"')
        activate = source.index('mv "$STAGE_DIR" "$PREFIX"')
        unit_install = source.index('install -m 0644 "$PREFIX/systemd/auralan.service" "$UNIT_PATH"')

        self.assertLess(dependency_install, activate)
        self.assertLess(activate, unit_install)
        self.assertIn('rollback_install', source)
        self.assertIn('systemctl disable "$UNIT_NAME"', source)
        self.assertIn('rm -rf "$PREFIX"', source)

    def test_git_sources_are_refused_when_dirty_before_archive(self):
        for script_name in ("install.sh", "upgrade.sh"):
            source = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
            dirty_check = source.index('status --porcelain --untracked-files=normal')
            archive = source.index('archive --format=tar HEAD')
            self.assertLess(dirty_check, archive, script_name)

    def test_upgrade_diagnoses_interrupted_markers_before_fresh_install_check(self):
        source = (ROOT / "scripts" / "upgrade.sh").read_text(encoding="utf-8")
        marker_check = source.index('interrupted AuraLAN upgrade markers exist')
        prefix_check = source.index('$PREFIX does not exist; use scripts/install.sh')
        self.assertLess(marker_check, prefix_check)

    def test_upgrade_checks_copied_state_before_switching_code(self):
        source = (ROOT / "scripts" / "upgrade.sh").read_text(encoding="utf-8")
        backup = source.index('Creating consistent SQLite backup')
        readiness = source.index('Checking staged code against a copy of current AuraLAN state')
        switch = source.index('Switching application code')

        self.assertLess(backup, readiness)
        self.assertLess(readiness, switch)
        self.assertIn('"$READINESS_DIR/auralan.db"', source)

    def test_upgrade_rollback_restores_application_unit_and_database(self):
        source = (ROOT / "scripts" / "upgrade.sh").read_text(encoding="utf-8")
        rollback_start = source.index('rollback() {')
        rollback_end = source.index('cleanup_stage() {')
        rollback = source[rollback_start:rollback_end]

        self.assertIn('mv "$ROLLBACK_DIR" "$PREFIX"', rollback)
        self.assertIn('cp -f "$UNIT_BACKUP" "$UNIT_PATH"', rollback)
        self.assertIn('restore_database', rollback)


if __name__ == "__main__":
    unittest.main()
