export const SPREAD_MIN_WIDTH = 900;

export function modeForViewport(width, height) {
  return width >= SPREAD_MIN_WIDTH && width > height * 1.08 ? 'spread' : 'single';
}

export function normalizeAnchor(pageIndex, mode, totalPages) {
  if (totalPages <= 0) return 0;
  const bounded = Math.max(0, Math.min(pageIndex, totalPages - 1));
  return mode === 'spread' ? Math.floor(bounded / 2) * 2 : bounded;
}

export function turn(anchor, direction, mode, totalPages) {
  const step = mode === 'spread' ? 2 : 1;
  const candidate = anchor + (direction === 'forward' ? step : -step);
  return normalizeAnchor(candidate, mode, totalPages);
}

export function visiblePageIndexes(anchor, mode, totalPages) {
  const start = normalizeAnchor(anchor, mode, totalPages);
  if (mode === 'single') return [start];
  return [start, start + 1].filter((index) => index < totalPages);
}
