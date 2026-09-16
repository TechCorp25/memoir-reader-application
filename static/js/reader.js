import * as pdfjsLib from 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.min.mjs';
import {
  modeForViewport,
  normalizeAnchor,
  turn,
  turnPhysical,
  visiblePageIndexes,
  visiblePhysicalPageIndexes,
} from './navigation.js';

pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.worker.min.mjs';

const BOOK_TITLE = 'The Long Road To Nowhere';

const state = {
  book: null,
  pages: [],
  docs: new Map(),
  anchor: 0,
  mode: 'single',
  physical: false,
  turning: false,
  pointer: null,
  renderToken: 0,
};

const stage = document.querySelector('[data-book-stage]');
const status = document.querySelector('[data-status]');
const position = document.querySelector('[data-position]');
const sourceInfo = document.querySelector('[data-source-info]');
const previousButton = document.querySelector('[data-previous]');
const nextButton = document.querySelector('[data-next]');

function setStatus(message, kind = 'normal') {
  status.textContent = message;
  status.dataset.kind = kind;
}

function buildLegacyPageMap(book) {
  const result = [];
  for (const chapter of book.chapters) {
    for (let page = 1; page <= chapter.pages; page += 1) {
      result.push({ kind: 'manuscript', chapter, localPage: page });
    }
  }
  return result;
}

function totalPages() {
  if (!state.book) return 0;
  return state.physical ? state.book.physical_total_pages : state.book.total_pages;
}

function visibleIndexes() {
  const total = totalPages();
  return state.physical
    ? visiblePhysicalPageIndexes(state.anchor, state.mode, total)
    : visiblePageIndexes(state.anchor, state.mode, total);
}

function nextAnchor(direction) {
  const total = totalPages();
  return state.physical
    ? turnPhysical(state.anchor, direction, state.mode, total)
    : turn(state.anchor, direction, state.mode, total);
}

async function pdfDocument(filename) {
  if (!state.docs.has(filename)) {
    const task = pdfjsLib.getDocument({
      url: `/api/document/${encodeURIComponent(filename)}?commit=${encodeURIComponent(state.book.commit_sha)}`,
    });
    state.docs.set(filename, task.promise.catch((error) => {
      state.docs.delete(filename);
      throw error;
    }));
  }
  return state.docs.get(filename);
}

function ariaLabelFor(mapping, index) {
  if (!state.physical) return `Page ${index + 1}`;
  if (!mapping) return 'Book page';
  if (mapping.kind === 'cover') return `Front cover of ${state.book.book_title || BOOK_TITLE}`;
  if (mapping.kind === 'title') return 'Book title page';
  if (mapping.kind === 'dedication') return 'Dedication page';
  if (mapping.kind === 'index') return 'Index page';
  if (mapping.kind === 'blank') return 'Intentional blank page';
  if (mapping.kind === 'manuscript') return `Manuscript page ${mapping.display_number}`;
  return 'Book page';
}

function sheetElement(globalIndex) {
  const mapping = state.pages[globalIndex];
  const kind = mapping?.kind || 'manuscript';
  const sheet = document.createElement('section');
  sheet.className = `page-sheet page-${kind}`;
  if (mapping?.side) sheet.classList.add(`page-${mapping.side}`);
  sheet.dataset.pageIndex = String(globalIndex);
  sheet.dataset.pageKind = kind;
  sheet.setAttribute('aria-label', ariaLabelFor(mapping, globalIndex));

  if (kind !== 'manuscript') return { sheet, kind };

  const canvas = document.createElement('canvas');
  canvas.className = 'page-canvas';
  canvas.setAttribute('aria-hidden', 'true');

  const textLayer = document.createElement('div');
  textLayer.className = 'text-layer';

  const loading = document.createElement('div');
  loading.className = 'page-loading';
  const number = mapping?.display_number ?? globalIndex + 1;
  loading.textContent = `Page ${number}`;

  sheet.append(canvas, textLayer, loading);
  return { sheet, canvas, textLayer, loading, kind };
}

