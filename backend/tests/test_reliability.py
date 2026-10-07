import concurrent.futures
import sqlite3
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException

from app.discovery.command import CommandResult
from app.discovery.network import dnsmasq, networkmanager
from app.main import _after_background_snapshot, activity_status, device_presence_history, forget_remembered_device, health, home_assistant_status, network_history_status, status, update_device_metadata
from app.models import DeviceMetadataUpdate
from app.persistence.device_store import DeviceStore, SCHEMA_VERSION
from app.services import system


class HealthReadinessTests(unittest.TestCase):
    def test_health_checks_local_state_readiness(self):
        with patch("app.main.store") as store_factory:
            store_factory.return_value.readiness_check.return_value = {"ready": True, "schema_version": 2}
            result = health()

        store_factory.return_value.readiness_check.assert_called_once_with()
        self.assertTrue(result["ok"])

    def test_health_reports_state_failure_as_unavailable(self):
        with patch("app.main.store") as store_factory:
            store_factory.return_value.readiness_check.side_effect = sqlite3.DatabaseError("broken")

            with self.assertRaises(HTTPException) as raised:
                health()

        self.assertEqual(raised.exception.status_code, 503)


class StatusMetadataTests(unittest.TestCase):
    def test_status_includes_runtime_version_metadata(self):
        snapshot = {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "system": {"state": "healthy", "title": "Healthy", "summary": "", "attention_count": 0},
            "host": {"name": "test", "uptime": "1m", "load": "0.00"},
            "network": {"access_point": {"available": False}, "uplink": {}, "dhcp": {}, "interfaces": [], "routes": []},
            "devices": [],
            "services": {"items": []},
            "activity": [],
            "errors": [],
        }
        with (
            patch("app.main.system_snapshot", return_value=snapshot),
            patch("app.main.brand", return_value={"version": "9.8.7-test", "apiVersion": "v1"}),
            patch("app.main._notification_status", return_value={"configured": False}),
            patch("app.main._activity_status", return_value=[]),
            patch("app.main.background_monitor") as monitor,
        ):
            monitor.status.return_value = {"enabled": True, "interval_seconds": 60, "running": True}
            result = status()

        self.assertEqual(result["version"], "9.8.7-test")
        self.assertEqual(result["api_version"], "v1")


class HomeAssistantReliabilityTests(unittest.TestCase):
    def test_home_assistant_endpoint_uses_aggregate_snapshot_only(self):
        snapshot = {
            "generated_at": "2026-09-29T19:00:00+02:00",
            "system": {"state": "healthy", "attention_count": 0},
            "devices": [],
            "services": {"items": []},
            "errors": [],
        }
        with (
            patch("app.main.system_snapshot", return_value=snapshot),
            patch("app.main.brand", return_value={"version": "9.8.7-test", "apiVersion": "v1"}),
            patch("app.main._notification_status", return_value={"configured": False, "pending_events": 0}),
            patch("app.main.wake_config") as wake,
            patch("app.main.background_monitor") as monitor,
        ):
            wake.return_value.enabled = False
            monitor.status.return_value = {"running": True, "last_success_at": 123}
            result = home_assistant_status()

        self.assertEqual(result["version"], "9.8.7-test")
        self.assertEqual(result["api_version"], "v1")
        self.assertEqual(result["devices_total"], 0)
        self.assertTrue(result["monitor_running"])
        self.assertFalse(result["webhook_configured"])
        self.assertFalse(result["wake_on_lan_enabled"])


class BackgroundPostProcessingReliabilityTests(unittest.TestCase):
    def test_history_storage_failure_does_not_block_existing_background_work(self):
        snapshot = {"devices": [{"id": "fixture"}]}
        with (
            patch("app.main.store") as store_factory,
            patch("app.main.webhook_notifier") as notifier,
        ):
            store_factory.return_value.record_network_snapshot.side_effect = sqlite3.DatabaseError("history unavailable")
            _after_background_snapshot(snapshot)

        store_factory.return_value.record_network_snapshot.assert_called_once_with(snapshot)
        store_factory.return_value.record_presence_transitions.assert_called_once_with(snapshot["devices"])
        store_factory.return_value.record_watch_transitions.assert_called_once_with(snapshot["devices"])
        notifier.dispatch_pending.assert_called_once_with()


