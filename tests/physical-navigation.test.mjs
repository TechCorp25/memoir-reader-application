import test from 'node:test';
import assert from 'node:assert/strict';
import {
  normalizePhysicalAnchor,
  turnPhysical,
  visiblePhysicalPageIndexes,
} from '../static/js/navigation.js';

test('wide book begins with a singleton front cover', () => {
  assert.deepEqual(visiblePhysicalPageIndexes(0, 'spread', 113), [0]);
});

test('opening the cover exposes physical pages 2 and 3', () => {
  const next = turnPhysical(0, 'forward', 'spread', 113);
  assert.equal(next, 1);
  assert.deepEqual(visiblePhysicalPageIndexes(next, 'spread', 113), [1, 2]);
});

test('spread turns advance exactly one bound-book spread', () => {
  assert.equal(turnPhysical(1, 'forward', 'spread', 113), 3);
  assert.deepEqual(visiblePhysicalPageIndexes(3, 'spread', 113), [3, 4]);
});

test('backward from first open spread returns to the cover', () => {
  assert.equal(turnPhysical(1, 'backward', 'spread', 113), 0);
});

test('a recto semantic page normalizes to the spread that contains it', () => {
  assert.equal(normalizePhysicalAnchor(8, 'spread', 113), 7);
  assert.deepEqual(visiblePhysicalPageIndexes(8, 'spread', 113), [7, 8]);
});

test('portrait mode advances one physical page including deliberate blanks', () => {
  assert.equal(turnPhysical(7, 'forward', 'single', 113), 8);
  assert.deepEqual(visiblePhysicalPageIndexes(8, 'single', 113), [8]);
});