async function renderTextLayer(page, viewport, container) {
  container.replaceChildren();
  container.style.setProperty('--scale-factor', String(viewport.scale));
  try {
    const textContent = await page.getTextContent();
    const layer = new pdfjsLib.TextLayer({
      textContentSource: textContent,
      container,
      viewport,
    });
    await layer.render();
  } catch (error) {
    // Text remains visible in the canvas if a browser-specific text-layer API fails.
    console.warn('Selectable text layer unavailable', error);
  }
}

async function renderManuscriptPage(mapping, slot, token) {
  const chapter = mapping.chapter;
  const filename = mapping.pdf_file || chapter?.pdf_file;
  const localPage = mapping.local_pdf_page || mapping.localPage;
  if (!filename || !localPage) throw new Error('Publication page map is incomplete.');

  const doc = await pdfDocument(filename);
  if (token !== state.renderToken) return;
  const page = await doc.getPage(localPage);
  if (token !== state.renderToken) return;

  const baseViewport = page.getViewport({ scale: 1 });
  const rect = slot.sheet.getBoundingClientRect();
  const cssScale = Math.min(rect.width / baseViewport.width, rect.height / baseViewport.height);
  const viewport = page.getViewport({ scale: cssScale });
  const dpr = Math.min(window.devicePixelRatio || 1, 2.5);

  slot.canvas.width = Math.max(1, Math.floor(viewport.width * dpr));
  slot.canvas.height = Math.max(1, Math.floor(viewport.height * dpr));
  slot.canvas.style.width = `${viewport.width}px`;
  slot.canvas.style.height = `${viewport.height}px`;

  const context = slot.canvas.getContext('2d', { alpha: false });
  await page.render({
    canvasContext: context,
    viewport,
    transform: dpr === 1 ? null : [dpr, 0, 0, dpr, 0, 0],
  }).promise;

  if (token !== state.renderToken) return;
  slot.textLayer.style.width = `${viewport.width}px`;
  slot.textLayer.style.height = `${viewport.height}px`;
  await renderTextLayer(page, viewport, slot.textLayer);
  slot.loading.remove();
}

function frontMatterContainer(className) {
  const container = document.createElement('div');
  container.className = `front-matter-content ${className}`;
  return container;
}

async function renderCover(mapping, slot, token) {
  const asset = state.book.assets?.[mapping.asset_id];
  if (!asset?.url || !asset.sha256) throw new Error('Approved cover asset is unavailable.');
  const image = document.createElement('img');
  image.className = 'cover-image';
  image.alt = `Front cover of ${state.book.book_title || BOOK_TITLE}`;
  image.src = asset.url;
  image.decoding = 'async';
  slot.sheet.appendChild(image);
  await new Promise((resolve, reject) => {
    image.addEventListener('load', resolve, { once: true });
    image.addEventListener('error', () => reject(new Error('Approved cover image could not be loaded.')), { once: true });
  });
  if (token !== state.renderToken) return;
}

function renderTitle(mapping, slot) {
  const container = frontMatterContainer('title-page');
  const heading = document.createElement('h1');
  heading.textContent = mapping.content || state.book.book_title || BOOK_TITLE;
  container.appendChild(heading);
  slot.sheet.appendChild(container);
}

function renderDedication(mapping, slot) {
  const container = frontMatterContainer('dedication-page');
  const text = document.createElement('p');
  text.textContent = mapping.content || '';
  if (state.book.dedication_presentation === 'script') text.classList.add('script-dedication');
  container.appendChild(text);
  slot.sheet.appendChild(container);
}

function renderIndex(slot) {
  const container = frontMatterContainer('index-page');
  const heading = document.createElement('h2');
  heading.textContent = 'Index';
  const list = document.createElement('ol');
  list.className = 'index-list';
  for (const entry of state.book.index || []) {
    const row = document.createElement('li');
    const title = document.createElement('span');
    const page = document.createElement('span');
    title.textContent = entry.title;
    page.textContent = String(entry.manuscript_page);
    row.append(title, page);
    list.appendChild(row);
  }
  container.append(heading, list);
  slot.sheet.appendChild(container);
}

