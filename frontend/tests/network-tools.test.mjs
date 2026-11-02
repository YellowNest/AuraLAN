import test from 'node:test';
import assert from 'node:assert/strict';
import { ipv4Cidr, networkSegments, serviceManagementLinks } from '../js/network-tools.js';

test('IPv4 CIDR parsing handles prefix, zero network, and malformed addresses', () => {
  assert.equal(ipv4Cidr('192.168.11.42/24')?.cidr, '192.168.11.0/24');
  assert.equal(ipv4Cidr('10.0.0.5/32')?.cidr, '10.0.0.5/32');
  assert.equal(ipv4Cidr('0.0.0.0/0')?.cidr, '0.0.0.0/0');
  for (const candidate of ['192.168.1/24', '192.168.256.3/24', '192.168.1.1/33', '2001:db8::1/64', '192.168.1.1/24/', '', null]) {
    assert.equal(ipv4Cidr(candidate), null, String(candidate));
  }
});

test('network segments retain only evidenced host networks and prefer a specific overlapping CIDR', () => {
  const network = { interfaces: [
    { name: 'lan0', role: 'uplink', type: 'ether', addresses: ['192.168.1.25/24'] },
    { name: 'lan0.20', role: 'virtual', type: 'vlan', vlan_id: 20, addresses: ['192.168.1.1/25'] },
    { name: 'br-docker', role: 'container_bridge', type: 'bridge', addresses: ['172.17.0.1/16'] },
    { name: 'lo', addresses: ['127.0.0.1/8'] },
  ] };
  const devices = [
    { ip: '192.168.1.12', ip_addresses: ['192.168.1.12'], state: 'online', online: true },
    { ip: '192.168.1.200', state: 'recently_seen', online: false },
    { ip: '192.168.1.15', state: 'known', online: false },
    { ip: '172.17.0.9', state: 'online', online: true },
  ];
  const result = networkSegments(network, devices);
  assert.equal(result.length, 2);
  assert.deepEqual(result.map(({ cidr, total, online, vlanId }) => ({ cidr, total, online, vlanId })),
    [
      { cidr: '192.168.1.0/24', total: 1, online: 0, vlanId: null },
      { cidr: '192.168.1.0/25', total: 1, online: 1, vlanId: 20 },
    ]);
  assert.deepEqual(networkSegments({}, devices), []);
});

test('management links only accept verified local IPv4 and supported open web ports', () => {
  assert.deepEqual(serviceManagementLinks('192.168.1.20', [{ port: 443 }, { port: 8123 }, { port: 8123 }, { port: 22 }]),
    [{ port: 443, scheme: 'https', href: 'https://192.168.1.20/' }, { port: 8123, scheme: 'http', href: 'http://192.168.1.20:8123/' }]);
  assert.deepEqual(serviceManagementLinks('203.0.113.2', [{ port: 80 }]), []);
  assert.deepEqual(serviceManagementLinks('127.0.0.1', [{ port: 80 }]), []);
  assert.deepEqual(serviceManagementLinks('192.168.1.1@evil.test', [{ port: 443 }]), []);
  assert.deepEqual(serviceManagementLinks('192.168.1.2', [{ port: 22 }, { port: 65535 }]), []);
  assert.deepEqual(serviceManagementLinks('172.30.5.4', [{ port: 8080 }]).map((x) => x.href), ['http://172.30.5.4:8080/']);
});
