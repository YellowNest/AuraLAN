import test from 'node:test';
import assert from 'node:assert/strict';
import { exploreNetworkMap, filterDevices, groupCurrentDevicesByConnection, identityCoverage, identityQuality, inventoryCsv, inventoryExportRows, isFavoriteNotSeen, isNewDevice, networkHistorySummary, networkMapInfrastructure, networkMapAccessPoints, partitionNetworkMapDevices, networkReviewQueue, sortDevices, visibleServiceItems } from '../js/data.js';
import { preferredLocale, translate } from '../js/i18n.js';

const devices = [
  { display_name: 'Sample iPhone', hostname: 'SAMPLE-IPHONE', vendor: 'Apple', category: 'phone', ip: '192.0.2.10', mac: '02:00:00:00:00:01', interface: 'wifi-ap', connection_type: 'wifi', online: true },
  { display_name: 'Living room TV', hostname: 'living-room-tv', vendor: 'Samsung', model: 'QE65Q70T', category: 'tv', ip: '192.0.2.20', mac: '02:00:00:00:00:02', interface: 'lan0', connection_type: 'ethernet', online: false },
  { display_name: 'Network device', vendor: null, model: null, category: 'unknown', ip: '192.0.2.30', mac: '02:00:00:00:00:03', interface: 'lan0', connection_type: 'ethernet', online: false, metadata: { alias: null } }
];


test('network topology keeps the upstream gateway separate from the local Wi-Fi AP', () => {
  const network = {
    uplink: { gateway: '192.0.2.1', ipv4: '192.0.2.44' },
    access_point: { available: true, ssid: 'Lab-Pi', ipv4: '198.51.100.1' },
  };
  assert.deepEqual(networkMapInfrastructure(network), {
    gatewayAddress: '192.0.2.1',
    accessPoint: { name: 'Lab-Pi', address: '198.51.100.1' },
  });
  assert.deepEqual(networkMapInfrastructure({
    uplink: { gateway: '192.0.2.1' },
    access_point: { available: false, ssid: 'Inactive AP', ipv4: '198.51.100.1' },
  }), {
    gatewayAddress: '192.0.2.1',
    accessPoint: null,
  });
  assert.deepEqual(networkMapInfrastructure({}), { gatewayAddress: null, accessPoint: null });
});

test('network map shows two different access points but never invents router-side associations', () => {
  const network = {
    uplink: { gateway: '192.0.2.1' },
    access_point: { available: true, ssid: 'Host AP', ipv4: '198.51.100.1/24', interface: 'hotspot-if' },
    known_access_points: [
      { ssid: 'Main Wi-Fi', address: '192.0.2.1', label: 'Gateway device' },
      { ssid: 'Workshop Wi-Fi', address: '192.0.2.9', label: 'Workshop' },
      { ssid: 'Duplicate', address: '192.0.2.1' },
      { ssid: 'Already local', address: '198.51.100.1' },
    ],
  };
  assert.deepEqual(networkMapAccessPoints(network), [
    { ssid: 'Host AP', address: '198.51.100.1/24', label: null, kind: 'local', gateway: false },
    { ssid: 'Main Wi-Fi', address: '192.0.2.1', label: 'Gateway device', kind: 'configured', gateway: true },
    { ssid: 'Workshop Wi-Fi', address: '192.0.2.9', label: 'Workshop', kind: 'configured', gateway: false },
  ]);
  const inventory = [
    { id: 'ap', state: 'online', connection_type: 'wifi', observations: [{ source: 'wifi_station', interface: 'hotspot-if' }] },
    { id: 'gateway-lan', state: 'online', connection_type: 'unknown', ip: '192.0.2.23', observations: [{ source: 'ip_neigh', interface: 'lan-uplink' }] },
  ];
  const partition = partitionNetworkMapDevices(network, inventory);
  assert.deepEqual(partition.apClients.map((x) => x.id), ['ap']);
  assert.deepEqual(partition.other.unknown.map((x) => x.id), ['gateway-lan']);
});

