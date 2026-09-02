'use strict';

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const DEFAULT_BASE_URL = 'http://127.0.0.1:8281';
const REPO = path.resolve(__dirname, '..');
const PLAYER_ID = 174;
const MAP = 'de_dust2';
const CUSTOM_FROM = '1736115900';
const CUSTOM_TO = '1767651900';
const EXPECTED_GRID = {width: 128, height: 103};
const EXPECTED_SOURCE_ROWS = 175;
const EXPECTED_TOTAL_BINS = 301;
const EXPECTED_RAW_MAX = 12;
const COLOR_ALPHA_THRESHOLD = 51;
const DIFFERENCE_CONFIDENCE = 0.22;
const DIFFERENCE_ALPHA_THRESHOLD = Math.floor(DIFFERENCE_CONFIDENCE * 255);
const CHROMA_THRESHOLD = 20;
const CONTRAST_DELTA_THRESHOLD = 12;
const DENSE_PIXEL_RATIO = 0.002;

function option(args, names) {
  const wanted = Array.isArray(names) ? names : [names];
  for (const name of wanted) {
    const prefix = `--${name}=`;
    const item = args.find((value) => value.startsWith(prefix));
    if (item) {
      return item.slice(prefix.length);
    }
  }
  return null;
}

function parseOptions() {
  const args = process.argv.slice(2);
  const baseUrl = option(args, 'base-url') || DEFAULT_BASE_URL;
  const receiptPath = option(args, ['receipt', 'json', 'output']);
  const screenshotPaths = {
    color: option(args, ['color-screenshot', 'overview-color-screenshot']),
    mono: option(args, ['mono-screenshot', 'overview-mono-screenshot']),
    difference: option(args, ['difference-screenshot', 'player-difference-screenshot']),
  };
  const timeoutValue = option(args, 'timeout-ms');
  const timeoutMs = timeoutValue === null ? 30000 : Number(timeoutValue);
  if (!Number.isFinite(timeoutMs) || timeoutMs < 1000 || timeoutMs > 120000) {
    throw new Error('invalid --timeout-ms (expected 1000..120000)');
  }
  if (!/^https?:\/\//i.test(baseUrl)) {
    throw new Error('invalid --base-url');
  }
  return {
    baseUrl: baseUrl.replace(/\/$/, ''),
    receiptPath: receiptPath ? path.resolve(receiptPath) : null,
    screenshotPaths: Object.fromEntries(
      Object.entries(screenshotPaths).map(([key, value]) => [key, value ? path.resolve(value) : null])
    ),
    timeoutMs,
    headed: !args.includes('--headless'),
  };
}

function ensureParent(filePath) {
  if (filePath) {
    fs.mkdirSync(path.dirname(filePath), {recursive: true});
  }
}

