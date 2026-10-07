import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.discovery.device_discovery import local_names
from app.discovery.integrations.docker import containers, parse_docker_list
from app.services import system


class ContainerHostViewTests(unittest.TestCase):
    def test_host_metrics_use_explicit_read_only_mounts(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "proc"
            sys = root / "sys"
            proc.mkdir()
            (sys / "class/thermal/thermal_zone0").mkdir(parents=True)
            (proc / "uptime").write_text("90061.00 0.00\n", encoding="utf-8")
            (proc / "meminfo").write_text(
                "MemTotal:       1000 kB\nMemAvailable:    250 kB\n",
                encoding="utf-8",
            )
            (sys / "class/thermal/thermal_zone0/temp").write_text("42500\n", encoding="utf-8")
            hostname = root / "hostname"
            hostname.write_text("host-machine\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "AURALAN_CONTAINER_MODE": "1",
                    "AURALAN_HOST_PROC": str(proc),
                    "AURALAN_HOST_SYS": str(sys),
                    "AURALAN_HOSTNAME_FILE": str(hostname),
                },
                clear=False,
            ):
                snapshot = system.host()

        self.assertEqual(snapshot["name"], "host-machine")
        self.assertEqual(snapshot["uptime"], "1d 1h")
        self.assertEqual(snapshot["memory_used_percent"], 75)
        self.assertEqual(snapshot["temperature_celsius"], 42.5)
        self.assertIsNone(snapshot["storage_used_percent"])

    def test_local_names_can_read_mounted_host_hosts_file(self):
        with TemporaryDirectory() as tmp:
            hosts = Path(tmp) / "hosts"
            hosts.write_text("192.0.2.50 living-room.local\n", encoding="utf-8")
            with patch.dict(os.environ, {"AURALAN_HOSTS_FILE": str(hosts)}, clear=False):
                names = local_names._read_names()
        self.assertEqual(names["192.0.2.50"], "living-room")


class ContainerDockerDiscoveryTests(unittest.TestCase):
    def test_engine_list_parser_keeps_only_safe_presentation_fields(self):
        rows = parse_docker_list(
            """[
              {
                "Names":["/caddy"],
                "Image":"caddy:latest",
                "State":"running",
                "Status":"Up 2 hours (healthy)",
                "HostConfig":{"NetworkMode":"host"},
                "Ports":[{"PrivatePort":443,"PublicPort":443,"Type":"tcp"}],
                "Labels":{"secret.example":"must-not-leak"}
              }
            ]"""
        )
        self.assertEqual(rows[0]["name"], "caddy")
        self.assertEqual(rows[0]["state"], "running")
        self.assertEqual(rows[0]["health"], "healthy")
        self.assertEqual(rows[0]["network_mode"], "host")
        self.assertEqual(rows[0]["ports"], "443→443/tcp")
        self.assertNotIn("Labels", rows[0])

    def test_configured_missing_socket_is_reported_without_cli_fallback(self):
        with TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "docker.sock")
            with patch.dict(os.environ, {"AURALAN_DOCKER_SOCKET": missing}, clear=False):
                detected, rows, error = containers()
        self.assertFalse(detected)
        self.assertEqual(rows, [])
        self.assertEqual(error, "Configured Docker socket does not exist")


if __name__ == "__main__":
    unittest.main()