async function renderPage(globalIndex, slot, token) {
  const mapping = state.pages[globalIndex];
  if (!mapping || token !== state.renderToken) return;

  if (mapping.kind === 'manuscript') {
    await renderManuscriptPage(mapping, slot, token);
    return;
  }
  if (mapping.kind === 'cover') {
    await renderCover(mapping, slot, token);
    return;
  }
  if (mapping.kind === 'title') {
    renderTitle(mapping, slot);
    return;
  }
  if (mapping.kind === 'dedication') {
    renderDedication(mapping, slot);
    return;
  }
  if (mapping.kind === 'index') {
    renderIndex(slot);
  }
  // Intentional blank pages deliberately render only the paper surface.
}

function manuscriptPageLabel(indexes) {
  const manuscript = indexes
    .map((index) => state.pages[index])
    .filter((page) => page?.kind === 'manuscript' && Number.isInteger(page.display_number));
  if (!manuscript.length) return '';
  const first = manuscript[0].display_number;
  const last = manuscript.at(-1).display_number;
  const total = state.book.manuscript_total_pages;
  return first === last ? `Page ${first} of ${total}` : `Pages ${first}–${last} of ${total}`;
}

function updatePosition() {
  if (!state.book) return;
  const indexes = visibleIndexes();

  if (state.physical) {
    position.textContent = manuscriptPageLabel(indexes);
    const manuscript = indexes.map((index) => state.pages[index]).find((page) => page?.kind === 'manuscript');
    document.title = manuscript?.chapter_title
      ? `${manuscript.chapter_title} — ${state.book.book_title || BOOK_TITLE}`
      : state.book.book_title || BOOK_TITLE;
  } else {
    const label = indexes.length === 2
      ? `Pages ${indexes[0] + 1}–${indexes[1] + 1} of ${state.book.total_pages}`
      : `Page ${indexes[0] + 1} of ${state.book.total_pages}`;
    position.textContent = label;
    const first = state.pages[indexes[0]];
    if (first?.chapter) document.title = `${first.chapter.title} — ${BOOK_TITLE}`;
  }

  previousButton.disabled = nextAnchor('backward') === state.anchor;
  nextButton.disabled = nextAnchor('forward') === state.anchor;
}

async function renderCurrent({ animate = false, direction = 'forward' } = {}) {
  if (!state.book) return;
  const token = ++state.renderToken;
  const indexes = visibleIndexes();
  const fragment = document.createDocumentFragment();
  const slots = indexes.map((index) => sheetElement(index));
  for (const slot of slots) fragment.appendChild(slot.sheet);

  stage.classList.toggle('is-spread', state.mode === 'spread' && indexes.length === 2);
  stage.classList.toggle('is-cover-state', state.physical && indexes.length === 1 && state.pages[indexes[0]]?.kind === 'cover');
  stage.replaceChildren(fragment);
  updatePosition();

  if (animate && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    stage.dataset.turn = direction;
    requestAnimationFrame(() => stage.classList.add('turning'));
    window.setTimeout(() => {
      stage.classList.remove('turning');
      delete stage.dataset.turn;
    }, 260);
  }

  await Promise.all(slots.map((slot, i) => renderPage(indexes[i], slot, token)));
  prefetchAdjacent(indexes).catch(() => {});
}

async function prefetchAdjacent(indexes) {
  const candidates = new Set();
  const first = indexes[0];
  const last = indexes.at(-1);
  for (const index of [first - 2, first - 1, last + 1, last + 2]) {
    const page = index >= 0 && index < state.pages.length ? state.pages[index] : null;
    if (!page || page.kind !== 'manuscript') continue;
    const filename = page.pdf_file || page.chapter?.pdf_file;
    if (filename) candidates.add(filename);
  }
  await Promise.all([...candidates].map((filename) => pdfDocument(filename)));
}