test('Network Explorer searches across network evidence without inventing associations', () => {
  const network = {
    access_point: { available: true, interface: 'local-ap', ssid: 'Local Lab', ipv4: '198.51.100.1/24' },
    known_access_points: [{ ssid: 'External Router', address: '192.0.2.1', label: 'Gateway' }],
  };
  const inventory = [
    { id: 'heat', state: 'online', online: true, display_name: 'Värmepump', vendor: 'Daikin', ip: '198.51.100.2', connection_type: 'wifi', observations: [{ source: 'wifi_station', interface: 'local-ap' }] },
    { id: 'tv', state: 'online', online: true, display_name: 'Apple TV', ip: '192.0.2.102', connection_type: 'unknown', observations: [{ source: 'ip_neigh', interface: 'uplink' }] },
    { id: 'camera', state: 'recently_seen', online: false, display_name: 'Kamera', ip: '192.0.2.105', connection_type: 'unknown', observations: [] },
    { id: 'remembered', state: 'known', online: false, display_name: 'Old', connection_type: 'wifi', observations: [{ source: 'wifi_station', interface: 'local-ap' }] },
  ];
  const all = exploreNetworkMap(network, inventory);
  assert.deepEqual(all.counts, { total: 3, local: 1, unassigned: 2, online: 2 });
  assert.equal(all.matched, 3);
  assert.deepEqual(exploreNetworkMap(network, inventory, 'DAIKIN', 'all').apClients.map((d) => d.id), ['heat']);
  assert.deepEqual(exploreNetworkMap(network, inventory, 'varmepump', 'all').apClients.map((d) => d.id), ['heat']);
  assert.deepEqual(exploreNetworkMap(network, inventory, '192.0.2.102', 'unassigned').other.unknown.map((d) => d.id), ['tv']);
  assert.deepEqual(exploreNetworkMap(network, inventory, '', 'local').other.unknown, []);
  assert.deepEqual(exploreNetworkMap(network, inventory, '', 'online').other.unknown.map((d) => d.id), ['tv']);
  assert.equal(exploreNetworkMap(network, inventory, 'missing', 'all').matched, 0);
  assert.equal(exploreNetworkMap(network, inventory, '', 'malformed').view, 'all');
  assert.equal(all.counts.total, 3, 'search and filters must not alter the source inventory');
});

test('network map remains meaningful with no declared external APs', () => {
  assert.deepEqual(networkMapAccessPoints({}), []);
  assert.deepEqual(networkMapAccessPoints({ uplink: { gateway: '192.0.2.1' } }), []);
  assert.equal(networkMapAccessPoints({ access_point: { available: true, ssid: 'Local' } }).length, 1);
});

test('device filtering supports friendly names, vendor, category, IP, and MAC', () => {
  assert.equal(filterDevices(devices, 'online').length, 1);
  assert.equal(filterDevices(devices, 'wifi', '02:00:00:00:00:01')[0].display_name, 'Sample iPhone');
  assert.equal(filterDevices(devices, 'all', 'samsung')[0].display_name, 'Living room TV');
  assert.equal(filterDevices(devices, 'all', 'qe65q70t')[0].display_name, 'Living room TV');
  assert.equal(filterDevices(devices, 'unknown').length, 1);
});

test('search combines independent fields, ignores accents, and respects filters', () => {
  const inventory = [
    { display_name: 'Värmepump', vendor: 'Daikin', category: 'smart_home', connection_type: 'wifi', online: true, metadata: { location: 'Kök', tags: ['klimat'] } },
    { display_name: 'TV i vardagsrum', vendor: 'Samsung', category: 'tv', connection_type: 'ethernet', online: false, metadata: { note: 'Filmkväll' } },
  ];
  assert.deepEqual(filterDevices(inventory, 'all', 'DAIKIN kök').map((device) => device.vendor), ['Daikin']);
  assert.deepEqual(filterDevices(inventory, 'all', 'varmepump klimat').map((device) => device.vendor), ['Daikin']);
  assert.deepEqual(filterDevices(inventory, 'all', 'samsung filmkvall').map((device) => device.vendor), ['Samsung']);
  assert.deepEqual(filterDevices(inventory, 'wifi', 'klimat daikin').map((device) => device.vendor), ['Daikin']);
  assert.deepEqual(filterDevices(inventory, 'online', 'samsung').map((device) => device.vendor), []);
  assert.deepEqual(filterDevices(inventory, 'all', 'kök saknas'), []);
  assert.equal(filterDevices(inventory, 'all', '  ').length, 2);
  assert.equal(filterDevices(inventory, 'all', 'VARMEPUMP').length, 1);
});

