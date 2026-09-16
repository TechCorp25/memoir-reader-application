export const SPREAD_MIN_WIDTH = 900;

export function modeForViewport(width, height) {
  return width >= SPREAD_MIN_WIDTH && width > height * 1.08 ? 'spread' : 'single';
}

// Legacy manuscript-only navigation remains unchanged until the physical-book
// publication payload is activated in the reader.
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

// Physical-book navigation models the cover as a singleton and then pairs
// physical positions 2-3, 4-5, 6-7, ... into bound-book spreads.
export function normalizePhysicalAnchor(pageIndex, mode, totalPages) {
  if (totalPages <= 0) return 0;
  const bounded = Math.max(0, Math.min(pageIndex, totalPages - 1));
  if (mode === 'single' || bounded === 0) return bounded;
  return bounded % 2 === 1 ? bounded : bounded - 1;
}

export function visiblePhysicalPageIndexes(anchor, mode, totalPages) {
  if (totalPages <= 0) return [];
  const start = normalizePhysicalAnchor(anchor, mode, totalPages);
  if (mode === 'single' || start === 0) return [start];
  return [start, start + 1].filter((index) => index < totalPages);
}

export function turnPhysical(anchor, direction, mode, totalPages) {
  if (totalPages <= 0) return 0;
  const current = normalizePhysicalAnchor(anchor, mode, totalPages);
  if (mode === 'single') {
    const delta = direction === 'forward' ? 1 : -1;
    return normalizePhysicalAnchor(current + delta, mode, totalPages);
  }

  if (direction === 'forward') {
    if (current === 0) return totalPages > 1 ? 1 : 0;
    const candidate = current + 2;
    return candidate < totalPages ? normalizePhysicalAnchor(candidate, mode, totalPages) : current;
  }

  if (current === 0) return 0;
  if (current === 1) return 0;
  return normalizePhysicalAnchor(current - 2, mode, totalPages);
}
