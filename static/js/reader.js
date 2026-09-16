import * as pdfjsLib from 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.min.mjs';
import { modeForViewport, normalizeAnchor, turn, visiblePageIndexes } from './navigation.js';

pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.worker.min.mjs';

const state = {
  book: null,
  pages: [],
  docs: new Map(),
  anchor: 0,
  mode: 'single',
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

function buildPageMap(book) {
  const result = [];
  for (const chapter of book.chapters) {
    for (let page = 1; page <= chapter.pages; page += 1) {
      result.push({ chapter, localPage: page });
    }
  }
  return result;
}

async function pdfDocument(filename) {
  if (!state.docs.has(filename)) {
    const task = pdfjsLib.getDocument({ url: `/api/document/${encodeURIComponent(filename)}?commit=${encodeURIComponent(state.book.commit_sha)}` });
    state.docs.set(filename, task.promise.catch((error) => {
      state.docs.delete(filename);
      throw error;
    }));
  }
  return state.docs.get(filename);
}

function sheetElement(globalIndex) {
  const sheet = document.createElement('section');
  sheet.className = 'page-sheet';
  sheet.dataset.pageIndex = String(globalIndex);
  sheet.setAttribute('aria-label', `Page ${globalIndex + 1}`);

  const canvas = document.createElement('canvas');
  canvas.className = 'page-canvas';
  canvas.setAttribute('aria-hidden', 'true');

  const textLayer = document.createElement('div');
  textLayer.className = 'text-layer';

  const loading = document.createElement('div');
  loading.className = 'page-loading';
  loading.textContent = `Page ${globalIndex + 1}`;

  sheet.append(canvas, textLayer, loading);
  return { sheet, canvas, textLayer, loading };
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

async function renderPage(globalIndex, slot, token) {
  const mapping = state.pages[globalIndex];
  if (!mapping || token !== state.renderToken) return;
  const { chapter, localPage } = mapping;
  const doc = await pdfDocument(chapter.pdf_file);
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

function updatePosition() {
  if (!state.book) return;
  const indexes = visiblePageIndexes(state.anchor, state.mode, state.book.total_pages);
  const label = indexes.length === 2
    ? `Pages ${indexes[0] + 1}–${indexes[1] + 1} of ${state.book.total_pages}`
    : `Page ${indexes[0] + 1} of ${state.book.total_pages}`;
  position.textContent = label;
  const first = state.pages[indexes[0]];
  if (first) document.title = `${first.chapter.title} — The Long Road To Nowhere`;
  previousButton.disabled = state.anchor <= 0;
  const lastVisible = indexes.at(-1) ?? 0;
  nextButton.disabled = lastVisible >= state.book.total_pages - 1;
}

async function renderCurrent({ animate = false, direction = 'forward' } = {}) {
  if (!state.book) return;
  const token = ++state.renderToken;
  const indexes = visiblePageIndexes(state.anchor, state.mode, state.book.total_pages);
  const fragment = document.createDocumentFragment();
  const slots = indexes.map((index) => sheetElement(index));
  for (const slot of slots) fragment.appendChild(slot.sheet);

  stage.classList.toggle('is-spread', state.mode === 'spread');
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
    if (index >= 0 && index < state.pages.length) candidates.add(state.pages[index].chapter.pdf_file);
  }
  await Promise.all([...candidates].map((filename) => pdfDocument(filename)));
}

async function performTurn(direction) {
  if (state.turning || !state.book) return;
  const next = turn(state.anchor, direction, state.mode, state.book.total_pages);
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
    const newMode = modeForViewport(window.innerWidth, window.innerHeight);
    state.mode = newMode;
    state.anchor = normalizeAnchor(state.anchor, state.mode, state.book.total_pages);
    renderCurrent();
  }, 120);
}

async function boot() {
  setStatus('Opening the book…');
  const response = await fetch('/api/book', { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('The canonical publication source could not be verified.');
  state.book = await response.json();
  state.pages = buildPageMap(state.book);
  if (state.pages.length !== state.book.total_pages) throw new Error('Publication page map failed integrity validation.');
  state.mode = modeForViewport(window.innerWidth, window.innerHeight);
  state.anchor = normalizeAnchor(0, state.mode, state.book.total_pages);
  sourceInfo.textContent = '';
  sourceInfo.dataset.commit = state.book.commit_sha;
  await document.fonts.ready;
  await renderCurrent();
  setStatus('');
  document.body.classList.add('book-ready');
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