test('identity quality distinguishes evidence-rich and unidentified devices', () => {
  const strong = {
    display_name: 'Living Room TV',
    hostname: 'living-room-tv',
    vendor: 'Example',
    model: 'MediaBox X',
    category: 'tv',
    metadata: {},
    identity: {
      display_name: { value: 'Living Room TV', source: 'dns_sd', confidence: 'medium' },
      sources: [{ source: 'dns_sd', confidence: 'medium' }, { source: 'oui_vendor', confidence: 'high' }],
    },
  };
  const limited = {
    display_name: 'Network device',
    hostname: null,
    vendor: null,
    model: null,
    category: 'unknown',
    metadata: {},
    identity: {
      display_name: { value: 'Network device', source: 'heuristic', confidence: 'low' },
      sources: [{ source: 'ip_neigh', confidence: 'medium' }],
    },
  };

  assert.equal(identityQuality(strong).level, 'strong');
  assert.equal(identityQuality(limited).level, 'limited');
  assert.equal(identityQuality({
    display_name: 'My device',
    category: 'unknown',
    metadata: { alias: 'My device' },
    identity: {
      display_name: { value: 'My device', source: 'manual_alias', confidence: 'high' },
      sources: [{ source: 'manual_alias', confidence: 'high' }],
    },
  }).level, 'strong');
  assert.equal(filterDevices([strong, limited], 'identity_limited').length, 1);

  const coverage = identityCoverage([strong, limited]);
  assert.equal(coverage.total, 2);
  assert.equal(coverage.strong, 1);
  assert.equal(coverage.limited, 1);
  assert.ok(coverage.score > 0 && coverage.score < 100);
});

test('device inventory supports new, favorite, and note discovery', () => {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const inventory = [
    {
      display_name: 'NAS',
      category: 'server',
      ip: '192.0.2.40',
      mac: '02:00:00:00:00:04',
      connection_type: 'ethernet',
      first_seen_at: nowSeconds - 3600,
      metadata: { favorite: true, note: 'Backup target', location: 'Office', tags: ['storage', 'critical'] },
    },
    {
      display_name: 'Old tablet',
      category: 'tablet',
      ip: '192.0.2.41',
      mac: '02:00:00:00:00:05',
      connection_type: 'wifi',
      first_seen_at: nowSeconds - (3 * 24 * 60 * 60),
      metadata: { favorite: false, note: null },
    },
  ];

  assert.equal(isNewDevice(inventory[0], nowSeconds * 1000), true);
  assert.equal(isNewDevice(inventory[1], nowSeconds * 1000), false);
  assert.equal(filterDevices(inventory, 'new').length, 1);
  assert.equal(filterDevices(inventory, 'favorites')[0].display_name, 'NAS');
  assert.equal(filterDevices(inventory, 'all', 'backup target')[0].display_name, 'NAS');
  assert.equal(filterDevices(inventory, 'all', 'office')[0].display_name, 'NAS');
  assert.equal(filterDevices(inventory, 'all', 'critical')[0].display_name, 'NAS');

  const remembered = {
    display_name: 'Old camera',
    category: 'camera',
    ip: '192.0.2.42',
    mac: '02:00:00:00:00:06',
    connection_type: 'wifi',
    state: 'known',
    metadata: {},
  };
  assert.equal(filterDevices([...inventory, remembered], 'known')[0].display_name, 'Old camera');
});

test('baseline filters distinguish new and missing devices', () => {
  const items = [
    { display_name: 'Known', category: 'computer', connection_type: 'ethernet', baseline_state: 'member', metadata: {} },
    { display_name: 'New', category: 'phone', connection_type: 'wifi', baseline_state: 'new', metadata: {} },
    { display_name: 'Missing', category: 'camera', connection_type: 'wifi', baseline_state: 'missing', metadata: {} },
  ];

  assert.deepEqual(filterDevices(items, 'baseline_new').map((item) => item.display_name), ['New']);
  assert.deepEqual(filterDevices(items, 'baseline_missing').map((item) => item.display_name), ['Missing']);
});

