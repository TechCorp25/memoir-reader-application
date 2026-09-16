import test from 'node:test';
import assert from 'node:assert/strict';
import { modeForViewport, normalizeAnchor, turn, visiblePageIndexes } from '../static/js/navigation.js';

test('portrait viewport uses single-page mode', () => {
  assert.equal(modeForViewport(430, 932), 'single');
});

test('wide landscape viewport uses spread mode', () => {
  assert.equal(modeForViewport(1366, 768), 'spread');
});

test('forward spread turn advances exactly two pages', () => {
  assert.equal(turn(0, 'forward', 'spread', 105), 2);
  assert.deepEqual(visiblePageIndexes(2, 'spread', 105), [2, 3]);
});

test('backward spread turn returns exactly one spread', () => {
  assert.equal(turn(2, 'backward', 'spread', 105), 0);
});

test('single-page turn advances exactly one page', () => {
  assert.equal(turn(1, 'forward', 'single', 105), 2);
});

test('spread anchor preserves the current semantic page pair', () => {
  assert.equal(normalizeAnchor(3, 'spread', 105), 2);
});

test('landscape phone uses a two-page spread', () => {
  assert.equal(modeForViewport(844, 390), 'spread');
});

test('portrait tablet remains single-page', () => {
  assert.equal(modeForViewport(820, 1180), 'single');
});

test('landscape tablet can use a two-page spread', () => {
  assert.equal(modeForViewport(1180, 820), 'spread');
});

test('constrained browser window remains single-page when not sufficiently landscape', () => {
  assert.equal(modeForViewport(850, 700), 'single');
});
