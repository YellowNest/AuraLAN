import test from 'node:test';
import assert from 'node:assert/strict';
import { focusBoardModel } from '../js/focus.js';

const favorite = (id, state, online, alias) => ({
  id, state, online, metadata: { favorite: true, alias },
});

test('distinguishes observed, last-seen-only and unconfirmed devices', () => {
  const result = focusBoardModel([
    favorite('online', 'current', true, 'Living Room'),
    favorite('absent', 'known', false, 'Router'),
    favorite('uncertain', 'current', false, 'Camera'),
    { id: 'ordinary', metadata: { favorite: false }, online: true },
  ]);
  assert.deepEqual([result.total, result.online, result.notSeen, result.unconfirmed], [3, 1, 1, 1]);
  assert.deepEqual(result.items.map(({ device, status }) => [device.id, status]), [
    ['absent', 'not_seen'], ['uncertain', 'unconfirmed'], ['online', 'online'],
  ]);
});

test('positive online evidence takes precedence over known state', () => {
  assert.equal(focusBoardModel([favorite('x', 'known', true, 'Example')]).items[0].status, 'online');
});

test('limits visible items without changing totals and sorts naturally', () => {
  const result = focusBoardModel([
    favorite('3', 'known', false, 'Node 10'),
    favorite('1', 'known', false, 'Node 2'),
    favorite('2', 'known', false, 'Node 1'),
  ], 2);
  assert.equal(result.total, 3);
  assert.equal(result.remaining, 1);
  assert.deepEqual(result.items.map(({ device }) => device.id), ['2', '1']);
});

test('empty or malformed responses degrade gracefully', () => {
  assert.deepEqual(focusBoardModel(null).items, []);
  assert.equal(focusBoardModel([null, {}, { metadata: { favorite: 'true' } }]).total, 0);
  assert.equal(focusBoardModel([favorite('x', 'known', false, 'X')], NaN).items.length, 1);
});