test('device sorting supports name, recency, location, and IP without mutating source order', () => {
  const source = [
    { display_name: 'Zulu', presentation_name: 'Zulu', ip: '192.0.2.20', first_seen_at: 100, last_seen_at: 200, metadata: { location: 'Office' } },
    { display_name: 'Alpha', presentation_name: 'Alpha', ip: '192.0.2.3', first_seen_at: 300, last_seen_at: 150, metadata: { location: 'Kitchen' } },
    { display_name: 'Beta', presentation_name: 'Beta', ip: '192.0.2.10', first_seen_at: 200, last_seen_at: 400, metadata: {} },
  ];

  assert.deepEqual(sortDevices(source, 'name').map((item) => item.display_name), ['Alpha', 'Beta', 'Zulu']);
  assert.deepEqual(sortDevices(source, 'last_seen').map((item) => item.display_name), ['Beta', 'Zulu', 'Alpha']);
  assert.deepEqual(sortDevices(source, 'first_seen').map((item) => item.display_name), ['Alpha', 'Beta', 'Zulu']);
  assert.deepEqual(sortDevices(source, 'location').map((item) => item.display_name), ['Alpha', 'Zulu', 'Beta']);
  assert.deepEqual(sortDevices(source, 'ip').map((item) => item.display_name), ['Alpha', 'Beta', 'Zulu']);
  assert.deepEqual(source.map((item) => item.display_name), ['Zulu', 'Alpha', 'Beta']);
});

test('network map groups current devices without reviving remembered devices', () => {
  const items = [
    { display_name: 'Phone', connection_type: 'wifi', state: 'online', metadata: {} },
    { display_name: 'Desktop', connection_type: 'ethernet', state: 'online', metadata: {} },
    { display_name: 'VPN client', connection_type: 'vpn', state: 'online', metadata: {} },
    { display_name: 'Mystery', connection_type: 'unknown', state: 'recently_seen', metadata: {} },
    { display_name: 'Old camera', connection_type: 'wifi', state: 'known', metadata: {} },
  ];

  const groups = groupCurrentDevicesByConnection(items);
  assert.equal(groups.wifi.length, 1);
  assert.equal(groups.ethernet.length, 1);
  assert.equal(groups.vpn.length, 1);
  assert.equal(groups.unknown.length, 1);
  assert.equal(filterDevices(items, 'connection_unknown')[0].display_name, 'Mystery');
});

test('network topology places only observed clients under the local AP, even with many devices', () => {
  const localAp = { access_point: { available: true, interface: 'hotspot-if', ssid: 'Test-Pi', ipv4: '198.51.100.1' } };
  const clients = Array.from({ length: 8 }, (_, index) => ({
    id: `local-${index}`, state: 'online', connection_type: 'wifi',
    observations: [{ source: index % 2 ? 'wifi_station' : 'ip_neigh', interface: 'hotspot-if' }],
  }));
  const otherDevices = [
    { id: 'router-side', state: 'online', connection_type: 'unknown', ip: '192.0.2.25', observations: [{ source: 'ip_neigh', interface: 'uplink-if' }] },
    { id: 'other-wifi', state: 'online', connection_type: 'wifi', observations: [{ source: 'wifi_station', interface: 'other-ap-if' }] },
    { id: 'vpn-peer', state: 'online', connection_type: 'vpn', observations: [] },
    { id: 'legacy-ap-client', state: 'online', connection_type: 'wifi', interface: 'hotspot-if', observations: [] },
    { id: 'ambiguous-legacy', state: 'online', connection_type: 'wifi', observations: [] },
    { id: 'remembered', state: 'known', connection_type: 'wifi', observations: [{ source: 'wifi_station', interface: 'hotspot-if' }] },
  ];
  const original = [...clients, ...otherDevices];
  const result = partitionNetworkMapDevices(localAp, original);
  assert.equal(result.apClients.length, 9);
  assert.equal(result.other.unknown.length, 1);
  assert.equal(result.other.wifi.length, 2);
  assert.equal(result.other.vpn.length, 1);
  assert.equal(result.other.ethernet.length, 0);
  assert.equal(result.apClients.some((device) => device.id === 'remembered'), false);
  assert.equal(result.apClients.some((device) => device.id === 'other-wifi'), false);
  assert.equal(original.length, 14, 'the source array must remain unchanged');
  assert.deepEqual(partitionNetworkMapDevices({ access_point: { available: false, interface: 'hotspot-if' } }, clients).apClients, []);
  assert.deepEqual(partitionNetworkMapDevices({}, clients).apClients, []);
});