function writeJson(filePath, value) {
  if (!filePath) {
    return;
  }
  ensureParent(filePath);
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

function head() {
  try {
    return execFileSync('rtk', ['git', 'rev-parse', 'HEAD'], {
      cwd: REPO,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  } catch {
    return null;
  }
}

function conciseError(error) {
  if (!error) {
    return 'unknown error';
  }
  const message = error && error.message ? error.message : String(error);
  return message.split('\n')[0].slice(0, 500);
}

function gate(name, pass, details) {
  return {name, pass: Boolean(pass), details: details || {}};
}

function pageSelector(root, selector) {
  return `${root} ${selector}`;
}

function apiUrl(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.origin}${parsed.pathname}?${parsed.searchParams.toString()}`;
  } catch {
    return null;
  }
}

function apiParameters(url) {
  try {
    return new URL(url).searchParams;
  } catch {
    return new URLSearchParams();
  }
}

function isHeatmapApi(url) {
  try {
    const parsed = new URL(url);
    return parsed.pathname.endsWith('/heatmap_points.php') && parsed.searchParams.get('v') === '2';
  } catch {
    return false;
  }
}

function matchesQuery(url, expected) {
  if (!isHeatmapApi(url)) {
    return false;
  }
  const params = apiParameters(url);
  return Object.entries(expected).every(([key, value]) => params.get(key) === String(value));
}

function sceneSummary(json) {
  const total = json && json.layers && Array.isArray(json.layers.total) ? json.layers.total : [];
  let rawMax = 0;
  for (const row of total) {
    if (Array.isArray(row)) {
      // The overview's raw cell magnitude is the both-channel total. This is
      // the reported 12 for the accepted de_dust2 witness (7 kills + 5 deaths).
      rawMax = Math.max(rawMax, (Number(row[3]) || 0) + (Number(row[4]) || 0));
    }
  }
  const grid = json && json.grid ? json.grid : {};
  const coverage = json && json.coverage ? json.coverage : {};
  const summary = json && json.summary ? json.summary : {};
  return {
    state: json && json.state || null,
    sourceRows: Number(coverage.sourceRows ?? summary.sourceRows ?? NaN),
    totalBins: total.length,
    grid: {width: Number(grid.width), height: Number(grid.height)},
    rawMax,
    map: json && json.map ? {
      name: json.map.name || null,
      image: json.map.image ? {
        width: Number(json.map.image.width),
        height: Number(json.map.image.height),
      } : null,
    } : null,
  };
}

async function responseRecord(response) {
  const body = await response.text();
  let json = null;
  try {
    json = JSON.parse(body);
  } catch {
    json = null;
  }
  return {
    url: apiUrl(response.url()),
    status: response.status(),
    ok: response.ok(),
    bytes: Buffer.byteLength(body, 'utf8'),
    summary: sceneSummary(json),
    json,
  };
}

async function waitForApi(page, matcher, trigger, timeoutMs) {
  const [response] = await Promise.all([
    page.waitForResponse((candidate) => matcher(candidate.url()), {timeout: timeoutMs}),
    trigger(),
  ]);
  return responseRecord(response);
}

async function waitForExplorer(page, rootSelector, timeoutMs) {
  await page.waitForSelector(rootSelector, {timeout: timeoutMs});
  await page.waitForFunction((selector) => {
    const root = document.querySelector(selector);
    const status = root && root.querySelector('[data-heatmap-status="1"]');
    const summary = root && root.querySelector('[data-heatmap-summary="1"]');
    const image = root && root.querySelector('[data-heatmap-image="1"]');
    const canvas = root && root.querySelector('[data-heatmap-canvas="1"]');
    const statusText = status && status.textContent ? status.textContent.trim() : '';
    return !!root
      && root.getAttribute('data-heatmap-mounted') === '1'
      && statusText !== ''
      && !/Loading heatmap data|Загрузка данных теплокарты/i.test(statusText)
      && !!summary
      && !!(summary.textContent && summary.textContent.trim())
      && !!image
      && image.complete
      && image.naturalWidth > 0
      && !!canvas
      && !!window.__heatmapVisualGate
      && window.__heatmapVisualGate.captures.some((capture) => capture.canvas === canvas && capture.pixels);
  }, rootSelector, {timeout: timeoutMs});
}

async function nextFrame(page) {
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => resolve())));
}

async function installWebglCapture(page) {
  await page.addInitScript(() => {
    const gate = {
      captures: [],
      patchInstalled: false,
      colorFrame: null,
    };
    window.__heatmapVisualGate = gate;
    const prototype = window.WebGL2RenderingContext && window.WebGL2RenderingContext.prototype;
    if (!prototype || typeof prototype.drawArrays !== 'function') {
      gate.patchError = 'webgl2_drawArrays_unavailable';
      return;
    }
    const original = prototype.drawArrays;
    if (original.__heatmapVisualGatePatched) {
      gate.patchInstalled = true;
      return;
    }
    const patched = function patchedDrawArrays(...args) {
      const result = original.apply(this, args);
      const capture = {
        canvas: this.canvas,
        args: args.slice(0, 3),
        width: 0,
        height: 0,
        pixels: null,
        error: null,
      };
      try {
        // This is deliberately adjacent to the real drawArrays call: the gate
        // never samples a later, possibly-cleared default framebuffer.
        if (typeof this.finish !== 'function' || typeof this.readPixels !== 'function') {
          throw new Error('webgl2_readback_unavailable');
        }
        this.finish();
        capture.width = this.drawingBufferWidth || 0;
        capture.height = this.drawingBufferHeight || 0;
        if (!capture.width || !capture.height) {
          throw new Error('webgl2_empty_drawing_buffer');
        }
        capture.pixels = new Uint8Array(capture.width * capture.height * 4);
        this.readPixels(0, 0, capture.width, capture.height, this.RGBA, this.UNSIGNED_BYTE, capture.pixels);
      } catch (error) {
        capture.error = String(error && error.message ? error.message : error);
      }
      gate.captures.push(capture);
      if (gate.captures.length > 8) {
        gate.captures.shift();
      }
      return result;
    };
    Object.defineProperty(patched, '__heatmapVisualGatePatched', {value: true});
    prototype.drawArrays = patched;
    gate.patchInstalled = true;
  });
}

function equalBytes(left, right) {
  if (!left || !right || left.length !== right.length) {
    return false;
  }
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) {
      return false;
    }
  }
  return true;
}

async function readFrame(page, mode, alphaThreshold) {
  return page.evaluate(({mode, alphaThreshold}) => {
    const gate = window.__heatmapVisualGate;
    const canvas = document.querySelector('[data-heatmap-canvas="1"]');
    if (!gate || !canvas) {
      return {error: 'missing_webgl_gate_or_canvas', mode};
    }
    let capture = null;
    for (let index = gate.captures.length - 1; index >= 0; index -= 1) {
      if (gate.captures[index].canvas === canvas) {
        capture = gate.captures[index];
        break;
      }
    }
    if (!capture) {
      return {error: 'no_drawArrays_capture', mode, patchInstalled: gate.patchInstalled, patchError: gate.patchError || null};
    }
    if (capture.error || !capture.pixels) {
      return {error: capture.error || 'readPixels_capture_missing', mode};
    }
    const pixels = capture.pixels;
    const metric = {
      pixelCount: capture.width * capture.height,
      width: capture.width,
      height: capture.height,
      alphaThreshold,
      alphaThresholdPixels: 0,
      coloredPixels: 0,
      warmPixels: 0,
      coolPixels: 0,
      alphaPositive: 0,
      maxAlphaByte: 0,
      maxAlpha: 0,
      meanAlpha: 0,
      maxChroma: 0,
      captureCount: gate.captures.length,
      drawArgs: capture.args,
      frameHash: null,
    };
    let alphaSum = 0;
    for (let offset = 0; offset < pixels.length; offset += 4) {
      const r = pixels[offset];
      const g = pixels[offset + 1];
      const b = pixels[offset + 2];
      const a = pixels[offset + 3];
      const chroma = Math.max(r, g, b) - Math.min(r, g, b);
      alphaSum += a;
      metric.maxAlphaByte = Math.max(metric.maxAlphaByte, a);
      metric.maxChroma = Math.max(metric.maxChroma, chroma);
      if (a > 0) metric.alphaPositive += 1;
      if (a >= alphaThreshold) {
        metric.alphaThresholdPixels += 1;
        if (chroma > 20) {
          metric.coloredPixels += 1;
          if (r > b + 10) metric.warmPixels += 1;
          else if (b > r + 10) metric.coolPixels += 1;
        }
      }
    }
    metric.maxAlpha = metric.maxAlphaByte / 255;
    metric.meanAlpha = metric.pixelCount ? alphaSum / metric.pixelCount / 255 : 0;
    // A hash is helpful in a compact receipt; exact equality is checked below
    // against a retained copy of the Color frame, not inferred from the hash.
    let hash = 2166136261;
    for (const byte of pixels) {
      hash ^= byte;
      hash = Math.imul(hash, 16777619);
    }
    metric.frameHash = (hash >>> 0).toString(16).padStart(8, '0');
    let identicalToColor = null;
    if (mode === 'color') {
      gate.colorFrame = {
        width: capture.width,
        height: capture.height,
        pixels: pixels.slice(),
      };
    } else if (mode === 'mono' && gate.colorFrame) {
      identicalToColor = gate.colorFrame.width === capture.width
        && gate.colorFrame.height === capture.height
        && gate.colorFrame.pixels.length === pixels.length;
      if (identicalToColor) {
        for (let index = 0; index < pixels.length; index += 1) {
          if (gate.colorFrame.pixels[index] !== pixels[index]) {
            identicalToColor = false;
            break;
          }
        }
      }
    }
    return {
      mode,
      metric,
      identicalToColor,
      pixels,
      width: capture.width,
      height: capture.height,
    };
  }, {mode, alphaThreshold});
}

async function backgroundContrast(page, occupiedCells, alphaThreshold) {
  return page.evaluate(({occupiedCells, alphaThreshold}) => {
    const canvas = document.querySelector('[data-heatmap-canvas="1"]');
    const image = document.querySelector('[data-heatmap-image="1"]');
    const root = document.querySelector('[data-heatmap-explorer="1"]');
    if (!canvas || !image || !root) {
      return {supported: false, error: 'missing_map_elements'};
    }
    const width = canvas.width || canvas.clientWidth || 0;
    const height = canvas.height || canvas.clientHeight || 0;
    const filter = getComputedStyle(image).filter || 'none';
    const sourceCanvas = document.createElement('canvas');
    const filteredCanvas = document.createElement('canvas');
    sourceCanvas.width = width;
    sourceCanvas.height = height;
    filteredCanvas.width = width;
    filteredCanvas.height = height;
    const sourceContext = sourceCanvas.getContext('2d', {willReadFrequently: true});
    const filteredContext = filteredCanvas.getContext('2d', {willReadFrequently: true});
    if (!sourceContext || !filteredContext || !('filter' in filteredContext) || !width || !height) {
      return {supported: false, error: 'temporary_2d_filter_unavailable', filter, width, height};
    }
    sourceContext.filter = 'none';
    sourceContext.drawImage(image, 0, 0, width, height);
    filteredContext.filter = filter;
    filteredContext.drawImage(image, 0, 0, width, height);
    const source = sourceContext.getImageData(0, 0, width, height).data;
    const background = filteredContext.getImageData(0, 0, width, height).data;
    const sourceHash = (() => {
      let hash = 2166136261;
      for (const byte of source) { hash ^= byte; hash = Math.imul(hash, 16777619); }
      return (hash >>> 0).toString(16).padStart(8, '0');
    })();
    const backgroundHash = (() => {
      let hash = 2166136261;
      for (const byte of background) { hash ^= byte; hash = Math.imul(hash, 16777619); }
      return (hash >>> 0).toString(16).padStart(8, '0');
    })();
    // The frame is retained by the drawArrays instrumentation. We read the
    // latest same-canvas capture here and composite its straight-alpha color
    // over the filtered image at the matching (top-left) map coordinate.
    const gate = window.__heatmapVisualGate;
    let capture = null;
    for (let index = gate.captures.length - 1; index >= 0; index -= 1) {
      if (gate.captures[index].canvas === canvas) {
        capture = gate.captures[index];
        break;
      }
    }
    if (!capture || !capture.pixels || capture.width !== width || capture.height !== height) {
      return {supported: false, error: 'missing_matching_webgl_frame', filter, width, height, sourceHash, backgroundHash};
    }
    const pixels = capture.pixels;
    let coloredPixels = 0;
    let contrastPixels = 0;
    let maxDelta = 0;
    let alphaThresholdPixels = 0;
    const samples = [];
    for (let yGl = 0; yGl < height; yGl += 1) {
      const yTop = height - 1 - yGl;
      for (let x = 0; x < width; x += 1) {
        const frameOffset = (yGl * width + x) * 4;
        const backgroundOffset = (yTop * width + x) * 4;
        const r = pixels[frameOffset];
        const g = pixels[frameOffset + 1];
        const b = pixels[frameOffset + 2];
        const aByte = pixels[frameOffset + 3];
        const a = aByte / 255;
        const chroma = Math.max(r, g, b) - Math.min(r, g, b);
        const br = background[backgroundOffset];
        const bg = background[backgroundOffset + 1];
        const bb = background[backgroundOffset + 2];
        if (aByte >= alphaThreshold) alphaThresholdPixels += 1;
        if (aByte >= alphaThreshold && chroma > 20) {
          coloredPixels += 1;
          const composite = [
            (r * a) + (br * (1 - a)),
            (g * a) + (bg * (1 - a)),
            (b * a) + (bb * (1 - a)),
          ];
          const delta = Math.max(
            Math.abs(composite[0] - br),
            Math.abs(composite[1] - bg),
            Math.abs(composite[2] - bb)
          );
          maxDelta = Math.max(maxDelta, delta);
          if (delta >= 12) {
            contrastPixels += 1;
            if (samples.length < 3) samples.push({x, yTop, rgba: [r, g, b, aByte], background: [br, bg, bb], delta});
          }
        }
      }
    }
    return {
      supported: true,
      filter,
      width,
      height,
      sourceHash,
      backgroundHash,
      backgroundPixels: width * height,
      alphaThreshold,
      alphaThresholdPixels,
      coloredPixels,
      contrastPixels,
      maxDelta,
      samples,
      occupiedCells,
    };
  }, {occupiedCells, alphaThreshold});
}

async function saveExplorerScreenshot(page, outputPath) {
  if (!outputPath) {
    return null;
  }
  ensureParent(outputPath);
  await page.locator('[data-heatmap-explorer="1"]').screenshot({path: outputPath});
  return outputPath;
}

function totalOccupiedCells(json) {
  const rows = json && json.layers && Array.isArray(json.layers.total) ? json.layers.total : [];
  return new Set(rows.map((row) => Array.isArray(row) ? row[0] : null).filter(Boolean));
}

function differenceMetrics(json) {
  const comparison = json && json.comparison ? json.comparison : {};
  const bins = Array.isArray(comparison.bins) ? comparison.bins : [];
  const occupied = bins.filter((row) => Array.isArray(row) && Number(row[5]) > 0);
  let warm = 0;
  let cool = 0;
  let neutral = 0;
  for (const row of occupied) {
    const value = Number(row[3]) || 0;
    if (value > 0) warm += 1;
    else if (value < 0) cool += 1;
    else neutral += 1;
  }
  return {
    occupiedBins: occupied.length,
    warmBins: warm,
    coolBins: cool,
    neutralBins: neutral,
    personalSample: Number(comparison.personalSample) || 0,
    otherSample: Number(comparison.otherSample) || 0,
    totalBins: bins.length,
  };
}

function visualThreshold(pixelCount) {
  return Math.max(512, Math.ceil(pixelCount * DENSE_PIXEL_RATIO));
}

function differenceThreshold(pixelCount, grid, occupiedBins) {
  const gridCells = Math.max(1, Number(grid.width) * Number(grid.height));
  const expectedCellPixels = pixelCount / gridCells;
  const expectedOccupiedPixels = occupiedBins * expectedCellPixels;
  // Difference has data-driven coverage: a 5% sample of occupied cell area is
  // enough to catch a transparent/neutral frame while allowing its 0.22
  // low-sample confidence to remain visible without demanding full fill.
  return Math.max(128, Math.ceil(expectedOccupiedPixels * 0.05));
}

async function collectStyle(page) {
  return page.evaluate(() => {
    const root = document.querySelector('[data-heatmap-explorer="1"]');
    const image = root && root.querySelector('[data-heatmap-image="1"]');
    const camera = root && root.querySelector('[data-heatmap-camera="1"]');
    const style = image ? getComputedStyle(image) : null;
    const cameraStyle = camera ? getComputedStyle(camera, '::after') : null;
    return {
      mapStyle: root ? root.getAttribute('data-heatmap-map-style') : null,
      filter: style ? style.filter : null,
      cameraOverlay: cameraStyle ? {
        opacity: cameraStyle.opacity,
        backgroundImage: cameraStyle.backgroundImage,
        mixBlendMode: cameraStyle.mixBlendMode,
      } : null,
    };
  });
}

async function mapOverview(options, report) {
  const context = await report.browser.newContext({viewport: {width: 1440, height: 1000}, locale: 'en-US'});
  const page = await context.newPage();
  await installWebglCapture(page);
  const errors = {page: [], console: [], requests: []};
  page.on('pageerror', (error) => errors.page.push(conciseError(error)));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.console.push(message.text().slice(0, 500));
  });
  page.on('request', (request) => {
    if (isHeatmapApi(request.url())) errors.requests.push(apiUrl(request.url()));
  });
  const url = `${options.baseUrl}/hlstats.php?mode=mapinfo&game=cstrike&map=${MAP}&lang=en&heatmap_explorer=1`
    + `&hm_from=${CUSTOM_FROM}&hm_to=${CUSTOM_TO}&hm_event=both&hm_lens=overview&hm_floor=all`;
  const root = '[data-heatmap-explorer="1"]';
  try {
    const overviewResponse = await waitForApi(
      page,
      (candidateUrl) => matchesQuery(candidateUrl, {
        game: 'cstrike', map: MAP, from: CUSTOM_FROM, to: CUSTOM_TO, event: 'both', lens: 'overview', floor: 'all', lang: 'en',
      }),
      () => page.goto(url, {waitUntil: 'commit', timeout: options.timeoutMs}),
      options.timeoutMs
    );
    report.overview = {url, response: overviewResponse, errors};
    await waitForExplorer(page, root, options.timeoutMs);

    const overviewContract = overviewResponse.summary;
    const colorFrame = await readFrame(page, 'color', COLOR_ALPHA_THRESHOLD);
    if (colorFrame.error) throw new Error(`overview_color:${colorFrame.error}`);
    const colorStyle = await collectStyle(page);
    const colorBackground = await backgroundContrast(page, totalOccupiedCells(overviewResponse.json).size, COLOR_ALPHA_THRESHOLD);
    const colorPath = await saveExplorerScreenshot(page, options.screenshotPaths.color);

    const beforeStyleRequests = errors.requests.length;
    await page.locator('[data-heatmap-map-style-option="mono"]').click();
    await page.waitForFunction(() => {
      const rootElement = document.querySelector('[data-heatmap-explorer="1"]');
      return rootElement && rootElement.getAttribute('data-heatmap-map-style') === 'mono';
    }, {timeout: options.timeoutMs});
    await nextFrame(page);
    const monoFrame = await readFrame(page, 'mono', COLOR_ALPHA_THRESHOLD);
    if (monoFrame.error) throw new Error(`overview_mono:${monoFrame.error}`);
    const monoStyle = await collectStyle(page);
    const monoBackground = await backgroundContrast(page, totalOccupiedCells(overviewResponse.json).size, COLOR_ALPHA_THRESHOLD);
    const monoPath = await saveExplorerScreenshot(page, options.screenshotPaths.mono);

    const colorRawPixels = colorFrame.pixels;
    const monoRawPixels = monoFrame.pixels;
    const exactFrameEqual = colorFrame.width === monoFrame.width
      && colorFrame.height === monoFrame.height
      && equalBytes(colorRawPixels, monoRawPixels)
      && monoFrame.identicalToColor === true;
    const backgroundPresentationDiffers = colorStyle.filter !== monoStyle.filter
      && colorBackground.supported
      && monoBackground.supported
      && colorBackground.backgroundHash !== monoBackground.backgroundHash;
    const threshold = visualThreshold(colorFrame.metric.pixelCount);
    const overviewGates = [
      gate('overview-contract', overviewResponse.status === 200
        && overviewResponse.summary.state === 'ok'
        && overviewContract.sourceRows === EXPECTED_SOURCE_ROWS
        && overviewContract.totalBins === EXPECTED_TOTAL_BINS
        && overviewContract.grid.width === EXPECTED_GRID.width
        && overviewContract.grid.height === EXPECTED_GRID.height
        && overviewContract.rawMax === EXPECTED_RAW_MAX, overviewContract),
      gate('color-raw-density', colorFrame.metric.coloredPixels >= threshold, {
        threshold, frame: colorFrame.metric,
      }),
      gate('mono-raw-density', monoFrame.metric.coloredPixels >= threshold, {
        threshold, frame: monoFrame.metric,
      }),
      gate('color-mono-webgl-identical', exactFrameEqual, {
        exactFrameEqual,
        colorHash: colorFrame.metric.frameHash,
        monoHash: monoFrame.metric.frameHash,
      }),
      gate('map-style-presentation-differs', backgroundPresentationDiffers, {
        colorFilter: colorStyle.filter,
        monoFilter: monoStyle.filter,
        colorBackgroundHash: colorBackground.backgroundHash,
        monoBackgroundHash: monoBackground.backgroundHash,
      }),
      gate('color-composite-contrast', colorBackground.supported
        && colorBackground.contrastPixels >= Math.ceil(colorFrame.metric.pixelCount * DENSE_PIXEL_RATIO), {
        required: Math.ceil(colorFrame.metric.pixelCount * DENSE_PIXEL_RATIO),
        contrast: colorBackground,
      }),
      gate('mono-composite-contrast', monoBackground.supported
        && monoBackground.contrastPixels >= Math.ceil(monoFrame.metric.pixelCount * DENSE_PIXEL_RATIO), {
        required: Math.ceil(monoFrame.metric.pixelCount * DENSE_PIXEL_RATIO),
        contrast: monoBackground,
      }),
      gate('style-is-map-only', errors.requests.length === beforeStyleRequests, {
        heatmapRequestsBefore: beforeStyleRequests,
        heatmapRequestsAfter: errors.requests.length,
      }),
      gate('overview-browser-errors', errors.page.length === 0 && errors.console.length === 0, errors),
    ];
    report.overview.style = {color: colorStyle, mono: monoStyle};
    report.overview.frames = {
      color: {metric: colorFrame.metric, background: colorBackground, screenshot: colorPath},
      mono: {metric: monoFrame.metric, background: monoBackground, screenshot: monoPath},
      exactFrameEqual,
    };
    report.overview.gates = overviewGates;
    report.overview.pass = overviewGates.every((item) => item.pass);
  } finally {
    await context.close();
  }
}

async function playerDifference(options, report) {
  const context = await report.browser.newContext({viewport: {width: 1440, height: 1000}, locale: 'ru-RU'});
  const page = await context.newPage();
  await installWebglCapture(page);
  const errors = {page: [], console: [], requests: []};
  page.on('pageerror', (error) => errors.page.push(conciseError(error)));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.console.push(message.text().slice(0, 500));
  });
  page.on('request', (request) => {
    if (isHeatmapApi(request.url())) errors.requests.push(apiUrl(request.url()));
  });
  const startUrl = `${options.baseUrl}/hlstats.php?mode=playerinfo&game=cstrike&player=${PLAYER_ID}`
    + `&killLimit=5&lang=ru&heatmap_explorer=1`;
  const root = '[data-heatmap-explorer="1"]';
  try {
    await page.goto(startUrl, {waitUntil: 'commit', timeout: options.timeoutMs});
    const [ajaxResponse] = await Promise.all([
      page.waitForResponse((response) => response.url().includes('mode=playerinfo')
        && response.url().includes('type=ajax')
        && response.url().includes('tab=mapperformance_servers'), {timeout: options.timeoutMs}),
      page.locator('#tab_mapperformance_servers').click(),
    ]);
    if (!ajaxResponse.ok()) throw new Error(`player_ajax_status_${ajaxResponse.status()}`);
    await waitForExplorer(page, root, options.timeoutMs);
    const mapSelect = page.locator(pageSelector(root, '[data-heatmap-map-select="1"]'));
    const rangeSelect = page.locator(pageSelector(root, '[data-heatmap-range="1"]'));
    const fromInput = page.locator(pageSelector(root, '[data-heatmap-from="1"]'));
    const toInput = page.locator(pageSelector(root, '[data-heatmap-to="1"]'));
    const apply = page.locator(pageSelector(root, '[data-heatmap-apply="1"]'));
    const currentMap = await mapSelect.inputValue();
    let defaultMap = null;
    if (currentMap !== MAP) {
      defaultMap = await waitForApi(
        page,
        (candidateUrl) => matchesQuery(candidateUrl, {player: PLAYER_ID, map: MAP, range: '30d', event: 'both', lens: 'overview', floor: 'all', lang: 'ru'}),
        () => mapSelect.selectOption(MAP),
        options.timeoutMs
      );
      await waitForExplorer(page, root, options.timeoutMs);
    }
    await rangeSelect.selectOption('custom');
    await fromInput.fill(CUSTOM_FROM);
    await toInput.fill(CUSTOM_TO);
    const customOverview = await waitForApi(
      page,
      (candidateUrl) => matchesQuery(candidateUrl, {player: PLAYER_ID, map: MAP, from: CUSTOM_FROM, to: CUSTOM_TO, event: 'both', lens: 'overview', floor: 'all', lang: 'ru'}),
      () => apply.click(),
      options.timeoutMs
    );
    await waitForExplorer(page, root, options.timeoutMs);
    const kills = page.locator(pageSelector(root, '[data-heatmap-event="kills"]'));
    const difference = page.locator(pageSelector(root, '[data-heatmap-lens="difference"]'));
    const differenceResponse = await waitForApi(
      page,
      (candidateUrl) => matchesQuery(candidateUrl, {player: PLAYER_ID, map: MAP, from: CUSTOM_FROM, to: CUSTOM_TO, event: 'kills', lens: 'difference', floor: 'all', lang: 'ru'}),
      async () => {
        await kills.click();
        await difference.click();
      },
      options.timeoutMs
    );
    await waitForExplorer(page, root, options.timeoutMs);
    const data = differenceMetrics(differenceResponse.json);
    const frame = await readFrame(page, 'difference', DIFFERENCE_ALPHA_THRESHOLD);
    if (frame.error) throw new Error(`difference:${frame.error}`);
    const occupiedCells = data.occupiedBins;
    const background = await backgroundContrast(page, occupiedCells, DIFFERENCE_ALPHA_THRESHOLD);
    const pixelThreshold = differenceThreshold(frame.metric.pixelCount, differenceResponse.json.grid || EXPECTED_GRID, data.occupiedBins);
    const contrastThreshold = differenceThreshold(frame.metric.pixelCount, differenceResponse.json.grid || EXPECTED_GRID, data.occupiedBins);
    const screenshot = await saveExplorerScreenshot(page, options.screenshotPaths.difference);
    const warmCoolPresent = (data.warmBins === 0 || frame.metric.warmPixels > 0)
      && (data.coolBins === 0 || frame.metric.coolPixels > 0);
    const diffGates = [
      gate('difference-workflow', differenceResponse.status === 200
        && differenceResponse.summary.state === 'ok'
        && differenceResponse.summary.sourceRows === EXPECTED_SOURCE_ROWS
        && data.personalSample >= 3
        && data.otherSample > 0
        && data.occupiedBins > 0, {
        response: differenceResponse.summary,
        workflow: {map: MAP, player: PLAYER_ID, event: 'kills', lens: 'difference', from: CUSTOM_FROM, to: CUSTOM_TO},
        defaultMap: defaultMap ? defaultMap.summary : null,
        customOverview: customOverview.summary,
      }),
      gate('difference-data-grounded-colored-pixels', frame.metric.coloredPixels >= pixelThreshold, {
        threshold: pixelThreshold,
        occupiedBins: data.occupiedBins,
        expectedOccupiedPixels: frame.metric.pixelCount
          * data.occupiedBins / Math.max(1, Number((differenceResponse.json.grid || EXPECTED_GRID).width)
            * Number((differenceResponse.json.grid || EXPECTED_GRID).height)),
        lowSampleConfidence: DIFFERENCE_CONFIDENCE,
        alphaThreshold: DIFFERENCE_ALPHA_THRESHOLD,
        frame: frame.metric,
      }),
      gate('difference-composite-contrast', background.supported && background.contrastPixels >= contrastThreshold, {
        threshold: contrastThreshold,
        lowSampleConfidence: DIFFERENCE_CONFIDENCE,
        alphaThreshold: DIFFERENCE_ALPHA_THRESHOLD,
        contrast: background,
      }),
      gate('difference-warm-cool-report', warmCoolPresent, {
        occupiedBins: data.occupiedBins,
        warmBins: data.warmBins,
        coolBins: data.coolBins,
        neutralBins: data.neutralBins,
        warmPixels: frame.metric.warmPixels,
        coolPixels: frame.metric.coolPixels,
      }),
      gate('difference-browser-errors', errors.page.length === 0 && errors.console.length === 0, errors),
    ];
    report.difference = {
      startUrl,
      ajax: {status: ajaxResponse.status()},
      response: differenceResponse,
      data,
      frame: {metric: frame.metric, background, screenshot},
      thresholds: {coloredPixels: pixelThreshold, contrastPixels: contrastThreshold, lowSampleConfidence: DIFFERENCE_CONFIDENCE},
      errors,
      gates: diffGates,
      pass: diffGates.every((item) => item.pass),
    };
  } finally {
    await context.close();
  }
}

async function run() {
  const options = parseOptions();
  const report = {
    schema: 'hlstatsx-modern-heatmap-visual-gate/v1',
    generatedAt: new Date().toISOString(),
    head: head(),
    baseUrl: options.baseUrl,
    viewport: {width: 1440, height: 1000},
    contract: {
      map: MAP,
      player: PLAYER_ID,
      window: {from: CUSTOM_FROM, to: CUSTOM_TO},
      grid: EXPECTED_GRID,
      overviewSourceRows: EXPECTED_SOURCE_ROWS,
      overviewBins: EXPECTED_TOTAL_BINS,
      overviewRawMax: EXPECTED_RAW_MAX,
      alphaThreshold: COLOR_ALPHA_THRESHOLD,
      chromaThreshold: CHROMA_THRESHOLD,
      contrastDeltaThreshold: CONTRAST_DELTA_THRESHOLD,
      densePixelRatio: DENSE_PIXEL_RATIO,
      differenceLowSampleConfidence: DIFFERENCE_CONFIDENCE,
      differenceAlphaThreshold: DIFFERENCE_ALPHA_THRESHOLD,
    },
    output: {
      receipt: options.receiptPath,
      screenshots: options.screenshotPaths,
    },
    pass: false,
    gates: [],
  };
  let browser = null;
  let workflowReport = null;
  try {
    browser = await chromium.launch({headless: !options.headed});
    report.browser = {
      engine: 'chromium',
      version: typeof browser.version === 'function' ? browser.version() : null,
      headed: options.headed,
      viewport: {width: 1440, height: 1000},
    };
    // Keep one browser process but isolated contexts for each public workflow;
    // this prevents stale scene state from hiding a bad normalization frame.
    workflowReport = {browser};
    await mapOverview(options, workflowReport);
    report.overview = workflowReport.overview;
    await playerDifference(options, workflowReport);
    report.difference = workflowReport.difference;
  } catch (error) {
    report.fatalError = conciseError(error);
    if (workflowReport) {
      report.overview = report.overview || workflowReport.overview;
      report.difference = report.difference || workflowReport.difference;
    }
  } finally {
    if (browser) {
      try { await browser.close(); } catch {}
    }
  }
  report.gates = [
    ...(report.overview && report.overview.gates ? report.overview.gates : []),
    ...(report.difference && report.difference.gates ? report.difference.gates : []),
  ];
  report.pass = !report.fatalError
    && !!report.overview && report.overview.pass
    && !!report.difference && report.difference.pass;
  if (report.fatalError) {
    report.gates.push(gate('fatal-error', false, {error: report.fatalError}));
  }
  writeJson(options.receiptPath, report);
  const compact = {
    pass: report.pass,
    head: report.head,
    receipt: options.receiptPath,
    screenshots: options.screenshotPaths,
    overview: report.overview ? {
      contract: report.overview.response ? report.overview.response.summary : null,
      color: report.overview.frames ? report.overview.frames.color.metric : null,
      mono: report.overview.frames ? report.overview.frames.mono.metric : null,
      exactFrameEqual: report.overview.frames ? report.overview.frames.exactFrameEqual : false,
      gates: report.overview.gates ? report.overview.gates.filter((item) => !item.pass).map((item) => item.name) : [],
    } : null,
    difference: report.difference ? {
      data: report.difference.data,
      frame: report.difference.frame ? report.difference.frame.metric : null,
      gates: report.difference.gates ? report.difference.gates.filter((item) => !item.pass).map((item) => item.name) : [],
    } : null,
    fatalError: report.fatalError || null,
  };
  console.log(JSON.stringify(compact, null, 2));
  if (!report.pass) process.exitCode = 1;
}

run().catch((error) => {
  console.error(conciseError(error));
  process.exitCode = 1;
});