class NetworkHistoryReliabilityTests(unittest.TestCase):
    def test_history_endpoint_uses_bounded_store_query(self):
        history = {
            "bucket_seconds": 900,
            "retention_days": 30,
            "window_hours": 48,
            "items": [{"bucket_start": 100, "updated_at": 100}],
        }
        with patch("app.main.store") as store_factory:
            store_factory.return_value.network_history.return_value = history
            result = network_history_status(48)

        store_factory.return_value.network_history.assert_called_once_with(48)
        self.assertEqual(result, history)

    def test_history_endpoint_degrades_to_empty_history_on_storage_failure(self):
        with patch("app.main.store") as store_factory:
            store_factory.return_value.network_history.side_effect = sqlite3.DatabaseError("broken")
            result = network_history_status(24)

        self.assertEqual(result["window_hours"], 24)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["bucket_seconds"], 900)
        self.assertEqual(result["retention_days"], 30)


class ActivityReliabilityTests(unittest.TestCase):
    def test_status_activity_reader_bypasses_cached_snapshot_history(self):
        snapshot = {"activity": [{"id": 1, "event_type": "device_first_seen"}]}
        with patch("app.main.store") as store_factory:
            store_factory.return_value.recent_events.return_value = [{"id": 2, "event_type": "baseline_captured"}]
            from app.main import _activity_status
            result = _activity_status(snapshot, 50)

        store_factory.return_value.recent_events.assert_called_once_with(50)
        self.assertEqual(result[0]["id"], 2)

    def test_activity_endpoint_uses_requested_history_limit(self):
        with patch("app.main.store") as store_factory:
            store_factory.return_value.recent_events.return_value = [{"id": 1}]
            result = activity_status(37)

        store_factory.return_value.recent_events.assert_called_once_with(37)
        self.assertEqual(result, {"items": [{"id": 1}]})

    def test_activity_endpoint_reports_storage_failure(self):
        with patch("app.main.store") as store_factory:
            store_factory.return_value.recent_events.side_effect = sqlite3.DatabaseError("broken")

            with self.assertRaises(HTTPException) as raised:
                activity_status(50)

        self.assertEqual(raised.exception.status_code, 503)


class PresenceHistoryReliabilityTests(unittest.TestCase):
    def test_presence_endpoint_returns_bounded_device_history(self):
        current = {"id": "sample-device"}
        history = [
            {
                "id": 1,
                "device_id": "sample-device",
                "event_type": "device_not_seen",
                "display_name": "Sample",
                "created_at": 100,
            }
        ]
        with (
            patch("app.main.system_snapshot", return_value={"devices": [current]}),
            patch("app.main.store") as store_factory,
        ):
            store_factory.return_value.presence_history.return_value = history
            result = device_presence_history("sample-device", 37)

        store_factory.return_value.presence_history.assert_called_once_with("sample-device", 37)
        self.assertEqual(result, {"device_id": "sample-device", "items": history})

    def test_presence_endpoint_rejects_unknown_device(self):
        with patch("app.main.system_snapshot", return_value={"devices": []}):
            with self.assertRaises(HTTPException) as raised:
                device_presence_history("missing-device", 50)

        self.assertEqual(raised.exception.status_code, 404)

    def test_presence_endpoint_reports_storage_failure(self):
        current = {"id": "sample-device"}
        with (
            patch("app.main.system_snapshot", return_value={"devices": [current]}),
            patch("app.main.store") as store_factory,
        ):
            store_factory.return_value.presence_history.side_effect = sqlite3.DatabaseError("broken")
            with self.assertRaises(HTTPException) as raised:
                device_presence_history("sample-device", 50)

        self.assertEqual(raised.exception.status_code, 503)