test('network topology never infers AP membership from matching IP ranges', () => {
  const network = { access_point: { available: true, interface: 'hotspot-if', ipv4: '198.51.100.1' } };
  const device = { id: 'unverified', state: 'online', ip: '198.51.100.27', connection_type: 'unknown',
    observations: [{ source: 'ip_neigh', interface: 'uplink-if' }] };
  const result = partitionNetworkMapDevices(network, [device]);
  assert.equal(result.apClients.length, 0);
  assert.equal(result.other.unknown.length, 1);
});

test('inventory export is stable, private-data explicit, and CSV-safe', () => {
  const items = [{
    presentation_name: '=HYPERLINK("https://example.invalid","sensor")',
    hostname: 'sensor.local',
    vendor: 'Example',
    model: 'T1',
    category: 'iot',
    state: 'known',
    online: null,
    connection_type: 'wifi',
    ip_addresses: ['192.0.2.55'],
    mac_addresses: ['02:00:00:00:00:55'],
    first_seen_at: 100,
    last_seen_at: 200,
    metadata: { favorite: true, note: 'Kitchen, shelf', location: 'Kitchen', tags: ['sensor', 'climate'] },
  }];

  const rows = inventoryExportRows(items);
  assert.equal(rows[0].name, '=HYPERLINK("https://example.invalid","sensor")');
  assert.equal(rows[0].note, 'Kitchen, shelf');
  assert.deepEqual(rows[0].ip_addresses, ['192.0.2.55']);
  assert.equal(rows[0].location, 'Kitchen');
  assert.deepEqual(rows[0].tags, ['sensor', 'climate']);

  const csv = inventoryCsv(items);
  assert.match(csv, /"'=HYPERLINK\(""https:\/\/example\.invalid"",""sensor""\)"/);
  assert.match(csv, /"Kitchen, shelf"/);
  assert.match(csv, /"02:00:00:00:00:55"/);
  assert.match(csv, /"Kitchen"/);
  assert.match(csv, /"sensor \| climate"/);
});

test('favorite devices become a watchlist only when they are not currently seen', () => {
  const currentFavorite = { display_name: 'NAS', state: 'online', connection_type: 'ethernet', metadata: { favorite: true } };
  const missingFavorite = { display_name: 'Camera', state: 'known', connection_type: 'wifi', metadata: { favorite: true } };
  const ordinaryRemembered = { display_name: 'Tablet', state: 'known', connection_type: 'wifi', metadata: { favorite: false } };

  assert.equal(isFavoriteNotSeen(currentFavorite), false);
  assert.equal(isFavoriteNotSeen(missingFavorite), true);
  assert.equal(isFavoriteNotSeen(ordinaryRemembered), false);
  assert.deepEqual(
    filterDevices([currentFavorite, missingFavorite, ordinaryRemembered], 'favorite_missing').map((item) => item.display_name),
    ['Camera'],
  );
});

test('absent optional integrations are not rendered as offline cards', () => {
  assert.deepEqual(visibleServiceItems([{ id: 'docker', detected: true }, { id: 'caddy', detected: false }]).map((item) => item.id), ['docker']);
});

test('i18n selects a supported locale and interpolates values', () => {
  assert.equal(preferredLocale('sv'), 'sv');
  assert.equal(translate('en', 'deviceCount', { count: 3 }), '3 devices');
});


test('device search includes secondary MAC addresses from a multi-NIC host', () => {
  const items = [{
    display_name: 'Office PC',
    hostname: 'OFFICE-PC',
    category: 'computer',
    device_type: 'computer',
    ip: '192.0.2.187',
    ip_addresses: ['192.0.2.187', '192.0.2.113'],
    mac: '02:00:00:00:10:02',
    mac_addresses: ['02:00:00:00:10:02', '02:00:00:00:10:01'],
    connection_type: 'unknown',
    metadata: {},
  }];
  assert.equal(filterDevices(items, 'all', '02:00:00:00:10:01').length, 1);
  assert.equal(filterDevices(items, 'all', '192.0.2.113').length, 1);
});