async function performTurn(direction) {
  if (state.turning || !state.book) return;
  const next = nextAnchor(direction);
  if (next === state.anchor) return;
  state.turning = true;
  state.anchor = next;
  await renderCurrent({ animate: true, direction });
  window.setTimeout(() => { state.turning = false; }, 280);
}

function selectionActive() {
  const selection = window.getSelection();
  return Boolean(selection && !selection.isCollapsed && selection.toString().trim());
}

function onPointerDown(event) {
  if (event.pointerType === 'mouse' && event.button !== 0) return;
  state.pointer = { x: event.clientX, y: event.clientY, id: event.pointerId };
}

function onPointerUp(event) {
  const start = state.pointer;
  state.pointer = null;
  if (!start || start.id !== event.pointerId || selectionActive()) return;
  const dx = event.clientX - start.x;
  const dy = event.clientY - start.y;
  const threshold = Math.max(48, Math.min(84, window.innerWidth * 0.075));
  if (Math.abs(dx) < threshold || Math.abs(dx) < Math.abs(dy) * 1.25) return;
  performTurn(dx < 0 ? 'forward' : 'backward');
}

let resizeTimer;
function onResize() {
  clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    if (!state.book) return;
    state.mode = modeForViewport(window.innerWidth, window.innerHeight);
    if (!state.physical) state.anchor = normalizeAnchor(state.anchor, state.mode, state.book.total_pages);
    renderCurrent();
  }, 120);
}

async function jsonResponse(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

async function loadBook() {
  const publicationResponse = await fetch('/api/publication', { headers: { Accept: 'application/json' } });
  if (publicationResponse.ok) {
    const book = await publicationResponse.json();
    if (!Array.isArray(book.pages) || book.pages.length !== book.physical_total_pages) {
      throw new Error('Physical publication page map failed integrity validation.');
    }
    return { book, pages: book.pages, physical: true };
  }

  const publicationError = await jsonResponse(publicationResponse);
  const controlledPendingAsset = publicationResponse.status === 503
    && publicationError.error === 'publication_assembly_unavailable'
    && String(publicationError.message || '').includes('AUTHOR_APPROVED_ASSET_NOT_MATERIALIZED');
  if (!controlledPendingAsset) {
    throw new Error('The physical publication authority could not be verified.');
  }

  const legacyResponse = await fetch('/api/book', { headers: { Accept: 'application/json' } });
  if (!legacyResponse.ok) throw new Error('The canonical publication source could not be verified.');
  const book = await legacyResponse.json();
  const pages = buildLegacyPageMap(book);
  if (pages.length !== book.total_pages) throw new Error('Publication page map failed integrity validation.');
  return { book, pages, physical: false };
}

async function boot() {
  setStatus('Opening the book…');
  const loaded = await loadBook();
  state.book = loaded.book;
  state.pages = loaded.pages;
  state.physical = loaded.physical;
  state.mode = modeForViewport(window.innerWidth, window.innerHeight);
  state.anchor = 0;
  sourceInfo.textContent = '';
  sourceInfo.dataset.commit = state.book.commit_sha;
  sourceInfo.dataset.readerMode = state.physical ? 'physical-publication' : 'publication-proof';
  await document.fonts.ready;
  await renderCurrent();
  setStatus('');
  document.body.classList.add('book-ready');
  document.body.classList.toggle('physical-book-ready', state.physical);
}

stage.addEventListener('pointerdown', onPointerDown, { passive: true });
stage.addEventListener('pointerup', onPointerUp, { passive: true });
stage.addEventListener('pointercancel', () => { state.pointer = null; }, { passive: true });
previousButton.addEventListener('click', () => performTurn('backward'));
nextButton.addEventListener('click', () => performTurn('forward'));
window.addEventListener('resize', onResize, { passive: true });
window.addEventListener('keydown', (event) => {
  if (event.key === 'ArrowRight' || event.key === 'PageDown') performTurn('forward');
  if (event.key === 'ArrowLeft' || event.key === 'PageUp') performTurn('backward');
});

boot().catch((error) => {
  console.error(error);
  setStatus(error.message || 'The book could not be opened.', 'error');
  document.body.classList.add('book-error');
});