class SnapshotReliabilityTests(unittest.TestCase):
    def setUp(self):
        with system._cache_lock:
            system._cache = None

    def tearDown(self):
        with system._cache_lock:
            system._cache = None

    def test_concurrent_cache_miss_runs_one_discovery_pass(self):
        calls = 0
        calls_lock = threading.Lock()
        started = threading.Event()
        release = threading.Event()

        def collect():
            nonlocal calls
            with calls_lock:
                calls += 1
            started.set()
            release.wait(timeout=1)
            return {"sequence": calls}

        with patch.object(system, "_collect", side_effect=collect):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(system.system_snapshot)
                self.assertTrue(started.wait(timeout=1))
                second = executor.submit(system.system_snapshot)
                time.sleep(0.05)
                release.set()
                first_result = first.result(timeout=1)
                second_result = second.result(timeout=1)

        self.assertEqual(calls, 1)
        self.assertIs(first_result, second_result)

    def test_cache_age_starts_after_slow_collection_finishes(self):
        calls = 0

        def collect():
            nonlocal calls
            calls += 1
            time.sleep(0.06)
            return {"sequence": calls}

        with (
            patch.object(system, "_collect", side_effect=collect),
            patch.object(system, "CACHE_TTL_SECONDS", 0.03),
        ):
            first = system.system_snapshot()
            second = system.system_snapshot()

        self.assertEqual(calls, 1)
        self.assertIs(first, second)


class PersistenceReliabilityTests(unittest.TestCase):
    def test_replaced_database_is_bootstrapped_again(self):
        with TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory))
            store.update_metadata("sample-device", alias="Sample device")
            store.path.unlink()

            data = store.enrich(["sample-device"])

            self.assertIn("first_seen_at", data["sample-device"])
            connection = sqlite3.connect(store.path)
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                connection.close()

        self.assertEqual(version, SCHEMA_VERSION)
        self.assertTrue(
            {"schema_migrations", "device_metadata", "device_presence", "device_identity_cache"}.issubset(tables)
        )

    def test_device_metadata_endpoint_normalizes_location_and_tags(self):
        current = {"id": "sample-device"}
        refreshed = {
            "id": "sample-device",
            "display_name": "Sample",
            "ip": "192.0.2.2",
            "mac": "00:11:22:33:44:55",
            "metadata": {
                "alias": None,
                "category_override": None,
                "note": None,
                "favorite": False,
                "location": "Office",
                "tags": ["Lab", "critical"],
            },
        }
        metadata_store = unittest.mock.Mock()

        with (
            patch("app.main.system_snapshot", side_effect=[
                {"devices": [current]},
                {"devices": [refreshed]},
            ]),
            patch("app.main.store", return_value=metadata_store),
        ):
            result = update_device_metadata(
                "sample-device",
                DeviceMetadataUpdate(
                    location=" Office ",
                    tags=[" Lab ", "lab", "critical", ""],
                ),
            )

        metadata_store.update_metadata.assert_called_once_with(
            "sample-device",
            location="Office",
            tags=["Lab", "critical"],
        )
        self.assertEqual(result["metadata"]["location"], "Office")
        self.assertEqual(result["metadata"]["tags"], ["Lab", "critical"])

    def test_sqlite_write_failure_becomes_service_unavailable(self):
        current = {"id": "sample-device"}
        broken_store = unittest.mock.Mock()
        broken_store.update_metadata.side_effect = sqlite3.OperationalError("database is locked")

        with (
            patch("app.main.system_snapshot", return_value={"devices": [current]}),
            patch("app.main.store", return_value=broken_store),
        ):
            with self.assertRaises(HTTPException) as raised:
                update_device_metadata(
                    "sample-device",
                    DeviceMetadataUpdate(alias="Sample device"),
                )

        self.assertEqual(raised.exception.status_code, 503)


class ForgetDeviceReliabilityTests(unittest.TestCase):
    def test_forget_requires_a_remembered_not_current_device(self):
        live = {"id": "live-device", "state": "online"}
        with patch("app.main.system_snapshot", return_value={"devices": [live]}):
            with self.assertRaises(HTTPException) as raised:
                forget_remembered_device("live-device")

        self.assertEqual(raised.exception.status_code, 409)

    def test_forget_removes_remembered_device_and_refreshes_snapshot(self):
        remembered = {"id": "remembered-device", "state": "known"}
        metadata_store = unittest.mock.Mock()
        metadata_store.forget_device.return_value = True

        with (
            patch(
                "app.main.system_snapshot",
                side_effect=[
                    {"devices": [remembered]},
                    {"devices": []},
                ],
            ) as snapshot,
            patch("app.main.store", return_value=metadata_store),
        ):
            result = forget_remembered_device("remembered-device")

        metadata_store.forget_device.assert_called_once_with("remembered-device")
        self.assertEqual(snapshot.call_args_list[-1].kwargs, {"force": True})
        self.assertEqual(
            result,
            {"forgotten": True, "device_id": "remembered-device"},
        )

    def test_forget_reports_storage_failure(self):
        remembered = {"id": "remembered-device", "state": "known"}
        metadata_store = unittest.mock.Mock()
        metadata_store.forget_device.side_effect = sqlite3.OperationalError("locked")

        with (
            patch("app.main.system_snapshot", return_value={"devices": [remembered]}),
            patch("app.main.store", return_value=metadata_store),
        ):
            with self.assertRaises(HTTPException) as raised:
                forget_remembered_device("remembered-device")

        self.assertEqual(raised.exception.status_code, 503)


