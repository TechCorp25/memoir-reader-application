import test from 'node:test';
import assert from 'node:assert/strict';
import {
  physicalSpreadStartForSemantic,
  turnPhysical,
  visiblePhysicalPageIndexes,
} from '../static/js/navigation.js';

test('wide book begins with a singleton front cover', () => {
  assert.deepEqual(visiblePhysicalPageIndexes(0, 'spread', 113), [0]);
});

test('opening the cover exposes physical pages 2 and 3', () => {
  const nextSemanticPage = turnPhysical(0, 'forward', 'spread', 113);
  assert.equal(nextSemanticPage, 1);
  assert.deepEqual(visiblePhysicalPageIndexes(nextSemanticPage, 'spread', 113), [1, 2]);
});

test('spread turns advance exactly one bound-book spread from either page in the spread', () => {
  assert.equal(turnPhysical(1, 'forward', 'spread', 113), 3);
  assert.equal(turnPhysical(2, 'forward', 'spread', 113), 3);
  assert.deepEqual(visiblePhysicalPageIndexes(3, 'spread', 113), [3, 4]);
});

test('backward from first open spread returns to the cover', () => {
  assert.equal(turnPhysical(1, 'backward', 'spread', 113), 0);
  assert.equal(turnPhysical(2, 'backward', 'spread', 113), 0);
});

test('recto semantic page composes into the physically correct spread', () => {
  assert.equal(physicalSpreadStartForSemantic(8, 113), 7);
  assert.deepEqual(visiblePhysicalPageIndexes(8, 'spread', 113), [7, 8]);
});

test('orientation changes preserve the exact semantic page', () => {
  const semanticPage = 8;
  assert.deepEqual(visiblePhysicalPageIndexes(semanticPage, 'single', 113), [8]);
  assert.deepEqual(visiblePhysicalPageIndexes(semanticPage, 'spread', 113), [7, 8]);
  assert.deepEqual(visiblePhysicalPageIndexes(semanticPage, 'single', 113), [8]);
});

test('portrait mode advances one physical page including deliberate blanks', () => {
  assert.equal(turnPhysical(7, 'forward', 'single', 113), 8);
  assert.deepEqual(visiblePhysicalPageIndexes(8, 'single', 113), [8]);
});
