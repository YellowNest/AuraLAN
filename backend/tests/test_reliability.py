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
from app.main import activity_status, health, update_device_metadata
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


class ActivityReliabilityTests(unittest.TestCase):
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
