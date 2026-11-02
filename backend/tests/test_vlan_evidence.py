import unittest
from unittest.mock import patch

from app.discovery.network import iproute
from app.models import InterfaceResponse


class VlanEvidenceTests(unittest.TestCase):
    def test_vlan_id_is_read_from_kernel_linkinfo_only(self):
        links = [
            {"ifname": "uplink0.20", "linkinfo": {"info_kind": "vlan", "info_data": {"id": 20}}, "operstate": "UP"},
            {"ifname": "uplink0", "linkinfo": {"info_kind": "ether"}},
            {"ifname": "vlan-invalid", "linkinfo": {"info_kind": "vlan", "info_data": {"id": 4095}}},
            {"ifname": "vlan-empty", "linkinfo": {"info_kind": "vlan", "info_data": None}},
        ]
        addresses = [{"ifname": "uplink0.20", "addr_info": [{"family": "inet", "local": "192.0.2.3", "prefixlen": 24}]}]
        with patch.object(iproute, "_json_command", side_effect=[links, addresses]):
            interfaces = iproute.interfaces(None, "uplink0")
        by_name = {entry["name"]: entry for entry in interfaces}
        self.assertEqual(by_name["uplink0.20"]["vlan_id"], 20)
        self.assertEqual(by_name["uplink0.20"]["addresses"], ["192.0.2.3/24"])
        self.assertIsNone(by_name["uplink0"]["vlan_id"])
        self.assertIsNone(by_name["vlan-invalid"]["vlan_id"])
        self.assertIsNone(by_name["vlan-empty"]["vlan_id"])
        self.assertEqual(InterfaceResponse(**by_name["uplink0.20"]).vlan_id, 20)


if __name__ == "__main__":
    unittest.main()
