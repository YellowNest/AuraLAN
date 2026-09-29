import test from 'node:test';
import assert from 'node:assert/strict';

import { deviceIconKey, isKnownDeviceIconKey } from '../js/device-icons.js';

test('backend icon key wins for Apple TV regardless of display name', () => {
  for (const display_name of [
    'Apple de TV, Living Room',
    'Apple TV, Guest Room',
    'Apple TV, Bedroom',
  ]) {
    assert.equal(deviceIconKey({
      display_name,
      vendor: 'Apple',
      category: 'unknown',
      icon_key: 'apple_tv',
    }), 'apple_tv');
  }
});

test('legacy Apple TV payloads use resolved vendor and category, not display-text guessing', () => {
  assert.equal(deviceIconKey({
    display_name: 'Living Room',
    vendor: 'Apple',
    category: 'tv',
  }), 'apple_tv');
  assert.equal(deviceIconKey({
    display_name: 'Apple anything',
    vendor: 'Apple',
    category: 'unknown',
  }), 'device_generic');
});

test('legacy product-family fallback stays narrow and representative', () => {
  assert.equal(deviceIconKey({ vendor: 'Roborock', category: 'smart_home' }), 'vacuum');
  assert.equal(deviceIconKey({ vendor: 'Meross', category: 'smart_home', metadata: { alias: 'Garage Door' } }), 'garage');
  assert.equal(deviceIconKey({ vendor: 'Espressif', category: 'microcontroller', metadata: { alias: 'Heat Pump' } }), 'heat_pump');
  assert.equal(deviceIconKey({ vendor: 'Meta', category: 'unknown', metadata: { alias: 'VR' } }), 'vr_headset');
});

test('category fallback stays deterministic and icon keys are validated', () => {
  assert.equal(deviceIconKey({ category: 'camera' }), 'camera');
  assert.equal(deviceIconKey({ category: 'smart_home' }), 'iot');
  assert.equal(deviceIconKey({ category: 'unknown' }), 'device_generic');
  assert.equal(isKnownDeviceIconKey('apple_tv'), true);
  assert.equal(isKnownDeviceIconKey('vacuum'), true);
  assert.equal(isKnownDeviceIconKey('vr_headset'), true);
  assert.equal(isKnownDeviceIconKey('apple'), false);
});