test('network review queue prioritizes actionable local signals without inventing security verdicts', () => {
  const nowSeconds = 2_000_000;
  const inventory = [
    {
      display_name: 'Camera',
      category: 'camera',
      state: 'known',
      first_seen_at: nowSeconds - 500_000,
      metadata: { favorite: true },
      identity: { display_name: { confidence: 'medium' }, sources: [] },
    },
    {
      display_name: 'New phone',
      category: 'phone',
      state: 'online',
      first_seen_at: nowSeconds - 3600,
      metadata: {},
      vendor: 'Example',
      identity: {
        display_name: { confidence: 'high' },
        device_type: { confidence: 'high' },
        sources: [{ confidence: 'high' }],
      },
    },
    {
      display_name: 'Mystery',
      category: 'unknown',
      state: 'online',
      first_seen_at: nowSeconds - 500_000,
      metadata: {},
      identity: { display_name: { confidence: 'low' }, sources: [{ confidence: 'medium' }] },
    },
  ];

  const queue = networkReviewQueue({
    devices: inventory,
    baseline: { new_count: 1, missing_count: 2 },
    activity: [
      { event_type: 'service_exposure_changed' },
      { event_type: 'device_first_seen' },
    ],
    services: [
      { detected: true, state: 'offline' },
      { detected: true, state: 'online' },
      { detected: false, state: 'offline' },
    ],
  }, nowSeconds * 1000);

  assert.deepEqual(
    queue.map((item) => [item.id, item.count]),
    [
      ['favorite_missing', 1],
      ['baseline_new', 1],
      ['baseline_missing', 2],
      ['identity_limited', 1],
      ['service_health', 1],
      ['service_changes', 1],
      ['new_devices', 1],
    ],
  );
  assert.equal(queue.find((item) => item.id === 'service_changes').route, 'activity');
  assert.equal(queue.find((item) => item.id === 'service_changes').filter, 'services');
});

test('network review queue is empty when current state has nothing worth review', () => {
  const queue = networkReviewQueue({
    devices: [{
      display_name: 'NAS',
      hostname: 'nas',
      vendor: 'Example',
      model: 'Storage',
      category: 'server',
      state: 'online',
      first_seen_at: 100,
      metadata: { favorite: false },
      identity: {
        display_name: { confidence: 'high' },
        device_type: { confidence: 'high' },
        sources: [{ confidence: 'high' }],
      },
    }],
    baseline: { new_count: 0, missing_count: 0 },
    activity: [],
    services: [{ detected: true, state: 'online' }],
  }, 3_000_000_000);

  assert.deepEqual(queue, []);
});


test('network history summary stays aggregate, ordered, and health-aware', () => {
  const summary = networkHistorySummary([
    { bucket_start: 200, current_devices: 5, online_devices: 4, remembered_devices: 1, services_offline: 1, discovery_errors: 0, system_state: 'degraded' },
    { bucket_start: 100, current_devices: 4, online_devices: 4, remembered_devices: 0, services_offline: 0, discovery_errors: 0, system_state: 'healthy' },
    { bucket_start: 300, current_devices: 6, online_devices: 6, remembered_devices: 1, services_offline: 0, discovery_errors: 0, system_state: 'healthy' },
  ]);

  assert.deepEqual(summary.samples.map((item) => item.bucket_start), [100, 200, 300]);
  assert.equal(summary.min_current, 4);
  assert.equal(summary.max_current, 6);
  assert.equal(summary.current_delta, 2);
  assert.equal(summary.healthy_percent, 67);
  assert.equal(summary.attention_samples, 1);
  assert.equal(summary.first_at, 100);
  assert.equal(summary.last_at, 300);
});

test('network history summary has safe empty defaults', () => {
  assert.deepEqual(networkHistorySummary([]), {
    samples: [],
    min_current: 0,
    max_current: 0,
    current_delta: 0,
    healthy_percent: 0,
    attention_samples: 0,
    first_at: null,
    last_at: null,
  });
});