class NetworkManagerReliabilityTests(unittest.TestCase):
    def test_terse_connection_name_with_colon_is_not_split_into_fake_fields(self):
        output = r"Office\:AP:802-11-wireless:radio-ap:activated"
        with (
            patch("app.discovery.network.networkmanager.command_exists", return_value=True),
            patch(
                "app.discovery.network.networkmanager.run_command",
                return_value=CommandResult(0, output),
            ),
        ):
            rows = networkmanager.active_connections()

        self.assertEqual(
            rows,
            [{
                "name": "Office:AP",
                "type": "802-11-wireless",
                "device": "radio-ap",
                "state": "activated",
            }],
        )

    def test_terse_ssid_unescapes_colon(self):
        output = (
            r"802-11-wireless.ssid:Office\:LAN"
            "\n"
            r"802-11-wireless.channel:11"
        )
        with (
            patch("app.discovery.network.networkmanager.command_exists", return_value=True),
            patch(
                "app.discovery.network.networkmanager.run_command",
                return_value=CommandResult(0, output),
            ),
        ):
            details = networkmanager.connection_details("Office:AP")

        self.assertEqual(details["ssid"], "Office:LAN")
        self.assertEqual(details["channel"], "11")


class PortabilityReliabilityTests(unittest.TestCase):
    def test_generic_host_without_access_point_can_be_healthy(self):
        network = {"access_point": {"available": False}}
        state = system.system_state(network, [], [])
        self.assertEqual(state["state"], "healthy")
        self.assertEqual(state["attention_count"], 0)

    def test_explicit_ap_override_that_is_not_an_ap_reports_warning(self):
        with (
            patch.dict("os.environ", {"AURALAN_WIFI_INTERFACE": "radio-client"}, clear=True),
            patch("app.services.system.networkmanager.wifi_candidates", return_value=[]),
            patch("app.services.system.iw.wireless_interfaces", return_value=[]),
            patch("app.services.system.iw.interface_info", return_value={"type": "MANAGED"}),
            patch("app.services.system.iproute.routes", return_value=[]),
            patch("app.services.system.iproute.default_route", return_value={"interface": None, "gateway": None}),
            patch("app.services.system.iproute.interfaces", return_value=[]),
            patch("app.services.system.iproute.ipv4_for", return_value=None),
            patch("app.services.system.dnsmasq.discover", return_value=({"detected": False, "state": "unknown", "unit": None, "interface": None, "lease_count": 0}, [])),
            patch("app.services.system.devices.collect_devices", return_value=([], [])),
        ):
            network, _devices, errors = system.discover_network()

        self.assertFalse(network["access_point"]["available"])
        self.assertEqual(errors, ["Configured Wi-Fi interface could not be confirmed in AP mode"])

    def test_dnsmasq_without_confirmed_ap_is_not_treated_as_dhcp(self):
        with patch("app.discovery.network.dnsmasq._service_rows") as service_rows:
            status, leases = dnsmasq.discover(None)

        service_rows.assert_not_called()
        self.assertFalse(status["detected"])
        self.assertEqual(status["lease_count"], 0)
        self.assertEqual(leases, [])

    def test_dnsmasq_for_other_interface_is_not_used_as_ap_dhcp(self):
        with (
            patch("app.discovery.network.dnsmasq._service_rows", return_value=[
                {"unit": "dnsmasq-example.service", "active": "active"},
            ]),
            patch("app.discovery.network.dnsmasq._config_path", return_value=Path("/tmp/example.conf")),
            patch("app.discovery.network.dnsmasq._config_values", return_value={
                "interface": "other-radio",
                "dhcp-leasefile": "/tmp/example.leases",
            }),
        ):
            status, leases = dnsmasq.discover("radio-ap")

        self.assertFalse(status["detected"])
        self.assertEqual(leases, [])


if __name__ == "__main__":
    unittest.main()
