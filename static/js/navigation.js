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

function boundedPhysicalIndex(pageIndex, totalPages) {
  if (totalPages <= 0) return 0;
  return Math.max(0, Math.min(pageIndex, totalPages - 1));
}

// The physical navigation API uses a semantic page index rather than a spread
// array index. This means an orientation change never changes the reader's
// current page: the same semantic page is simply composed into a different view.
export function physicalSpreadStartForSemantic(pageIndex, totalPages) {
  const bounded = boundedPhysicalIndex(pageIndex, totalPages);
  if (totalPages <= 0 || bounded === 0) return 0;
  return bounded % 2 === 1 ? bounded : bounded - 1;
}

export function visiblePhysicalPageIndexes(semanticPageIndex, mode, totalPages) {
  if (totalPages <= 0) return [];
  const bounded = boundedPhysicalIndex(semanticPageIndex, totalPages);
  if (mode === 'single') return [bounded];
  const start = physicalSpreadStartForSemantic(bounded, totalPages);
  if (start === 0) return [0];
  return [start, start + 1].filter((index) => index < totalPages);
}

export function turnPhysical(semanticPageIndex, direction, mode, totalPages) {
  if (totalPages <= 0) return 0;
  const current = boundedPhysicalIndex(semanticPageIndex, totalPages);
  if (mode === 'single') {
    const delta = direction === 'forward' ? 1 : -1;
    return boundedPhysicalIndex(current + delta, totalPages);
  }

  const spreadStart = physicalSpreadStartForSemantic(current, totalPages);
  if (direction === 'forward') {
    if (spreadStart === 0) return totalPages > 1 ? 1 : 0;
    const nextStart = spreadStart + 2;
    return nextStart < totalPages ? nextStart : current;
  }

  if (spreadStart === 0) return 0;
  if (spreadStart === 1) return 0;
  return spreadStart - 2;
}
