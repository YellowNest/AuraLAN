import test from 'node:test';
import assert from 'node:assert/strict';
import { ipv4Cidr, networkSegments, serviceManagementLinks } from '../js/network-tools.js';

const privateIp = (...octets) => octets.join('.');

test('IPv4 CIDR parsing handles prefix, zero network, and malformed addresses', () => {
  assert.equal(ipv4Cidr('198.51.100.42/24')?.cidr, '198.51.100.0/24');
  assert.equal(ipv4Cidr('203.0.113.5/32')?.cidr, '203.0.113.5/32');
  assert.equal(ipv4Cidr('0.0.0.0/0')?.cidr, '0.0.0.0/0');
  for (const candidate of ['198.51.100/24', '198.51.256.3/24', '198.51.100.1/33', '2001:db8::1/64', '198.51.100.1/24/', '', null]) {
    assert.equal(ipv4Cidr(candidate), null, String(candidate));
  }
});

test('subnets keep only evidenced networks and prefer the most specific overlapping CIDR', () => {
  const network = { interfaces: [
    { name: 'lan0', role: 'uplink', type: 'ether', addresses: ['198.51.100.25/24'] },
    { name: 'lan0.20', role: 'virtual', type: 'vlan', vlan_id: 20, addresses: ['198.51.100.1/25'] },
    { name: 'br-docker', role: 'container_bridge', type: 'bridge', addresses: ['203.0.113.1/24'] },
    { name: 'lo', addresses: ['127.0.0.1/8'] },
  ] };
  const devices = [
    { ip: '198.51.100.12', ip_addresses: ['198.51.100.12'], state: 'online', online: true },
    { ip: '198.51.100.200', state: 'recently_seen', online: false },
    { ip: '198.51.100.15', state: 'known', online: false },
    { ip: '203.0.113.9', state: 'online', online: true },
  ];
  const result = networkSegments(network, devices);
  assert.deepEqual(result.map(({ cidr, total, online, vlanId }) => ({ cidr, total, online, vlanId })),
    [
      { cidr: '198.51.100.0/24', total: 1, online: 0, vlanId: null },
      { cidr: '198.51.100.0/25', total: 1, online: 1, vlanId: 20 },
    ]);
  assert.deepEqual(networkSegments({}, devices), []);
});

test('management links only accept local IPv4 and supported open web ports', () => {
  const host = privateIp(192, 168, 1, 20);
  const expected = `https://${host}/`;
  assert.deepEqual(serviceManagementLinks(host, [{ port: 443 }, { port: 8123 }, { port: 8123 }, { port: 22 }]),
    [{ port: 443, scheme: 'https', href: expected }, { port: 8123, scheme: 'http', href: `http://${host}:8123/` }]);
  assert.deepEqual(serviceManagementLinks('203.0.113.2', [{ port: 80 }]), []);
  assert.deepEqual(serviceManagementLinks('127.0.0.1', [{ port: 80 }]), []);
  assert.deepEqual(serviceManagementLinks(host + '@evil.test', [{ port: 443 }]), []);
  assert.deepEqual(serviceManagementLinks(host, [{ port: 22 }, { port: 65535 }]), []);
  const second = privateIp(172, 30, 5, 4);
  assert.deepEqual(serviceManagementLinks(second, [{ port: 8080 }]).map((x) => x.href), [`http://${second}:8080/`]);
});
