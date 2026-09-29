import threading
import unittest
from unittest.mock import patch

from app.monitor import BackgroundMonitor, configured_interval


class BackgroundMonitorTests(unittest.TestCase):
    def test_interval_can_be_disabled_and_is_bounded(self):
        with patch.dict("os.environ", {"AURALAN_MONITOR_INTERVAL": "0"}, clear=False):
            self.assertEqual(configured_interval(), 0)
        with patch.dict("os.environ", {"AURALAN_MONITOR_INTERVAL": "1"}, clear=False):
            self.assertEqual(configured_interval(), 15)
        with patch.dict("os.environ", {"AURALAN_MONITOR_INTERVAL": "999999"}, clear=False):
            self.assertEqual(configured_interval(), 3600)
        with patch.dict("os.environ", {"AURALAN_MONITOR_INTERVAL": "not-a-number"}, clear=False):
            self.assertEqual(configured_interval(), 60)

    def test_run_once_records_success_without_exposing_snapshot_data(self):
        calls = []

        def collector(*, force=False):
            calls.append(force)
            return {"devices": [{"id": "private"}]}

        monitor = BackgroundMonitor(collector, interval_seconds=60)
        self.assertTrue(monitor.run_once())

        status = monitor.status()
        self.assertEqual(calls, [True])
        self.assertIsNotNone(status["last_attempt_at"])
        self.assertIsNotNone(status["last_success_at"])
        self.assertIsNone(status["last_error"])
        self.assertNotIn("devices", status)

    def test_run_once_executes_post_collect_hook(self):
        seen = []

        def collector(*, force=False):
            return {"devices": [{"id": "one"}]}

        def after_collect(snapshot):
            seen.append(snapshot["devices"][0]["id"])

        monitor = BackgroundMonitor(collector, interval_seconds=60, after_collect=after_collect)
        self.assertTrue(monitor.run_once())
        self.assertEqual(seen, ["one"])

    def test_run_once_contains_collector_failure(self):
        def collector(*, force=False):
            raise RuntimeError("sample failure")

        monitor = BackgroundMonitor(collector, interval_seconds=60)
        self.assertFalse(monitor.run_once())

        status = monitor.status()
        self.assertEqual(status["last_error"], "RuntimeError")
        self.assertIsNone(status["last_success_at"])

    def test_enabled_monitor_runs_without_a_browser_request(self):
        called = threading.Event()

        def collector(*, force=False):
            self.assertTrue(force)
            called.set()
            return {}

        monitor = BackgroundMonitor(collector, interval_seconds=15)
        monitor.start()
        try:
            self.assertTrue(called.wait(timeout=1))
            self.assertTrue(monitor.status()["running"])
        finally:
            monitor.stop()

        self.assertFalse(monitor.status()["running"])

    def test_disabled_monitor_does_not_start_thread(self):
        monitor = BackgroundMonitor(lambda **_: {}, interval_seconds=0)
        monitor.start()
        self.assertFalse(monitor.status()["running"])


if __name__ == "__main__":
    unittest.main()
