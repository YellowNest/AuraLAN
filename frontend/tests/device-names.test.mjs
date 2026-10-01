import test from 'node:test';
import assert from 'node:assert/strict';

import {
  friendlyDeviceContext,
  friendlyDeviceListIdentity,
  friendlyDeviceName,
  isTechnicalDeviceName,
  prettifyDeviceName,
} from '../js/device-names.js';

test('manual alias always wins and is preserved exactly', () => {
  const device = {
    display_name: 'living-room-tv',
    hostname: 'living-room-tv',
    category: 'tv',
    vendor: 'Samsung',
    metadata: { alias: 'Living room TV' },
  };
  assert.equal(friendlyDeviceName(device, { categoryName: 'TV' }), 'Living room TV');
});

test('hostnames become friendly product-aware labels', () => {
  assert.equal(prettifyDeviceName('sample-iphone.local'), 'Sample iPhone');
  assert.equal(prettifyDeviceName('living_room_tv'), 'Living room TV');
  assert.equal(prettifyDeviceName('esp32-a81f23'), 'ESP32');
});

test('localized Apple TV discovery names are normalized', () => {
  assert.equal(prettifyDeviceName('Apple de TV, Living Room'), 'Apple TV, Living Room');
});

test('technical identifiers never become the primary visible name', () => {
  assert.equal(isTechnicalDeviceName('192.0.2.204'), true);
  assert.equal(isTechnicalDeviceName('02:00:00:00:00:01'), true);
  assert.equal(prettifyDeviceName('192.0.2.204'), '');
});

test('vendor and type provide a human fallback', () => {
  const device = {
    display_name: '192.0.2.204',
    hostname: null,
    category: 'tv',
    vendor: 'Samsung',
    metadata: {},
  };
  assert.equal(friendlyDeviceName(device, { categoryName: 'TV' }), 'Samsung · TV');
});

test('Apple device families get familiar names when no hostname exists', () => {
  const phone = { display_name: '192.0.2.10', category: 'phone', vendor: 'Apple', metadata: {} };
  const tablet = { display_name: '192.0.2.11', category: 'tablet', vendor: 'Apple', metadata: {} };
  assert.equal(friendlyDeviceName(phone, { categoryName: 'Phone' }), 'iPhone');
  assert.equal(friendlyDeviceName(tablet, { categoryName: 'Tablet' }), 'iPad');
});

test('context keeps manufacturer and type visible under friendly names', () => {
  const device = { category: 'tv', vendor: 'Samsung', model: 'QE65Q70T' };
  assert.equal(friendlyDeviceContext(device, 'Living Room TV', 'TV'), 'Samsung · TV');
  assert.equal(friendlyDeviceContext(device, 'Samsung QE65Q70T TV', 'TV'), 'Samsung · TV');
});

test('device-list identity keeps the full MAC visible before manufacturer context', () => {
  const device = { vendor: 'Apple', mac: '02:00:00:00:00:51', category: 'tv' };
  assert.equal(friendlyDeviceListIdentity(device), '02:00:00:00:00:51 · Apple');
  assert.equal(friendlyDeviceListIdentity({ vendor: 'Meross', mac: '02:00:00:00:00:52' }), '02:00:00:00:00:52 · Meross');
});


test('low-confidence backend fallbacks are replaced by localized connection names', () => {
  const device = {
    display_name: 'Network device',
    hostname: null,
    category: 'unknown',
    connection_type: 'wifi',
    vendor: null,
    metadata: {},
    identity: {
      display_name: { value: 'Network device', source: 'heuristic', confidence: 'low' },
    },
  };
  assert.equal(friendlyDeviceName(device, {
    categoryName: '',
    wifiDevice: 'Wi-Fi-enhet',
    networkDevice: 'Nätverksenhet',
  }), 'Wi-Fi-enhet');
  assert.equal(friendlyDeviceContext(device, 'Wi-Fi-enhet', ''), '');
});

test('localized smart-home type stays concise in the list', () => {
  const device = {
    display_name: 'Smart device',
    hostname: null,
    category: 'smart_home',
    connection_type: 'wifi',
    vendor: null,
    metadata: {},
    identity: {
      display_name: { value: 'Smart device', source: 'heuristic', confidence: 'low' },
    },
  };
  assert.equal(friendlyDeviceName(device, {
    categoryName: 'Smart enhet',
    unnamedType: (type) => type,
    wifiDevice: 'Wi-Fi-enhet',
  }), 'Smart enhet');
});


test('private MAC devices explain why vendor lookup may be unavailable', () => {
  const device = {
    display_name: 'Network device',
    hostname: null,
    category: 'unknown',
    connection_type: 'unknown',
    vendor: null,
    mac: '02:00:00:00:00:44',
    mac_type: 'private',
    metadata: {},
    identity: {
      display_name: { value: 'Network device', source: 'heuristic', confidence: 'low' },
    },
  };
  assert.equal(friendlyDeviceName(device, {
    categoryName: '',
    privateDevice: 'Enhet med privat MAC',
    networkDevice: 'Nätverksenhet',
  }), 'Enhet med privat MAC');
  assert.equal(
    friendlyDeviceListIdentity(device, { privateMac: 'Privat MAC' }),
    '02:00:00:00:00:44 · Privat MAC',
  );
});
