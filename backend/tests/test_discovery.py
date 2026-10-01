from __future__ import annotations

import os
import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.discovery.integrations.caddy import discover as caddy_discover
from app.discovery.integrations.docker import parse_docker_inspect
from app.discovery.integrations.wireguard import parse_wg_dump
from app.discovery.network.iproute import classify_interface
from app.discovery.network import networkmanager
from app.discovery.network.iw import parse_iw_dev, parse_iw_info
from app.discovery.network.devices import _merge_system_oui, _merge_systemd_oui_hwdb, build_devices, mac_type, oui_vendor, resolve_observations
from app.discovery.device_discovery.base import DeviceObservation
from app.discovery.device_discovery import dhcp, dns_sd, local_names, mdns, netbios, pihole_network, resolver, ssdp
from app.discovery.command import CommandResult, run_command
from app.discovery.device_inference import clean_hostname, device_icon_key, infer_device_type
from app.models import StatusResponse
from app.persistence.device_store import DeviceStore


class CommandRunnerTests(unittest.TestCase):
    def test_invalid_utf8_from_local_tool_is_replaced_not_raised(self):
        result = run_command([
            sys.executable,
            "-c",
            "import os; os.write(1, b'valid\\xfftail')",
        ])
        self.assertEqual(result.code, 0)
        self.assertEqual(result.output, "valid�tail")


class NetworkDiscoveryTests(unittest.TestCase):
    def test_interface_roles_keep_container_networks_out_of_client_scope(self):
        self.assertEqual(classify_interface("wifi-ap", "wireless", "wifi-ap", "lan-uplink"), "access_point")
        self.assertEqual(classify_interface("lan-uplink", "ether", "wifi-ap", "lan-uplink"), "uplink")
        self.assertEqual(classify_interface("vpn-tunnel", "wireguard", "wifi-ap", "lan-uplink"), "vpn")
        self.assertEqual(classify_interface("br-abc", "bridge", "wifi-ap", "lan-uplink"), "container_bridge")
        self.assertEqual(classify_interface("veth123", "veth", "wifi-ap", "lan-uplink"), "virtual")
        self.assertEqual(classify_interface("virtual-macvlan", "macvlan", "wifi-ap", "lan-uplink"), "virtual")

    def test_iw_parser_confirms_access_point_and_band(self):
        parsed = parse_iw_info("Interface wifi-ap\n\ttype AP\n\tssid Test-AP\n\tchannel 1 (2412 MHz), width: 20 MHz\n")
        self.assertEqual(parsed["type"], "AP")
        self.assertEqual(parsed["ssid"], "Test-AP")
        self.assertEqual(parsed["channel"], 1)
        self.assertEqual(parsed["band"], "2.4 GHz")

    def test_iw_dev_parser_discovers_interface_names_without_linux_naming_assumptions(self):
        rows = parse_iw_dev(
            "phy#0\n\tInterface wifi-client\n\t\ttype managed\n"
            "phy#1\n\tInterface hotspot-main\n\t\ttype AP\n"
        )
        self.assertEqual(rows, [
            {"name": "wifi-client", "type": "MANAGED"},
            {"name": "hotspot-main", "type": "AP"},
        ])

    def test_networkmanager_returns_every_wifi_candidate_and_honours_preference(self):
        rows = [
            {"name": "Client WiFi", "type": "802-11-wireless", "device": "wifi-client", "state": "activated"},
            {"name": "Hotspot", "type": "802-11-wireless", "device": "hotspot-main", "state": "activated"},
        ]
        with (
            patch("app.discovery.network.networkmanager.active_connections", return_value=rows),
            patch("app.discovery.network.networkmanager.connection_details", return_value={"ssid": "Example", "channel": "6"}),
        ):
            candidates = networkmanager.wifi_candidates("hotspot-main")
        self.assertEqual([row["interface"] for row in candidates], ["hotspot-main", "wifi-client"])


class IntegrationDiscoveryTests(unittest.TestCase):
    def test_docker_caddy_is_online_even_with_host_networking(self):
        caddy = caddy_discover([{"name": "caddy", "image": "caddy:latest", "state": "running", "status": "Up 1 hour", "network_mode": "host", "ports": None, "health": None}])
        self.assertTrue(caddy["detected"])
        self.assertEqual(caddy["state"], "online")
        self.assertEqual(caddy["runtime"], "docker")

    def test_docker_inspect_parser_excludes_sensitive_fields(self):
        rows = parse_docker_inspect('[{"Name":"/caddy","Config":{"Image":"caddy:latest","Env":["EXAMPLE_SETTING=redacted"]},"HostConfig":{"NetworkMode":"host","Binds":["/example:/x"]},"State":{"Running":true,"Status":"running"},"NetworkSettings":{"Ports":{}}}]')
        self.assertEqual(rows[0]["name"], "caddy")
        self.assertEqual(rows[0]["network_mode"], "host")
        self.assertNotIn("Env", rows[0])
        self.assertNotIn("Binds", rows[0])

    def test_wireguard_dump_counts_interface_and_peers(self):
        interfaces, peers = parse_wg_dump("vpn-tunnel\tprivate\tpublic\t51820\t0\nvpn-tunnel\tprivate\tpeer\tallowed\tendpoint\t51820\t0\t0\t0\n")
        self.assertEqual(interfaces, 1)
        self.assertEqual(peers, 1)


class ContractTests(unittest.TestCase):
    def test_status_model_has_safe_defaults_for_partial_network_failure(self):
        status = StatusResponse.model_validate({
            "generated_at": "2026-01-01T00:00:00+00:00", "system": {"state": "warning", "title": "Unavailable", "summary": "", "attention_count": 1},
            "host": {"name": "test", "uptime": "1m", "load": "0.00"},
            "network": {"access_point": {"available": False}, "uplink": {}, "dhcp": {}, "interfaces": [], "routes": []},
            "devices": [], "services": {"items": []}, "errors": ["network unavailable"]
        })
        self.assertEqual(status.system.state, "warning")
        self.assertEqual(status.network.access_point.state, "unknown")


class DeviceIdentityTests(unittest.TestCase):
    def _observation(self, source="ip_neigh", **changes):
        values = {"source": source, "mac": "B8:F8:62:00:00:01", "ip": "192.0.2.24", "interface": "wifi-ap", "role": "access_point", "neighbour_state": "REACHABLE"}
        values.update(changes)
        return DeviceObservation(**values)

    def test_dhcp_and_neighbour_merge_to_one_named_device(self):
        devices = resolve_observations([
            self._observation(), self._observation("dhcp_lease", hostname="living-room-tv", lease_expires_at=1234),
        ])
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["display_name"], "Living Room TV")
        self.assertEqual(devices[0]["category"], "tv")
        self.assertEqual(devices[0]["ip"], "192.0.2.24")

    def test_wifi_station_is_strong_online_evidence_and_merges(self):
        devices = resolve_observations([
            self._observation(neighbour_state="STALE"), self._observation("wifi_station", signal_dbm=-48, neighbour_state=None),
        ])
        self.assertEqual(len(devices), 1)
        self.assertTrue(devices[0]["online"])
        self.assertEqual(devices[0]["signal_quality"], "excellent")
        self.assertEqual(devices[0]["connection_type"], "wifi")

    def test_default_route_gateway_is_identified_as_router(self):
        device = resolve_observations(
            [
                self._observation(
                    interface="lan-uplink",
                    role="uplink",
                    ip="192.0.2.1",
                    neighbour_state="REACHABLE",
                ),
            ],
            default_gateway="192.0.2.1",
        )[0]

        self.assertEqual(device["category"], "router")
        self.assertEqual(device["device_type"], "router")
        self.assertEqual(device["icon_key"], "router")
        self.assertEqual(device["identity"]["device_type"]["source"], "default_route")
        self.assertEqual(device["identity"]["device_type"]["confidence"], "high")
        self.assertIn(
            {"source": "default_route", "confidence": "high"},
            device["identity"]["sources"],
        )
        self.assertEqual(device["connection_type"], "unknown")

    def test_manual_category_override_still_wins_for_default_gateway(self):
        device_id = "b8f862000001"
        device = resolve_observations(
            [
                self._observation(
                    interface="lan-uplink",
                    role="uplink",
                    ip="192.0.2.1",
                    neighbour_state="REACHABLE",
                ),
            ],
            {device_id: {"category_override": "server"}},
            default_gateway="192.0.2.1",
        )[0]

        self.assertEqual(device["category"], "server")
        self.assertEqual(device["identity"]["device_type"]["source"], "manual_alias")

    def test_uplink_neighbour_does_not_claim_client_is_ethernet(self):
        device = resolve_observations([
            self._observation(interface="lan-uplink", role="uplink", neighbour_state="REACHABLE"),
        ])[0]
        self.assertEqual(device["connection_type"], "unknown")

    def test_access_point_observation_is_wifi_client_evidence(self):
        device = resolve_observations([
            self._observation(interface="wifi-ap", role="access_point", neighbour_state="REACHABLE"),
        ])[0]
        self.assertEqual(device["connection_type"], "wifi")

    def test_dhcp_without_confirmed_access_point_does_not_claim_wifi(self):
        observation = dhcp.observations(
            [{"mac": "02:00:00:00:00:41", "ip": "192.0.2.71", "hostname": "sample-device", "lease_expires_at": 0}],
            None,
        )[0]
        self.assertEqual(observation.role, "unknown")
        device = resolve_observations([observation])[0]
        self.assertEqual(device["connection_type"], "unknown")

    def test_stale_neighbour_is_recently_seen_not_online(self):
        device = resolve_observations([self._observation(neighbour_state="STALE")])[0]
        self.assertIsNone(device["online"])
        self.assertEqual(device["state"], "recently_seen")

    def test_private_mac_has_no_oui_vendor(self):
        device = resolve_observations([self._observation(mac="02:42:AC:11:00:02")])[0]
        self.assertEqual(mac_type("02:42:AC:11:00:02"), "private")
        self.assertIsNone(oui_vendor("02:42:AC:11:00:02"))
        self.assertIsNone(device["vendor"])

    def test_common_linux_oui_registry_formats_are_merged_offline(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "oui.txt"
            path.write_text(
                "AA-BB-CC   (hex)\tExample Devices Ltd.\n"
                "DDEEFF Example Networks Inc.\n",
                encoding="utf-8",
            )
            prefixes = {}
            _merge_system_oui(prefixes, path)
        self.assertEqual(prefixes["AABBCC"], "Example Devices Ltd.")
        self.assertEqual(prefixes["DDEEFF"], "Example Networks Inc.")

    def test_oui_lookup_prefers_more_specific_ieee_assignment(self):
        prefixes = {
            "70B3D5": "IEEE Registration Authority",
            "70B3D5C": "Specific MA-M Vendor",
            "70B3D5C3C": "Specific MA-S Vendor",
        }
        with patch("app.discovery.network.devices._oui_prefixes", return_value=prefixes):
            self.assertEqual(oui_vendor("70:B3:D5:C3:C0:01"), "Specific MA-S Vendor")
            self.assertEqual(oui_vendor("70:B3:D5:CA:00:01"), "Specific MA-M Vendor")
            self.assertEqual(oui_vendor("70:B3:D5:10:00:01"), "IEEE Registration Authority")

    def test_systemd_hwdb_can_supply_offline_oui_vendor(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "20-OUI.hwdb"
            path.write_text(
                "# fixture\n"
                "OUI:A1B2C3*\n"
                " ID_OUI_FROM_DATABASE=Example Devices Ltd.\n"
                "\n"
                "OUI:DDEEFF1*\n"
                " ID_OUI_FROM_DATABASE=Specific Networks\n",
                encoding="utf-8",
            )
            prefixes = {}
            _merge_systemd_oui_hwdb(prefixes, path)
        self.assertEqual(prefixes["A1B2C3"], "Example Devices Ltd.")
        self.assertEqual(prefixes["DDEEFF1"], "Specific Networks")

    def test_oui_and_conservative_microcontroller_inference(self):
        with patch("app.discovery.network.devices._oui_prefixes", return_value={"B8F862": "Espressif Inc."}):
            device = resolve_observations([self._observation()])[0]
            self.assertEqual(oui_vendor("B8:F8:62:00:00:01"), "Espressif Inc.")
        self.assertEqual(device["display_name"], "ESP device")
        self.assertEqual(device["category"], "microcontroller")

    def test_manual_alias_and_category_override_win(self):
        device = resolve_observations([self._observation()], {"b8f862000001": {"alias": "Kitchen sensor", "category_override": "camera"}})[0]
        self.assertEqual(device["display_name"], "Kitchen sensor")
        self.assertEqual(device["category"], "camera")
        self.assertEqual(device["identity"]["display_name"]["source"], "manual_alias")

    def test_apple_tv_bonjour_service_identifies_tv(self):
        inferred = infer_device_type(
            hostname="living-room",
            vendor="Apple",
            service_hints=("_mediaremotetv._tcp",),
        )
        self.assertEqual(inferred.device_type, "tv")
        self.assertEqual(inferred.confidence, "high")

    def test_upnp_device_types_improve_broad_category_without_guessing_model(self):
        renderer = infer_device_type(
            hostname="Living Room Receiver",
            vendor="Example Audio",
            service_hints=("urn:schemas-upnp-org:device:MediaRenderer:1",),
        )
        gateway = infer_device_type(
            hostname="Home Gateway",
            vendor=None,
            service_hints=("urn:schemas-upnp-org:device:InternetGatewayDevice:1",),
        )
        self.assertEqual(renderer.device_type, "media_player")
        self.assertEqual(renderer.confidence, "high")
        self.assertEqual(gateway.device_type, "router")

    def test_standard_profiles_improve_device_type(self):
        camera = infer_device_type(
            hostname=None,
            vendor=None,
            service_hints=("_hap._tcp", "homekit-camera"),
        )
        matter = infer_device_type(
            hostname=None,
            vendor=None,
            service_hints=("_matter._tcp",),
        )
        nas = infer_device_type(hostname="sample-synology", vendor=None)
        self.assertEqual((camera.device_type, camera.confidence), ("camera", "high"))
        self.assertEqual((matter.device_type, matter.confidence), ("smart_home", "high"))
        self.assertEqual((nas.device_type, nas.confidence), ("server", "high"))

    def test_apple_tv_identity_normalizes_name_and_icon(self):
        mac = "02:00:00:00:00:17"
        device = resolve_observations([
            self._observation(mac=mac, ip="192.0.2.50"),
            self._observation(
                "dns_sd",
                mac=mac,
                ip="192.0.2.50",
                service_name="Apple de TV, Living Room",
                service_types=("_mediaremotetv._tcp", "_airplay._tcp"),
                model="AppleTV14,1",
                manufacturer="Apple",
                neighbour_state=None,
            ),
        ])[0]
        self.assertEqual(device["display_name"], "Apple TV, Living Room")
        self.assertEqual(device["category"], "tv")
        self.assertEqual(device["icon_key"], "apple_tv")

    def test_apple_tv_icon_is_stable_for_resolved_apple_tv_family(self):
        self.assertEqual(
            device_icon_key(category="tv", vendor="Apple", hostname="Living Room"),
            "apple_tv",
        )
        self.assertEqual(
            device_icon_key(category="media_player", vendor=None, service_hints=("_mediaremotetv._tcp",)),
            "apple_tv",
        )
        self.assertEqual(
            device_icon_key(category="unknown", vendor="Apple", hostname="Apple TV, Guest Room"),
            "apple_tv",
        )

    def test_product_family_icons_use_resolved_vendor_and_user_alias_evidence(self):
        self.assertEqual(
            device_icon_key(category="smart_home", vendor="Beijing Roborock Technology Co., Ltd.", hostname="Robot Vacuum"),
            "vacuum",
        )
        self.assertEqual(device_icon_key(category="smart_home", vendor="Meross", hostname="Garage Door"), "garage")
        self.assertEqual(device_icon_key(category="microcontroller", vendor="Espressif", hostname="Heat Pump"), "heat_pump")
        self.assertEqual(device_icon_key(category="unknown", vendor="Meta Platforms, Inc.", hostname="VR"), "vr_headset")

    def test_hostname_cleanup_and_signature_inference(self):
        self.assertEqual(clean_hostname("sample-iphone"), "Sample iPhone")
        self.assertEqual(clean_hostname("esp32-a81f23"), "ESP device")
        inferred = infer_device_type(hostname="LGwebOSTV", vendor=None)
        self.assertEqual(inferred.device_type, "tv")
        self.assertEqual(inferred.confidence, "medium")
        self.assertEqual(infer_device_type(hostname=None, vendor="Chengdu Meross Technology Co., Ltd.").device_type, "smart_home")
        self.assertEqual(infer_device_type(hostname="Heat Pump", vendor=None).device_type, "smart_home")
        self.assertEqual(infer_device_type(hostname="Luftvärmepump", vendor=None).device_type, "smart_home")

    def test_product_identity_can_supply_safe_vendor_when_private_mac_hides_oui(self):
        device = resolve_observations([
            self._observation(
                "dhcp_lease",
                mac="02:00:00:00:00:31",
                ip="192.0.2.61",
                hostname="sample-iphone",
                neighbour_state=None,
            ),
        ])[0]
        self.assertEqual(device["vendor"], "Apple")
        self.assertEqual(device["category"], "phone")
        self.assertEqual(device["identity"]["vendor"]["source"], "product_signature")

    def test_mdns_name_is_used_when_dhcp_has_no_hostname(self):
        device = resolve_observations([
            self._observation(), self._observation("mdns_name", hostname="living-room-tv", neighbour_state=None),
        ])[0]
        self.assertEqual(device["display_name"], "Living Room TV")
        self.assertEqual(device["identity"]["display_name"]["source"], "mdns_name")

    def test_provider_failure_does_not_stop_dhcp_observation(self):
        rows = [{"name": "wifi-ap", "role": "access_point"}]
        with (
            TemporaryDirectory() as directory,
            patch("app.discovery.network.devices.neigh.observations", side_effect=RuntimeError("bad neighbour provider")),
            patch("app.discovery.network.devices.mdns.observations", return_value=[]),
            patch("app.discovery.network.devices.local_names.observations", return_value=[]),
            patch("app.discovery.network.devices.dns_sd.observations", return_value=[]),
            patch("app.discovery.network.devices.resolver.observations", return_value=[]),
            patch("app.discovery.network.devices.netbios.observations", return_value=[]),
            patch("app.discovery.network.devices.ssdp.observations", return_value=[]),
            patch("app.discovery.network.devices.pihole_network.observations", return_value=[]),
        ):
            records = build_devices(rows, [{"mac": "DC:56:E7:00:00:01", "ip": "192.0.2.31", "hostname": "living-room-tv", "lease_expires_at": 0}], {}, DeviceStore(Path(directory)))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["display_name"], "Living Room TV")

    def test_mdns_caches_hits_and_misses_to_avoid_subprocess_storms(self):
        seed = [self._observation()]
        with patch.object(mdns, "_cached", {}), patch("app.discovery.device_discovery.mdns.command_exists", return_value=True), patch("app.discovery.device_discovery.mdns.run_command", return_value=CommandResult(0, "192.0.2.24\tliving-room-tv.local")) as command:
            self.assertEqual(mdns.observations(seed)[0].hostname, "living-room-tv")
            self.assertEqual(mdns.observations(seed)[0].hostname, "living-room-tv")
        self.assertEqual(command.call_count, 1)

    def test_per_device_name_caches_prune_departed_clients(self):
        old = self._observation(mac="02:00:00:00:30:01", ip="192.0.2.130")
        new = self._observation(mac="02:00:00:00:30:02", ip="192.0.2.131")

        with (
            patch.object(mdns, "_cached", {}),
            patch("app.discovery.device_discovery.mdns.command_exists", return_value=True),
            patch(
                "app.discovery.device_discovery.mdns.run_command",
                side_effect=lambda argv, **_: CommandResult(0, f"{argv[-1]}\\tdevice.local"),
            ),
        ):
            mdns.observations([old])
            mdns.observations([new])
            self.assertEqual(set(mdns._cached), {(new.ip, new.mac)})

        with (
            patch.object(resolver, "_cached", {}),
            patch("app.discovery.device_discovery.resolver.command_exists", return_value=True),
            patch(
                "app.discovery.device_discovery.resolver.run_command",
                side_effect=lambda argv, **_: CommandResult(0, f"{argv[-1]}\\tdevice.local"),
            ),
        ):
            resolver.observations([old])
            resolver.observations([new])
            self.assertEqual(set(resolver._cached), {new.ip})

        netbios_output = "\\tDEVICE <00> -         B <ACTIVE>"
        with (
            patch.object(netbios, "_cached", {}),
            patch("app.discovery.device_discovery.netbios.command_exists", return_value=True),
            patch(
                "app.discovery.device_discovery.netbios.run_command",
                return_value=CommandResult(0, netbios_output),
            ),
        ):
            netbios.observations([old])
            netbios.observations([new])
            self.assertEqual(set(netbios._cached), {new.ip})

    def test_mdns_cache_entries_keep_independent_ttl(self):
        first = self._observation(mac="02:00:00:00:31:01", ip="192.0.2.140")
        second = self._observation(mac="02:00:00:00:31:02", ip="192.0.2.141")
        first_key = (first.ip, first.mac)
        second_key = (second.ip, second.mac)

        with (
            patch.object(mdns, "_cached", {first_key: (0.0, "first-device")}),
            patch("app.discovery.device_discovery.mdns.command_exists", return_value=True),
            patch("app.discovery.device_discovery.mdns.time.monotonic", side_effect=[299.0, 301.0]),
            patch(
                "app.discovery.device_discovery.mdns.run_command",
                side_effect=lambda argv, **_: CommandResult(0, f"{argv[-1]}\\trefreshed.local"),
            ) as command,
        ):
            mdns.observations([first, second])
            self.assertEqual(mdns._cached[first_key][0], 0.0)
            self.assertEqual(mdns._cached[second_key][0], 299.0)

            mdns.observations([first, second])
            self.assertEqual(mdns._cached[first_key][0], 301.0)
            self.assertEqual(mdns._cached[second_key][0], 299.0)

        self.assertEqual(command.call_count, 2)

    def test_local_host_files_enrich_only_known_addresses_without_dns(self):
        seed = [self._observation(mac="02:00:00:00:00:11", ip="192.0.2.44")]
        with patch.object(local_names, "_cached_names", {}), patch.object(local_names, "_cached_at", -1e9), patch("app.discovery.device_discovery.local_names._read_names", return_value={"192.0.2.44": "living-room-tv"}):
            first = local_names.observations(seed)
            second = local_names.observations(seed)
        self.assertEqual(first[0].hostname, "living-room-tv")
        self.assertEqual(second[0].hostname, "living-room-tv")

    def test_configured_resolver_enriches_only_already_observed_ip(self):
        seed = [self._observation(mac="02:00:00:00:20:01", ip="192.0.2.127")]
        with (
            patch.object(resolver, "_cached", {}),
            patch("app.discovery.device_discovery.resolver.command_exists", return_value=True),
            patch("app.discovery.device_discovery.resolver.run_command", return_value=CommandResult(0, "192.0.2.127\tsample-iphone.local")),
        ):
            found = resolver.observations(seed)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].hostname, "sample-iphone")

    def test_netbios_enriches_only_known_client_name(self):
        seed = [self._observation(mac="AA:BB:CC:00:00:01", ip="192.0.2.113")]
        output = "Looking up status of 192.0.2.113\n\tLIVINGROOM-PC <00> -         B <ACTIVE>\n\tWORKGROUP     <00> - <GROUP> B <ACTIVE>"
        with (
            patch.object(netbios, "_cached", {}),
            patch("app.discovery.device_discovery.netbios.command_exists", return_value=True),
            patch("app.discovery.device_discovery.netbios.run_command", return_value=CommandResult(0, output)),
        ):
            found = netbios.observations(seed)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].hostname, "LIVINGROOM-PC")

    def test_ssdp_friendly_name_model_and_vendor_enrich_known_client(self):
        seed = [self._observation(mac="AA:BB:CC:00:00:02", ip="192.0.2.114")]
        rows = [{
            "ip": "192.0.2.114",
            "friendly_name": "Living Room Receiver",
            "manufacturer": "Example Audio",
            "model": "RX-1000",
            "device_type": "urn:schemas-upnp-org:device:MediaRenderer:1",
        }]
        with patch("app.discovery.device_discovery.ssdp._rows", return_value=rows):
            found = ssdp.observations(seed)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].service_name, "Living Room Receiver")
        self.assertEqual(found[0].manufacturer, "Example Audio")
        self.assertEqual(found[0].model, "RX-1000")
        self.assertIn("MediaRenderer", found[0].service_types[0])

    def test_ssdp_location_is_restricted_to_responding_local_ip(self):
        self.assertIsNotNone(ssdp._safe_location("http://192.0.2.114:1400/xml/device.xml", "192.0.2.114"))
        self.assertIsNone(ssdp._safe_location("http://192.0.2.200:1400/xml/device.xml", "192.0.2.114"))
        self.assertIsNone(ssdp._safe_location("https://192.0.2.114/xml/device.xml", "192.0.2.114"))

    def test_pihole_ftl_name_can_identify_private_mac_without_fake_oui_vendor(self):
        seed = [self._observation(mac="02:00:00:00:20:01", ip="192.0.2.127")]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pihole-FTL.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE network (id INTEGER PRIMARY KEY, hwaddr TEXT, macVendor TEXT)")
            connection.execute("CREATE TABLE network_addresses (network_id INTEGER, ip TEXT, name TEXT)")
            connection.execute("INSERT INTO network(id, hwaddr, macVendor) VALUES (1, '02:00:00:00:20:01', 'Apple, Inc.')")
            connection.execute("INSERT INTO network_addresses(network_id, ip, name) VALUES (1, '192.0.2.127', 'sample-iphone')")
            connection.commit()
            connection.close()
            with (
                patch.object(pihole_network, "CANDIDATE_DATABASES", (path,)),
                patch.object(pihole_network, "_cached_rows", []),
                patch.object(pihole_network, "_cached_at", -1e9),
            ):
                found = pihole_network.observations(seed)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].hostname, "sample-iphone")
        self.assertIsNone(found[0].manufacturer)

    def test_dns_sd_unescape_decodes_utf8_byte_sequences(self):
        slash = chr(92)
        escaped = f"Heat{slash}032pump{slash}032M{slash}195{slash}164rke"
        self.assertEqual(dns_sd._unescape(escaped), "Heat pump Märke")
    def test_dns_sd_unescape_handles_escaped_literal_punctuation(self):
        slash = chr(92)
        self.assertEqual(dns_sd._unescape(f"70-35-60-63{slash}.1"), "70-35-60-63.1")

    def test_sleep_proxy_instance_extracts_human_label(self):
        self.assertEqual(
            dns_sd._sleep_proxy_name("70-35-60-63.1 Living Room", "sample-host"),
            "Living Room",
        )
        self.assertIsNone(dns_sd._sleep_proxy_name("Sleep Proxy", "sample-host"))

    def test_sleep_proxy_human_label_can_beat_generic_product_family_name(self):
        seed = [self._observation(mac="02:00:00:00:00:18", ip="192.0.2.52")]
        slash = chr(92)
        output = "\n".join([
            f"=;wifi-ap;IPv4;70-35-60-63{slash}.1 Living Room;_sleep-proxy._udp;local;sample-host.local;192.0.2.52;1234;",
            "=;wifi-ap;IPv4;Apple TV;_airplay._tcp;local;sample-host.local;192.0.2.52;7000;",
        ])
        with (
            patch.object(dns_sd, "_cached_rows", []),
            patch.object(dns_sd, "_cached_at", -1e9),
            patch("app.discovery.device_discovery.dns_sd.command_exists", return_value=True),
            patch("app.discovery.device_discovery.dns_sd.run_command", return_value=CommandResult(0, output)),
        ):
            found = dns_sd.observations(seed)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].service_name, "Living Room")

    def test_sleep_proxy_instance_name_does_not_override_real_service_name(self):
        seed = [self._observation(mac="02:00:00:00:00:18", ip="192.0.2.52")]
        slash = chr(92)
        output = "\n".join([
            f"=;wifi-ap;IPv4;70-35-60-63{slash}.1 Sample TV;_sleep-proxy._udp;local;sample-host.local;192.0.2.52;1234;",
            "=;wifi-ap;IPv4;Sample TV;_airplay._tcp;local;sample-host.local;192.0.2.52;7000;",
        ])
        with (
            patch.object(dns_sd, "_cached_rows", []),
            patch.object(dns_sd, "_cached_at", -1e9),
            patch("app.discovery.device_discovery.dns_sd.command_exists", return_value=True),
            patch("app.discovery.device_discovery.dns_sd.run_command", return_value=CommandResult(0, output)),
        ):
            found = dns_sd.observations(seed)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].service_name, "Sample TV")

    def test_dns_sd_strips_machine_identifier_prefix_from_human_service_name(self):
        self.assertEqual(
            dns_sd._useful_service_name("A1B2C3D4E5F6@Living Room", "device-host"),
            "Living Room",
        )

    def test_dns_sd_rejects_identifier_prefixed_link_local_capability_name(self):
        self.assertIsNone(
            dns_sd._useful_service_name(
                "02:00:00:00:00:44@fe80::1234:5678-supportsRP-26",
                "sample-phone",
            )
        )

    def test_dns_sd_uses_raw_service_types_from_avahi(self):
        seed = [self._observation(mac="02:00:00:00:00:19", ip="192.0.2.53")]
        output = '=;wifi-ap;IPv4;Living\\032Room;_airplay._tcp;local;living-room.local;192.0.2.53;7000;"model=AppleTV14,1"'
        with (
            patch.object(dns_sd, "_cached_rows", []),
            patch.object(dns_sd, "_cached_at", -1e9),
            patch("app.discovery.device_discovery.dns_sd.command_exists", return_value=True),
            patch("app.discovery.device_discovery.dns_sd.run_command", return_value=CommandResult(0, output)) as command,
        ):
            found = dns_sd.observations(seed)
        self.assertEqual(found[0].service_name, "Living Room")
        self.assertIn("_airplay._tcp", found[0].service_types)
        argv = command.call_args.args[0]
        self.assertIn("--parsable", argv)
        self.assertIn("--no-db-lookup", argv)

    def test_human_apple_service_name_is_kept_even_when_hostname_matches(self):
        seed = [self._observation(mac="02:00:00:00:00:1A", ip="192.0.2.54")]
        output = '=;wifi-ap;IPv4;Guest\\032Room;_companion-link._tcp;local;Guest-Room.local;192.0.2.54;49153;"rpMd=AppleTV14,1"'
        with (
            patch.object(dns_sd, "_cached_rows", []),
            patch.object(dns_sd, "_cached_at", -1e9),
            patch("app.discovery.device_discovery.dns_sd.command_exists", return_value=True),
            patch("app.discovery.device_discovery.dns_sd.run_command", return_value=CommandResult(0, output)),
        ):
            found = dns_sd.observations(seed)
        self.assertEqual(found[0].service_name, "Guest Room")

    def test_dns_sd_reuses_known_ip_and_exposes_service_identity(self):
        seed = [self._observation(mac="02:00:00:00:00:12", ip="192.0.2.45")]
        output = '=;wifi-ap;IPv4;Living\\032Room\\032TV;_googlecast._tcp;local;living-room-tv.local;192.0.2.45;8009;"fn=Living\\032Room\\032TV" "model=CastBox\\0324K" "manufacturer=Example\\032Labs"'
        with patch.object(dns_sd, "_cached_rows", []), patch.object(dns_sd, "_cached_at", -1e9), patch("app.discovery.device_discovery.dns_sd.command_exists", return_value=True), patch("app.discovery.device_discovery.dns_sd.run_command", return_value=CommandResult(0, output)):
            observations = dns_sd.observations(seed)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].service_name, "Living Room TV")
        self.assertEqual(observations[0].hostname, "living-room-tv")
        self.assertEqual(observations[0].model, "CastBox 4K")
        self.assertEqual(observations[0].manufacturer, "Example Labs")
        self.assertIn("_googlecast._tcp", observations[0].service_types)

    def test_dns_sd_extracts_homekit_profile_hint(self):
        seed = [self._observation(mac="02:00:00:00:00:25", ip="192.0.2.75")]
        output = '=;wifi-ap;IPv4;Front\\032Door;_hap._tcp;local;front-door.local;192.0.2.75;1234;"ci=17" "md=Camera\\032Pro"'
        with (
            patch.object(dns_sd, "_cached_rows", []),
            patch.object(dns_sd, "_cached_at", -1e9),
            patch("app.discovery.device_discovery.dns_sd.command_exists", return_value=True),
            patch("app.discovery.device_discovery.dns_sd.run_command", return_value=CommandResult(0, output)),
        ):
            observations = dns_sd.observations(seed)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].model, "Camera Pro")
        self.assertIn("homekit-camera", observations[0].profile_hints)

    def test_dns_sd_accepts_apple_companion_model_key(self):
        seed = [self._observation(mac="02:00:00:00:00:26", ip="192.0.2.76")]
        output = '=;wifi-ap;IPv4;Living\\032Room;_companion-link._tcp;local;living-room.local;192.0.2.76;49153;"rpMd=AppleTV14,1"'
        with (
            patch.object(dns_sd, "_cached_rows", []),
            patch.object(dns_sd, "_cached_at", -1e9),
            patch("app.discovery.device_discovery.dns_sd.command_exists", return_value=True),
            patch("app.discovery.device_discovery.dns_sd.run_command", return_value=CommandResult(0, output)),
        ):
            observations = dns_sd.observations(seed)
        self.assertEqual(observations[0].model, "AppleTV14,1")

    def test_dns_sd_name_and_service_type_improve_identity(self):
        mac = "02:00:00:00:00:13"
        device = resolve_observations([
            self._observation(mac=mac, ip="192.0.2.46"),
            self._observation(
                "dns_sd",
                mac=mac,
                ip="192.0.2.46",
                hostname="living-room-tv",
                service_name="Living Room TV",
                service_types=("_googlecast._tcp",),
                neighbour_state=None,
            ),
        ])[0]
        self.assertEqual(device["display_name"], "Living Room TV")
        self.assertEqual(device["category"], "tv")
        self.assertEqual(device["identity"]["display_name"]["source"], "dns_sd")
        service_only = infer_device_type(hostname="lounge-player", vendor=None, service_hints=("_googlecast._tcp",))
        self.assertEqual(service_only.device_type, "media_player")

    def test_dns_sd_model_and_manufacturer_can_replace_generic_identity(self):
        mac = "02:00:00:00:00:15"
        device = resolve_observations([
            self._observation(mac=mac, ip="192.0.2.48"),
            self._observation(
                "dns_sd",
                mac=mac,
                ip="192.0.2.48",
                service_types=("_googlecast._tcp",),
                model="CastBox 4K",
                manufacturer="Example Labs",
                neighbour_state=None,
            ),
        ])[0]
        self.assertEqual(device["display_name"], "Example Labs CastBox 4K")
        self.assertEqual(device["vendor"], "Example Labs")
        self.assertEqual(device["model"], "CastBox 4K")
        self.assertEqual(device["category"], "media_player")
        self.assertEqual(device["identity"]["model"]["source"], "dns_sd")
        self.assertEqual(device["identity"]["vendor"]["source"], "dns_sd")

    def test_apple_bonjour_model_code_becomes_familiar_product_family(self):
        mac = "02:00:00:00:00:16"
        device = resolve_observations([
            self._observation(mac=mac, ip="192.0.2.49"),
            self._observation(
                "dns_sd",
                mac=mac,
                ip="192.0.2.49",
                service_types=("_device-info._tcp",),
                model="iPhone15,3",
                neighbour_state=None,
            ),
        ])[0]
        self.assertEqual(device["display_name"], "iPhone")
        self.assertEqual(device["model"], "iPhone15,3")
        self.assertEqual(device["category"], "phone")

    def test_unidentified_device_uses_neutral_network_name_not_unknown(self):
        device = resolve_observations([
            self._observation(mac="02:00:00:00:00:14", ip="192.0.2.47"),
        ])[0]
        self.assertEqual(device["display_name"], "Network device")
        self.assertEqual(device["category"], "unknown")

    def test_ssdp_model_keeps_real_identity_source(self):
        device = resolve_observations([
            self._observation(mac="02:00:00:00:00:31", ip="192.0.2.81"),
            self._observation(
                "ssdp",
                mac="02:00:00:00:00:31",
                ip="192.0.2.81",
                model="MediaBox X",
                neighbour_state=None,
            ),
        ])[0]
        self.assertEqual(device["display_name"], "MediaBox X")
        self.assertEqual(device["identity"]["display_name"]["source"], "ssdp")

    def test_same_trusted_pc_hostname_coalesces_multiple_network_adapters(self):
        devices = resolve_observations([
            self._observation("dhcp_lease", mac="02:00:00:00:10:01", ip="192.0.2.113", hostname="OFFICE-PC"),
            self._observation("netbios_name", mac="02:00:00:00:10:02", ip="192.0.2.187", hostname="OFFICE-PC"),
        ])
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["display_name"], "Office PC")
        self.assertEqual(devices[0]["category"], "computer")
        self.assertCountEqual(devices[0]["mac_addresses"], ["02:00:00:00:10:01", "02:00:00:00:10:02"])
        self.assertCountEqual(devices[0]["ip_addresses"], ["192.0.2.113", "192.0.2.187"])

    def test_same_pc_hostname_is_not_merged_when_user_aliases_conflict(self):
        metadata = {
            "020000001001": {"alias": "Office desktop"},
            "020000001002": {"alias": "Test machine"},
        }
        devices = resolve_observations([
            self._observation("dhcp_lease", mac="02:00:00:00:10:01", ip="192.0.2.113", hostname="OFFICE-PC"),
            self._observation("netbios_name", mac="02:00:00:00:10:02", ip="192.0.2.187", hostname="OFFICE-PC"),
        ], metadata)
        self.assertEqual(len(devices), 2)

    def test_low_confidence_generic_devices_sort_after_identified_online_devices(self):
        devices = resolve_observations([
            self._observation(mac="02:00:00:00:00:20", ip="192.0.2.50"),
            self._observation(mac="02:00:00:00:00:21", ip="192.0.2.51"),
            self._observation("dhcp_lease", mac="02:00:00:00:00:21", ip="192.0.2.51", hostname="office-laptop"),
        ])
        self.assertEqual(devices[0]["display_name"], "Office Laptop")
        self.assertEqual(devices[1]["display_name"], "Network device")

    def test_identity_cache_keeps_name_for_same_private_mac_when_live_name_disappears(self):
        with TemporaryDirectory() as directory:
            device_store = DeviceStore(Path(directory))
            first = resolve_observations([
                self._observation("dhcp_lease", mac="02:00:00:00:20:01", ip="192.0.2.127", hostname="sample-iphone"),
            ])[0]
            device_store.remember_identities([first])
            metadata = device_store.enrich([first["id"]])
            second = resolve_observations([
                self._observation(mac="02:00:00:00:20:01", ip="192.0.2.127"),
            ], metadata)[0]
        self.assertEqual(second["display_name"], "Sample iPhone")
        self.assertEqual(second["vendor"], "Apple")
        self.assertEqual(second["category"], "phone")
        self.assertEqual(second["identity"]["display_name"]["source"], "identity_cache")

    def test_store_persists_alias_and_presence(self):
        with TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory))
            store.update_metadata("abc", alias="Hall TV", category_override="tv")
            data = store.enrich(["abc"])["abc"]
            self.assertEqual(data["alias"], "Hall TV")
            self.assertEqual(data["category_override"], "tv")
            self.assertIn("first_seen_at", data)


if __name__ == "__main__":
    unittest.main()
