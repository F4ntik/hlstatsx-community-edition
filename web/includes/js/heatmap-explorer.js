(function (root, factory) {
  'use strict';

  var api = factory();
  if (typeof module !== 'undefined' && module && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.HeatmapExplorerScene = api.HeatmapExplorerScene;
    root.HeatmapExplorerCamera = api.HeatmapExplorerCamera;
    root.HeatmapExplorerUrlState = api.HeatmapExplorerUrlState;
    root.HeatmapExplorerWorkspace = api.HeatmapExplorerWorkspace;
    root.HeatmapGlRenderer = api.HeatmapGlRenderer;
    root.HeatmapPointGeometry = api.HeatmapPointGeometry;
    root.HeatmapSurfaceGraph = api.HeatmapSurfaceGraph;
    root.loadSurfaceGraph = api.loadSurfaceGraph;
    root.gaussianKernel1d = api.gaussianKernel1d;
    root.gaussianSmooth = api.gaussianSmooth;
    root.presentationField = api.presentationField;
    root.regionContains = api.regionContains;
    root.regionGridMask = api.regionGridMask;
    root.utcInputSeconds = api.utcInputSeconds;
    root.utcInputValue = api.utcInputValue;
    if (root.document && api.HeatmapExplorerWorkspace) {
      var mountExplorerWorkspaces = function () {
        api.HeatmapExplorerWorkspace.mountAll(root.document, {window: root});
      };
      if (root.document.readyState === 'loading' && typeof root.addEventListener === 'function') {
        root.addEventListener('DOMContentLoaded', mountExplorerWorkspaces);
      } else {
        mountExplorerWorkspaces();
      }
    }
  }
}(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  var hasOwn = Object.prototype.hasOwnProperty;
  var TOKEN = /^[A-Za-z][A-Za-z0-9_-]{0,31}$/;
  var CELL = /^c(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;
  var HASH = /^[a-f0-9]{16}$/;
  var SHA256 = /^[a-f0-9]{64}$/;
  var HEATMAP_Z_MIN = -8388608;
  var HEATMAP_Z_MAX = 8388607;
  var RANGE_SECONDS = {
    '7d': 604800,
    '30d': 2592000,
    '90d': 7776000,
    '365d': 31536000
  };
  var MAX_CUSTOM_WINDOW_FUTURE_SECONDS = 300;
  var URL_KEYS = ['range', 'from', 'to', 'lens', 'event', 'floor', 'cell'];
  var URL_QUERY_KEYS = {
    hm_range: 'range',
    hm_from: 'from',
    hm_to: 'to',
    hm_lens: 'lens',
    hm_event: 'event',
    hm_floor: 'floor',
    hm_cell: 'cell'
  };
  var SCENE_STATES = {
    ok: true,
    empty: true,
    insufficient_sample: true,
    missing_coordinates: true,
    floors_unavailable: true,
    weak_projection: true,
    too_many_events: true
  };
  var BLOCKED_SCENE_STATES = {
    missing_coordinates: true,
    floors_unavailable: true,
    weak_projection: true,
    too_many_events: true
  };

  function isRecord(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function own(object, key) {
    return hasOwn.call(object, key);
  }

  function exactKeys(value, expected) {
    if (!isRecord(value)) {
      return false;
    }
    var keys = Object.keys(value);
    if (keys.length !== expected.length) {
      return false;
    }
    for (var index = 0; index < expected.length; index += 1) {
      if (!own(value, expected[index])) {
        return false;
      }
    }
    return true;
  }

  function compactArray(value) {
    if (!Array.isArray(value) || Object.keys(value).length !== value.length) {
      return false;
    }
    for (var index = 0; index < value.length; index += 1) {
      if (!own(value, index)) {
        return false;
      }
    }
    return true;
  }

  function finiteNumber(value) {
    return typeof value === 'number' && Number.isFinite(value);
  }

  function safeInteger(value) {
    return Number.isSafeInteger(value);
  }

  function nonNegativeInteger(value) {
    return safeInteger(value) && value >= 0;
  }

  function positiveInteger(value) {
    return safeInteger(value) && value > 0;
  }

  function invalidScene() {
    throw new Error('invalid_scene');
  }

  function invalidUrl() {
    throw new Error('invalid_heatmap_url_state');
  }

  function canonicalCell(cell, x, y) {
    return cell === ('c' + x + '.' + y);
  }

  function parseCellId(cell) {
    if (typeof cell !== 'string') {
      return null;
    }
    var match = CELL.exec(cell);
    if (!match) {
      return null;
    }
    var x = Number(match[1]);
    var y = Number(match[2]);
    if (!safeInteger(x) || !safeInteger(y) || x > 127 || y > 127) {
      return null;
    }
    return {cell: cell, gridX: x, gridY: y};
  }

  function exactStringArray(value, expected) {
    if (!compactArray(value) || value.length !== expected.length) {
      return false;
    }
    for (var index = 0; index < expected.length; index += 1) {
      if (value[index] !== expected[index]) {
        return false;
      }
    }
    return true;
  }

  function cloneQuery(query) {
    return {
      game: query.game,
      map: query.map,
      player: query.player,
      from: query.from,
      to: query.to,
      event: query.event,
      lens: query.lens,
      floor: query.floor,
      lang: query.lang
    };
  }

  function validateQuery(query) {
    if (!exactKeys(query, ['game', 'map', 'player', 'from', 'to', 'event', 'lens', 'floor', 'lang'])
      || typeof query.game !== 'string' || !TOKEN.test(query.game)
      || typeof query.map !== 'string' || !TOKEN.test(query.map)
      || !nonNegativeInteger(query.player)
      || !safeInteger(query.from) || !safeInteger(query.to) || query.from >= query.to
      || (query.event !== 'kills' && query.event !== 'deaths' && query.event !== 'both')
      || (query.lens !== 'overview' && query.lens !== 'me' && query.lens !== 'difference')
      || typeof query.floor !== 'string'
      || typeof query.lang !== 'string' || (query.lang !== 'en' && query.lang !== 'ru')
      || ((query.lens === 'me' || query.lens === 'difference') && query.player <= 0)
      || (query.lens === 'difference' && query.event === 'both')) {
      invalidScene();
    }
    if (query.floor !== 'all' && !TOKEN.test(query.floor)) {
      invalidScene();
    }
  }

  function validateMap(map, query) {
    if (!exactKeys(map, ['game', 'realgame', 'name', 'image', 'projectionHash', 'floorConfigHash'])
      || map.game !== query.game || map.name !== query.map
      || typeof map.realgame !== 'string' || !TOKEN.test(map.realgame)
      || typeof map.projectionHash !== 'string' || !HASH.test(map.projectionHash)
      || typeof map.floorConfigHash !== 'string' || !HASH.test(map.floorConfigHash)
      || !exactKeys(map.image, ['url', 'width', 'height'])
      || typeof map.image.url !== 'string' || map.image.url.length === 0
      || !positiveInteger(map.image.width) || !positiveInteger(map.image.height)) {
      invalidScene();
    }
  }

  function validateFloors(floors, query, activeFloor, state) {
    if (!compactArray(floors) || activeFloor !== query.floor) {
      invalidScene();
    }
    var seen = Object.create(null);
    var requested = null;
    for (var index = 0; index < floors.length; index += 1) {
      var floor = floors[index];
      if (!exactKeys(floor, ['id', 'label', 'count', 'available'].concat(['regions', 'blocked'].filter(function (key) { return own(floor, key); })))
        || typeof floor.id !== 'string' || !TOKEN.test(floor.id)
        || typeof floor.label !== 'string'
        || !nonNegativeInteger(floor.count)
        || typeof floor.available !== 'boolean'
        || own(seen, floor.id)) {
        invalidScene();
      }
      ['regions', 'blocked'].forEach(function (key) {
        if (own(floor, key) && (!compactArray(floor[key]) || floor[key].length > 8
          || !floor[key].every(function (p) { return compactArray(p) && p.length >= 3 && p.length <= 32
            && p.every(function (v) { return compactArray(v) && v.length === 2 && v.every(function (n) { return safeInteger(n) && Math.abs(n) <= 200000000; }); }); }))) invalidScene();
      });
      seen[floor.id] = true;
      if (floor.id === query.floor) {
        requested = floor;
      }
    }
    if (query.floor !== 'all' && (!requested
      || ((state === 'ok' || state === 'insufficient_sample') && !requested.available))) {
      invalidScene();
    }
  }

  function validateGrid(grid) {
    if (!exactKeys(grid, ['bucketSize', 'width', 'height', 'fields'])
      || !positiveInteger(grid.bucketSize)
      || !positiveInteger(grid.width) || grid.width > 128
      || !positiveInteger(grid.height) || grid.height > 128
      || !exactStringArray(grid.fields, ['cell', 'x', 'y', 'kills', 'deaths'])) {
      invalidScene();
    }
  }

  function parseLayerRows(rows, grid) {
    if (!compactArray(rows)) {
      invalidScene();
    }
    var byCell = Object.create(null);
    var normalized = [];
    var previousY = -1;
    var previousX = -1;
    for (var index = 0; index < rows.length; index += 1) {
      var row = rows[index];
      if (!compactArray(row) || row.length !== 5
        || typeof row[0] !== 'string'
        || !nonNegativeInteger(row[1]) || !nonNegativeInteger(row[2])
        || !nonNegativeInteger(row[3]) || !nonNegativeInteger(row[4])
        || row[1] >= grid.width || row[2] >= grid.height
        || !canonicalCell(row[0], row[1], row[2])
        || own(byCell, row[0])
        || row[2] < previousY || (row[2] === previousY && row[1] <= previousX)) {
        invalidScene();
      }
      var cell = {
        cell: row[0],
        gridX: row[1],
        gridY: row[2],
        kills: row[3],
        deaths: row[4]
      };
      byCell[cell.cell] = cell;
      normalized.push(cell);
      previousY = cell.gridY;
      previousX = cell.gridX;
    }
    return {rows: normalized, byCell: byCell};
  }

  function validateLayerCompatibility(total, me, others) {
    if (total.rows.length !== me.rows.length || total.rows.length !== others.rows.length) {
      invalidScene();
    }
    for (var index = 0; index < total.rows.length; index += 1) {
      var totalCell = total.rows[index];
      var meCell = me.rows[index];
      var othersCell = others.rows[index];
      if (totalCell.kills + totalCell.deaths === 0
        || totalCell.cell !== meCell.cell || totalCell.cell !== othersCell.cell
        || totalCell.gridX !== meCell.gridX || totalCell.gridX !== othersCell.gridX
        || totalCell.gridY !== meCell.gridY || totalCell.gridY !== othersCell.gridY
        || meCell.kills > totalCell.kills || meCell.deaths > totalCell.deaths
        || othersCell.kills !== totalCell.kills - meCell.kills
        || othersCell.deaths !== totalCell.deaths - meCell.deaths) {
        invalidScene();
      }
    }
  }

  function parseComparison(comparison, grid, total, me, others, query, state) {
    if (!exactKeys(comparison, ['fields', 'bins', 'personalSample', 'otherSample'])
      || !exactStringArray(comparison.fields, ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'])
      || !compactArray(comparison.bins)
      || !nonNegativeInteger(comparison.personalSample)
      || !nonNegativeInteger(comparison.otherSample)) {
      invalidScene();
    }

    var channel = query.event;
    var expectedPersonal = 0;
    var expectedOthers = 0;
    if (channel !== 'both') {
      for (var layerIndex = 0; layerIndex < me.rows.length; layerIndex += 1) {
        expectedPersonal += channel === 'kills' ? me.rows[layerIndex].kills : me.rows[layerIndex].deaths;
        expectedOthers += channel === 'kills' ? others.rows[layerIndex].kills : others.rows[layerIndex].deaths;
      }
    }
    if (comparison.personalSample !== expectedPersonal || comparison.otherSample !== expectedOthers) {
      invalidScene();
    }

    var byCell = Object.create(null);
    var normalized = [];
    var previousY = -1;
    var previousX = -1;
    for (var index = 0; index < comparison.bins.length; index += 1) {
      var row = comparison.bins[index];
      if (!compactArray(row) || row.length !== 6
        || typeof row[0] !== 'string'
        || !nonNegativeInteger(row[1]) || !nonNegativeInteger(row[2])
        || !finiteNumber(row[3]) || !finiteNumber(row[4]) || !nonNegativeInteger(row[5])
        || row[1] >= grid.width || row[2] >= grid.height
        || !canonicalCell(row[0], row[1], row[2])
        || own(byCell, row[0])
        || row[2] < previousY || (row[2] === previousY && row[1] <= previousX)) {
        invalidScene();
      }
      var totalCell = total.byCell[row[0]];
      var meCell = me.byCell[row[0]];
      var othersCell = others.byCell[row[0]];
      if (!totalCell || !meCell || !othersCell
        || totalCell.gridX !== row[1] || totalCell.gridY !== row[2]) {
        invalidScene();
      }
      var expectedSample = channel === 'kills'
        ? meCell.kills + othersCell.kills
        : meCell.deaths + othersCell.deaths;
      if (row[5] !== expectedSample
        || (channel === 'kills' && row[4] !== 0)
        || (channel === 'deaths' && row[3] !== 0)) {
        invalidScene();
      }
      var bin = {
        cell: row[0],
        gridX: row[1],
        gridY: row[2],
        killDelta: row[3],
        deathDelta: row[4],
        sample: row[5]
      };
      byCell[bin.cell] = bin;
      normalized.push(bin);
      previousY = bin.gridY;
      previousX = bin.gridX;
    }

    if (query.lens !== 'difference' && normalized.length !== 0) {
      invalidScene();
    }
    if (query.lens === 'difference' && state === 'ok'
      && (normalized.length !== total.rows.length || comparison.personalSample < 3)) {
      invalidScene();
    }
    if (state === 'insufficient_sample'
      && (query.lens !== 'difference' || comparison.personalSample >= 3 || normalized.length !== 0)) {
      invalidScene();
    }
    if (normalized.length > 0) {
      if (query.lens !== 'difference' || channel === 'both' || normalized.length !== total.rows.length) {
        invalidScene();
      }
      for (var rowIndex = 0; rowIndex < normalized.length; rowIndex += 1) {
        if (normalized[rowIndex].cell !== total.rows[rowIndex].cell) {
          invalidScene();
        }
      }
    }
    return {rows: normalized, byCell: byCell};
  }

  function validateMetricObject(metrics, required) {
    if (!isRecord(metrics)) {
      invalidScene();
    }
    for (var index = 0; index < required.length; index += 1) {
      if (!own(metrics, required[index]) || !nonNegativeInteger(metrics[required[index]])) {
        invalidScene();
      }
    }
    var keys = Object.keys(metrics);
    for (var keyIndex = 0; keyIndex < keys.length; keyIndex += 1) {
      if (!finiteNumber(metrics[keys[keyIndex]]) || metrics[keys[keyIndex]] < 0) {
        invalidScene();
      }
    }
  }

  function validateHistogramRows(rows) {
    if (!compactArray(rows)) {
      invalidScene();
    }
    for (var index = 0; index < rows.length; index += 1) {
      var row = rows[index];
      if (!exactKeys(row, ['z', 'count'])
        || !safeInteger(row.z) || row.z < HEATMAP_Z_MIN || row.z > HEATMAP_Z_MAX
        || !nonNegativeInteger(row.count)) {
        invalidScene();
      }
    }
  }

  function cloneHistogramRows(rows) {
    var output = [];
    for (var index = 0; index < rows.length; index += 1) {
      output.push({z: rows[index].z, count: rows[index].count});
    }
    return output;
  }

  function validateCoverage(metrics) {
    if (!exactKeys(metrics, [
      'sourceRows', 'candidate', 'validXY', 'validZ', 'zHistogram',
      'missingCoordinates', 'malformedCoordinates', 'assigned', 'unassigned',
      'xyCoverage', 'zCoverage', 'projected', 'inBounds', 'outOfBounds', 'projectionCoverage'
    ])) {
      invalidScene();
    }
    for (var index = 0; index < 9; index += 1) {
      var countKey = [
        'sourceRows', 'candidate', 'validXY', 'validZ', 'missingCoordinates',
        'malformedCoordinates', 'assigned', 'unassigned', 'projected'
      ][index];
      if (!nonNegativeInteger(metrics[countKey])) {
        invalidScene();
      }
    }
    for (index = 0; index < 3; index += 1) {
      var boundedKey = ['xyCoverage', 'zCoverage', 'projectionCoverage'][index];
      if (!finiteNumber(metrics[boundedKey]) || metrics[boundedKey] < 0 || metrics[boundedKey] > 1) {
        invalidScene();
      }
    }
    if (!nonNegativeInteger(metrics.inBounds) || !nonNegativeInteger(metrics.outOfBounds)) {
      invalidScene();
    }
    validateHistogramRows(metrics.zHistogram);
  }

  function cloneCoverage(metrics) {
    var output = cloneMetricObject(metrics);
    output.zHistogram = cloneHistogramRows(metrics.zHistogram);
    return output;
  }

  function cloneMetricObject(metrics) {
    var output = {};
    var keys = Object.keys(metrics);
    for (var index = 0; index < keys.length; index += 1) {
      output[keys[index]] = metrics[keys[index]];
    }
    return output;
  }

  function validateWarnings(warnings) {
    if (!compactArray(warnings)) {
      invalidScene();
    }
    for (var index = 0; index < warnings.length; index += 1) {
      if (typeof warnings[index] !== 'string' || warnings[index].length === 0) {
        invalidScene();
      }
    }
  }

  function validateFallback(fallback) {
    if (!exactKeys(fallback, ['v1', 'jpeg', 'thumbnail'])
      || typeof fallback.v1 !== 'string' || fallback.v1.length === 0
      || typeof fallback.jpeg !== 'string' || fallback.jpeg.length === 0
      || typeof fallback.thumbnail !== 'string' || fallback.thumbnail.length === 0) {
      invalidScene();
    }
  }

  function HeatmapExplorerScene(payload) {
    if (!exactKeys(payload, [
      'schemaVersion', 'state', 'query', 'map', 'floors', 'activeFloor', 'grid',
      'layers', 'comparison', 'coverage', 'summary', 'warnings', 'fallback'
    ].concat(own(payload, 'surfaces') ? ['surfaces'] : [])) || payload.schemaVersion !== 2
      || !SCENE_STATES[payload.state]) {
      invalidScene();
    }

    validateQuery(payload.query);
    validateMap(payload.map, payload.query);
    validateFloors(payload.floors, payload.query, payload.activeFloor, payload.state);
    validateGrid(payload.grid);
    if (!exactKeys(payload.layers, ['total', 'me', 'others'])) {
      invalidScene();
    }
    var total = parseLayerRows(payload.layers.total, payload.grid);
    var me = parseLayerRows(payload.layers.me, payload.grid);
    var others = parseLayerRows(payload.layers.others, payload.grid);
    validateLayerCompatibility(total, me, others);
    var comparison = parseComparison(
      payload.comparison, payload.grid, total, me, others, payload.query, payload.state
    );
    if (payload.state === 'empty'
      && (total.rows.length !== 0 || me.rows.length !== 0 || others.rows.length !== 0 || comparison.rows.length !== 0)) {
      invalidScene();
    }
    if ((payload.state === 'ok' || payload.state === 'insufficient_sample') && total.rows.length === 0) {
      invalidScene();
    }
    validateCoverage(payload.coverage);
    validateMetricObject(payload.summary, ['rowsRead', 'sourceRows', 'personalSample', 'otherSample']);
    validateWarnings(payload.warnings);
    validateFallback(payload.fallback);
    this.surfaces = own(payload, 'surfaces') ? validateSurfaces(payload.surfaces, payload) : null;
    this._denseCache = Object.create(null);

    this.state = payload.state;
    this.query = cloneQuery(payload.query);
    this.map = {
      game: payload.map.game,
      realgame: payload.map.realgame,
      name: payload.map.name,
      image: {
        url: payload.map.image.url,
        width: payload.map.image.width,
        height: payload.map.image.height
      },
      projectionHash: payload.map.projectionHash,
      floorConfigHash: payload.map.floorConfigHash
    };
    this.grid = {
      bucketSize: payload.grid.bucketSize,
      width: payload.grid.width,
      height: payload.grid.height
    };
    this.activeFloor = payload.activeFloor;
    this.floors = payload.floors.map(function (floor) {
      return {
        id: floor.id,
        label: floor.label,
        count: floor.count,
        available: floor.available,
        regions: floor.regions ? floor.regions.map(function (p) { return p.map(function (v) { return v.slice(); }); }) : [],
        blocked: floor.blocked ? floor.blocked.map(function (p) { return p.map(function (v) { return v.slice(); }); }) : []
      };
    });
    this.coverage = cloneCoverage(payload.coverage);
    this.summary = cloneMetricObject(payload.summary);
    this.warnings = payload.warnings.slice();
    this.fallback = {
      v1: payload.fallback.v1,
      jpeg: payload.fallback.jpeg,
      thumbnail: payload.fallback.thumbnail
    };
    this._layers = {total: total, me: me, others: others};
    this._comparison = comparison;
  }

  HeatmapExplorerScene.prototype.dense = function (layer, channel) {
    var allowedLayer = layer === 'total' || layer === 'me' || layer === 'others' || layer === 'difference';
    var allowedChannel = channel === 'kills' || channel === 'deaths' || (layer !== 'difference' && channel === 'both');
    if (!allowedLayer || !allowedChannel) {
      throw new Error('invalid_dense_selection');
    }
    var cacheKey = layer + ':' + channel;
    if (this._denseCache[cacheKey]) return this._denseCache[cacheKey];

    var size = this.grid.width * this.grid.height;
    var values = new Float32Array(size);
    var opacity = new Float32Array(size);
    var occupied = [];
    var maxAbs = 0;
    var index;
    var row;
    var value;

    if (layer === 'difference') {
      for (index = 0; index < this._comparison.rows.length; index += 1) {
        row = this._comparison.rows[index];
        value = channel === 'kills' ? row.killDelta : row.deathDelta;
        var differenceOffset = row.gridY * this.grid.width + row.gridX;
        values[differenceOffset] = value;
        var personal = this._layers.me.byCell[row.cell];
        var personalCount = channel === 'kills' ? personal.kills : personal.deaths;
        opacity[differenceOffset] = personalCount < 3 ? 0.22 : 1;
        maxAbs = Math.max(maxAbs, Math.abs(value));
        if (value !== 0) {
          occupied.push(row);
        }
      }
    } else {
      var rows = this._layers[layer].rows;
      for (index = 0; index < rows.length; index += 1) {
        row = rows[index];
        value = channel === 'kills' ? row.kills : (channel === 'deaths' ? row.deaths : row.kills + row.deaths);
        var offset = row.gridY * this.grid.width + row.gridX;
        values[offset] = value;
        opacity[offset] = value !== 0 ? 1 : 0;
        maxAbs = Math.max(maxAbs, Math.abs(value));
        if (value !== 0) {
          occupied.push(row);
        }
      }
    }

    occupied.sort(function (left, right) {
      return left.gridY - right.gridY || left.gridX - right.gridX;
    });
    return (this._denseCache[cacheKey] = {values: values, opacity: opacity, maxAbs: maxAbs, occupied: occupied});
  };

  HeatmapExplorerScene.prototype._cellAt = function (gridX, gridY) {
    var cell = 'c' + gridX + '.' + gridY;
    var known = this._layers.total.byCell[cell];
    return known || {cell: cell, gridX: gridX, gridY: gridY};
  };

  HeatmapExplorerScene.prototype.cellFromPointer = function (x, y, view, camera) {
    if (!finiteNumber(x) || !finiteNumber(y) || !isRecord(view)
      || !finiteNumber(view.left) || !finiteNumber(view.top)
      || !finiteNumber(view.width) || !finiteNumber(view.height)
      || view.width <= 0 || view.height <= 0) {
      return null;
    }
    var transform = camera && camera.state ? camera.state : camera;
    var zoom = transform && finiteNumber(transform.zoom) && transform.zoom > 0 ? transform.zoom : 1;
    var panX = transform && finiteNumber(transform.panX) ? transform.panX : 0;
    var panY = transform && finiteNumber(transform.panY) ? transform.panY : 0;
    var localX = (x - view.left - panX) / zoom;
    var localY = (y - view.top - panY) / zoom;
    if (localX < 0 || localY < 0 || localX >= view.width || localY >= view.height) {
      return null;
    }
    var gridX = Math.floor(localX * this.grid.width / view.width);
    var gridY = Math.floor(localY * this.grid.height / view.height);
    if (gridX < 0 || gridY < 0 || gridX >= this.grid.width || gridY >= this.grid.height) {
      return null;
    }
    return this._cellAt(gridX, gridY);
  };

  HeatmapExplorerScene.prototype.nextOccupied = function (cellId, direction, layer, channel) {
    if (direction !== 'left' && direction !== 'right' && direction !== 'up' && direction !== 'down') {
      return null;
    }
    var occupied = this.dense(layer, channel).occupied;
    if (occupied.length === 0) {
      return null;
    }
    var parsed = parseCellId(cellId);
    var current = null;
    if (parsed) {
      for (var index = 0; index < occupied.length; index += 1) {
        if (occupied[index].cell === parsed.cell) {
          current = occupied[index];
          break;
        }
      }
    }

    var candidates;
    if (current) {
      candidates = occupied.filter(function (candidate) {
        return (direction === 'left' && candidate.gridX < current.gridX)
          || (direction === 'right' && candidate.gridX > current.gridX)
          || (direction === 'up' && candidate.gridY < current.gridY)
          || (direction === 'down' && candidate.gridY > current.gridY);
      });
      candidates.sort(function (left, right) {
        var leftPrimary;
        var rightPrimary;
        var leftPerpendicular;
        var rightPerpendicular;
        if (direction === 'left' || direction === 'right') {
          leftPrimary = direction === 'left' ? current.gridX - left.gridX : left.gridX - current.gridX;
          rightPrimary = direction === 'left' ? current.gridX - right.gridX : right.gridX - current.gridX;
          leftPerpendicular = Math.abs(left.gridY - current.gridY);
          rightPerpendicular = Math.abs(right.gridY - current.gridY);
        } else {
          leftPrimary = direction === 'up' ? current.gridY - left.gridY : left.gridY - current.gridY;
          rightPrimary = direction === 'up' ? current.gridY - right.gridY : right.gridY - current.gridY;
          leftPerpendicular = Math.abs(left.gridX - current.gridX);
          rightPerpendicular = Math.abs(right.gridX - current.gridX);
        }
        return leftPrimary - rightPrimary || leftPerpendicular - rightPerpendicular
          || left.gridY - right.gridY || left.gridX - right.gridX;
      });
      return candidates.length ? candidates[0] : null;
    }

    candidates = occupied.slice();
    candidates.sort(function (left, right) {
      var leftEdge;
      var rightEdge;
      if (direction === 'left') {
        leftEdge = left.gridX;
        rightEdge = right.gridX;
      } else if (direction === 'right') {
        leftEdge = -left.gridX;
        rightEdge = -right.gridX;
      } else if (direction === 'up') {
        leftEdge = left.gridY;
        rightEdge = right.gridY;
      } else {
        leftEdge = -left.gridY;
        rightEdge = -right.gridY;
      }
      return leftEdge - rightEdge || left.gridY - right.gridY || left.gridX - right.gridX;
    });
    return candidates[0];
  };

  HeatmapExplorerScene.prototype.cellSummary = function (cellId) {
    var total = this._layers.total.byCell[cellId];
    if (!total) {
      return null;
    }
    var me = this._layers.me.byCell[cellId];
    var others = this._layers.others.byCell[cellId];
    var comparison = this._comparison.byCell[cellId] || {
      killDelta: 0,
      deathDelta: 0,
      sample: 0
    };
    return {
      cell: total.cell,
      gridX: total.gridX,
      gridY: total.gridY,
      total: {kills: total.kills, deaths: total.deaths},
      me: {kills: me.kills, deaths: me.deaths},
      others: {kills: others.kills, deaths: others.deaths},
      comparison: {
        killDelta: comparison.killDelta,
        deathDelta: comparison.deathDelta,
        sample: comparison.sample
      }
    };
  };

  function numeric(value, fallback) {
    return finiteNumber(value) ? value : fallback;
  }

  function HeatmapExplorerCamera(options) {
    options = isRecord(options) ? options : {};
    this.minZoom = numeric(options.minZoom, 1);
    this.maxZoom = numeric(options.maxZoom, 8);
    if (this.minZoom <= 0) {
      this.minZoom = 1;
    }
    if (this.maxZoom < this.minZoom) {
      this.maxZoom = this.minZoom;
    }
    this.viewportWidth = Math.max(0, numeric(options.viewportWidth, 0));
    this.viewportHeight = Math.max(0, numeric(options.viewportHeight, 0));
    this.contentWidth = Math.max(0, numeric(options.contentWidth, 0));
    this.contentHeight = Math.max(0, numeric(options.contentHeight, 0));
    this.state = {
      zoom: this.minZoom,
      panX: 0,
      panY: 0,
      reducedMotion: options.reducedMotion === true
    };
    this._destroyed = false;
  }

  HeatmapExplorerCamera.prototype._clamp = function () {
    this.state.zoom = Math.max(this.minZoom, Math.min(this.maxZoom, this.state.zoom));
    if (this.state.zoom <= this.minZoom) {
      this.state.zoom = this.minZoom;
      this.state.panX = 0;
      this.state.panY = 0;
      return;
    }
    var minX = Math.min(0, this.viewportWidth - this.contentWidth * this.state.zoom);
    var minY = Math.min(0, this.viewportHeight - this.contentHeight * this.state.zoom);
    this.state.panX = Math.max(minX, Math.min(0, this.state.panX));
    this.state.panY = Math.max(minY, Math.min(0, this.state.panY));
  };

  HeatmapExplorerCamera.prototype.setViewport = function (viewportWidth, viewportHeight, contentWidth, contentHeight) {
    this.viewportWidth = Math.max(0, numeric(viewportWidth, 0));
    this.viewportHeight = Math.max(0, numeric(viewportHeight, 0));
    this.contentWidth = Math.max(0, numeric(contentWidth, 0));
    this.contentHeight = Math.max(0, numeric(contentHeight, 0));
    this._clamp();
    return this.transform();
  };

  HeatmapExplorerCamera.prototype.panBy = function (dx, dy) {
    if (this.state.zoom <= this.minZoom) {
      return this.transform();
    }
    this.state.panX += numeric(dx, 0);
    this.state.panY += numeric(dy, 0);
    this._clamp();
    return this.transform();
  };

  HeatmapExplorerCamera.prototype.zoomAt = function (factor, anchorX, anchorY) {
    if (!finiteNumber(factor) || factor <= 0) {
      return this.transform();
    }
    var oldZoom = this.state.zoom;
    var newZoom = Math.max(this.minZoom, Math.min(this.maxZoom, oldZoom * factor));
    if (newZoom <= this.minZoom) {
      return this.reset();
    }
    var x = numeric(anchorX, this.viewportWidth / 2);
    var y = numeric(anchorY, this.viewportHeight / 2);
    this.state.panX = x - (x - this.state.panX) * newZoom / oldZoom;
    this.state.panY = y - (y - this.state.panY) * newZoom / oldZoom;
    this.state.zoom = newZoom;
    this._clamp();
    return this.transform();
  };

  HeatmapExplorerCamera.prototype.handleKey = function (key) {
    if (key === '+' || key === '=') {
      this.zoomAt(1.25, this.viewportWidth / 2, this.viewportHeight / 2);
      return true;
    }
    if (key === '-') {
      this.zoomAt(0.8, this.viewportWidth / 2, this.viewportHeight / 2);
      return true;
    }
    if (key === 'Home') {
      this.reset();
      return true;
    }
    if (this.state.zoom <= this.minZoom) {
      return false;
    }
    if (key === 'ArrowLeft') {
      this.panBy(-48, 0);
      return true;
    }
    if (key === 'ArrowRight') {
      this.panBy(48, 0);
      return true;
    }
    if (key === 'ArrowUp') {
      this.panBy(0, -48);
      return true;
    }
    if (key === 'ArrowDown') {
      this.panBy(0, 48);
      return true;
    }
    return false;
  };

  HeatmapExplorerCamera.prototype.reset = function () {
    this.state.zoom = this.minZoom;
    this.state.panX = 0;
    this.state.panY = 0;
    return this.transform();
  };

  function cssNumber(value) {
    var rounded = Math.round(value * 1000) / 1000;
    return String(rounded);
  }

  HeatmapExplorerCamera.prototype.transform = function () {
    return {
      zoom: this.state.zoom,
      panX: this.state.panX,
      panY: this.state.panY,
      css: 'translate3d(' + cssNumber(this.state.panX) + 'px, '
        + cssNumber(this.state.panY) + 'px, 0) scale(' + cssNumber(this.state.zoom) + ')',
      animate: !this.state.reducedMotion
    };
  };

  HeatmapExplorerCamera.prototype.destroy = function () {
    this._destroyed = true;
  };

  function decodeQueryPart(value) {
    try {
      return decodeURIComponent(value.replace(/\+/g, ' '));
    } catch (error) {
      invalidUrl();
    }
  }

  function inspectSearch(search) {
    if (typeof search !== 'string') {
      invalidUrl();
    }
    var input = search.charAt(0) === '?' ? search.slice(1) : search;
    var known = Object.create(null);
    var unrelated = [];
    if (input === '') {
      return {known: known, unrelated: unrelated};
    }
    var parts = input.split('&');
    for (var index = 0; index < parts.length; index += 1) {
      var raw = parts[index];
      var separator = raw.indexOf('=');
      var rawKey = separator === -1 ? raw : raw.slice(0, separator);
      var rawValue = separator === -1 ? '' : raw.slice(separator + 1);
      var key = decodeQueryPart(rawKey);
      var value = decodeQueryPart(rawValue);
      if (key.slice(0, 3) === 'hm_') {
        var mapped = URL_QUERY_KEYS[key];
        if (!mapped || own(known, mapped)) {
          invalidUrl();
        }
        known[mapped] = value;
      } else {
        unrelated.push(raw);
      }
    }
    return {known: known, unrelated: unrelated};
  }

  function canonicalWindowNumber(value) {
    if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value)) {
      invalidUrl();
    }
    var number = Number(value);
    if (!safeInteger(number)) {
      invalidUrl();
    }
    return number;
  }

  function normalizeNowSeconds(options) {
    var value = options && own(options, 'nowSeconds') ? options.nowSeconds : null;
    if (typeof value === 'function') {
      try {
        value = value();
      } catch (error) {
        value = null;
      }
    }
    if (!finiteNumber(value)) {
      value = Date.now() / 1000;
    }
    value = Math.floor(value);
    return safeInteger(value) && value >= 0 ? value : 0;
  }

  function validateCustomWindow(from, to, nowSeconds) {
    if (from >= to || to - from > 315360000 || to > nowSeconds + MAX_CUSTOM_WINDOW_FUTURE_SECONDS) {
      invalidUrl();
    }
  }

  function validateUrlValues(values, present, options) {
    var output = {};
    var hasRange = present.range;
    var hasFrom = present.from;
    var hasTo = present.to;
    if (hasRange && (hasFrom || hasTo)) {
      invalidUrl();
    }
    if (hasFrom !== hasTo) {
      invalidUrl();
    }
    if (hasRange) {
      if (typeof values.range !== 'string' || !own(RANGE_SECONDS, values.range)) {
        invalidUrl();
      }
      output.range = values.range;
    }
    if (hasFrom) {
      var from = canonicalWindowNumber(values.from);
      var to = canonicalWindowNumber(values.to);
      validateCustomWindow(from, to, normalizeNowSeconds(options));
      output.from = from;
      output.to = to;
    }
    if (present.lens) {
      if (values.lens !== 'overview' && values.lens !== 'me' && values.lens !== 'difference') {
        invalidUrl();
      }
      output.lens = values.lens;
    }
    if (present.event) {
      if (values.event !== 'kills' && values.event !== 'deaths' && values.event !== 'both') {
        invalidUrl();
      }
      output.event = values.event;
    }
    if ((present.lens ? values.lens : 'overview') === 'difference'
      && (present.event ? values.event : 'both') === 'both') {
      invalidUrl();
    }
    if (present.floor) {
      if (typeof values.floor !== 'string' || (values.floor !== 'all' && !TOKEN.test(values.floor))) {
        invalidUrl();
      }
      output.floor = values.floor;
    }
    if (present.cell) {
      var cell = parseCellId(values.cell);
      if (!cell) {
        invalidUrl();
      }
      output.cell = cell.cell;
    }
    return output;
  }

  function parseUrlState(search, options) {
    var inspected = inspectSearch(search);
    var values = inspected.known;
    var present = {};
    for (var index = 0; index < URL_KEYS.length; index += 1) {
      present[URL_KEYS[index]] = own(values, URL_KEYS[index]);
    }
    return validateUrlValues(values, present, options);
  }

  function serializableValue(value, numberAllowed) {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    if (Array.isArray(value) || (typeof value === 'object' && value !== null)) {
      invalidUrl();
    }
    if (numberAllowed && safeInteger(value) && value >= 0) {
      return String(value);
    }
    if (typeof value !== 'string') {
      invalidUrl();
    }
    return value;
  }

  function serializeUrlState(search, state, options) {
    var inspected = inspectSearch(search);
    if (!isRecord(state)) {
      invalidUrl();
    }
    var values = {};
    var present = {};
    for (var index = 0; index < URL_KEYS.length; index += 1) {
      var key = URL_KEYS[index];
      var raw = own(state, key) ? state[key] : null;
      var value = serializableValue(raw, key === 'from' || key === 'to');
      present[key] = value !== null;
      values[key] = value;
    }
    var normalized = validateUrlValues(values, present, options);
    var result = [];
    if (own(normalized, 'range')) {
      result.push('hm_range=' + encodeURIComponent(normalized.range));
    }
    if (own(normalized, 'from')) {
      result.push('hm_from=' + encodeURIComponent(String(normalized.from)));
      result.push('hm_to=' + encodeURIComponent(String(normalized.to)));
    }
    if (own(normalized, 'lens')) {
      result.push('hm_lens=' + encodeURIComponent(normalized.lens));
    }
    if (own(normalized, 'event')) {
      result.push('hm_event=' + encodeURIComponent(normalized.event));
    }
    if (own(normalized, 'floor')) {
      result.push('hm_floor=' + encodeURIComponent(normalized.floor));
    }
    if (own(normalized, 'cell')) {
      result.push('hm_cell=' + encodeURIComponent(normalized.cell));
    }
    return result.concat(inspected.unrelated).length
      ? '?' + result.concat(inspected.unrelated).join('&')
      : '';
  }

  function HeatmapExplorerUrlState() {
  }

  HeatmapExplorerUrlState.parse = parseUrlState;
  HeatmapExplorerUrlState.serialize = serializeUrlState;

  function gaussianKernel1d(sigma, radius) {
    var kernel = new Float32Array(radius * 2 + 1), sum = 0, i;
    for (i = -radius; i <= radius; i++) {
      kernel[i + radius] = Math.exp(-i * i / (2 * sigma * sigma));
      sum += kernel[i + radius];
    }
    for (i = 0; i < kernel.length; i++) kernel[i] /= sum;
    return kernel;
  }

  function utcInputValue(seconds) {
    return safeInteger(seconds) ? new Date(seconds * 1000).toISOString().slice(0, 19) : '';
  }

  function utcInputSeconds(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(value)) invalidUrl();
    var full = value.length === 16 ? value + ':00' : value;
    var seconds = Date.parse(full + 'Z') / 1000;
    if (!safeInteger(seconds) || utcInputValue(seconds) !== full) invalidUrl();
    return seconds;
  }

  function regionContains(polygon, x, y) {
    var inside = false;
    for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      var a = polygon[j], b = polygon[i];
      if ((b[0] - a[0]) * (y - a[1]) === (b[1] - a[1]) * (x - a[0])
        && x >= Math.min(a[0], b[0]) && x <= Math.max(a[0], b[0]) && y >= Math.min(a[1], b[1]) && y <= Math.max(a[1], b[1])) return true;
      if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
    }
    return inside;
  }

  function sceneRegions(scene, kind) {
    var selected = scene.floors.filter(function (floor) { return floor.id === scene.activeFloor; })[0];
    return selected && selected[kind || 'regions'] ? selected[kind || 'regions'] : [];
  }

  function polygonTouchesCell(p, left, top, right, bottom) {
    if ([[left, top], [right, top], [right, bottom], [left, bottom]].some(function (v) { return regionContains(p, v[0], v[1]); })) return true;
    // Segment clipping against the cell catches even walls narrower than a bucket.
    return p.some(function (a, i) {
      var b = p[(i + 1) % p.length], low = 0, high = 1;
      for (var axis = 0; axis < 2; axis++) {
        var delta = b[axis] - a[axis], min = axis ? top : left, max = axis ? bottom : right;
        if (delta === 0) { if (a[axis] < min || a[axis] > max) return false; }
        else { var t1 = (min - a[axis]) / delta, t2 = (max - a[axis]) / delta; low = Math.max(low, Math.min(t1, t2)); high = Math.min(high, Math.max(t1, t2)); }
      }
      return low <= high;
    });
  }

  function regionGridMask(scene) {
    var regions = sceneRegions(scene), blocked = sceneRegions(scene, 'blocked');
    if (!regions.length && !blocked.length) return null;
    var grid = scene.grid, mask = new Uint8Array(grid.width * grid.height), bucket = grid.bucketSize;
    for (var y = 0; y < grid.height; y++) for (var x = 0; x < grid.width; x++) {
      var left = x * bucket, top = y * bucket, right = left + bucket, bottom = top + bucket;
      // Retain boundary cells containing actual data. The exact polygon clips pixels later.
      var occupied = scene.cellSummary('c' + x + '.' + y);
      var contains = !regions.length || regions.some(function (p) { return regionContains(p, left + bucket / 2, top + bucket / 2); });
      var wall = blocked.some(function (p) { return polygonTouchesCell(p, left, top, right, bottom); });
      mask[y * grid.width + x] = !wall && (contains || occupied && (occupied.total.kills > 0 || occupied.total.deaths > 0)) ? 1 : 0;
    }
    return mask;
  }

  function gaussianSmooth(input, width, height, kernel, mask) {
    var current = input, radius = Math.floor(kernel.length / 2);
    for (var axis = 0; axis < 2; axis++) {
      var output = new Float32Array(input.length);
      for (var y = 0; y < height; y++) {
        for (var x = 0; x < width; x++) {
          if (mask && !mask[y * width + x]) continue;
          var sum = 0, weight = 0;
          for (var offset = -radius; offset <= radius; offset++) {
            var sx = axis === 0 ? x + offset : x, sy = axis === 1 ? y + offset : y;
            if (sx < 0 || sy < 0 || sx >= width || sy >= height) continue;
            if (mask) {
              var blocked = false;
              for (var step = Math.min(0, offset); step <= Math.max(0, offset); step++) {
                var mx = axis === 0 ? x + step : x, my = axis === 1 ? y + step : y;
                if (!mask[my * width + mx]) { blocked = true; break; }
              }
              if (blocked) continue;
            }
            sum += current[sy * width + sx] * kernel[offset + radius];
            weight += kernel[offset + radius];
          }
          output[y * width + x] = weight ? sum / weight : 0;
        }
      }
      current = output;
    }
    return current;
  }

  function surfaceBytes(value, length) {
    if (typeof value !== 'string' || value.length !== Math.ceil(length / 3) * 4
      || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) throw new TypeError('invalid_surfaces');
    var raw = atob(value), bytes = new Uint8Array(length);
    if (raw.length !== length) throw new TypeError('invalid_surfaces');
    for (var i = 0; i < length; i++) bytes[i] = raw.charCodeAt(i);
    return bytes;
  }

  function validateSurfaces(s, payload) {
    if (!exactKeys(s, ['version','state','asset','fields','rows','allowedData','diagnostics']) || s.version !== 1
      || ['ready','missing_asset','invalid_asset','identity_mismatch','low_coverage'].indexOf(s.state) < 0
      || !exactStringArray(s.fields, ['node','kills','deaths','meKills','meDeaths'])
      || !compactArray(s.rows) || !exactKeys(s.diagnostics, ['candidate','assigned','missingZ','ambiguous','offSurface','excluded'])
      || !Object.keys(s.diagnostics).every(function (k) { return nonNegativeInteger(s.diagnostics[k]); })) invalidScene();
    if (!s.asset) {
      if (s.state === 'ready' || s.rows.length || s.allowedData !== '') invalidScene();
      return JSON.parse(JSON.stringify(s));
    }
    var a = s.asset;
    if (!exactKeys(a, ['url','sha256','grid','nodeCount','edgeCount'])
      || a.url !== 'hlstatsimg/heatmap-surfaces/cstrike/' + payload.map.name + '.json' || payload.map.realgame !== 'cstrike'
      || !SHA256.test(a.sha256) || !exactKeys(a.grid, ['width','height'])
      || !positiveInteger(a.grid.width) || a.grid.width > 512 || !positiveInteger(a.grid.height) || a.grid.height > 384
      || !positiveInteger(a.nodeCount) || a.nodeCount > 196608 || !nonNegativeInteger(a.edgeCount) || a.edgeCount > 393216
      || s.rows.length > a.nodeCount) invalidScene();
    var allowed = surfaceBytes(s.allowedData, a.nodeCount), last = -1, sum = 0, totals = [0,0,0,0];
    for (var i = 0; i < allowed.length; i++) if (allowed[i] > 1) invalidScene();
    s.rows.forEach(function (r) {
      if (!compactArray(r) || r.length !== 5 || !r.every(nonNegativeInteger) || r[0] <= last || r[0] >= a.nodeCount
        || !allowed[r[0]] || r[1] + r[2] === 0 || r[3] > r[1] || r[4] > r[2]) invalidScene();
      last = r[0]; sum += r[1] + r[2];
      for (var column=0;column<4;column++) totals[column] += r[column+1];
    });
    var d = s.diagnostics;
    if (d.candidate !== d.assigned + d.missingZ + d.ambiguous + d.offSurface + d.excluded
      || d.candidate !== payload.coverage.inBounds || d.candidate > 500000
      || (payload.state !== 'too_many_events' && sum !== d.assigned)
      || (s.state === 'ready' && d.candidate && d.assigned / d.candidate < 0.7)) invalidScene();
    if (payload.state !== 'too_many_events') {
      var limits = [0,0,0,0];
      payload.layers.total.forEach(function (r) { limits[0]+=r[3];limits[1]+=r[4]; });
      payload.layers.me.forEach(function (r) { limits[2]+=r[3];limits[3]+=r[4]; });
      if (totals.some(function (value,index) { return value > limits[index]; })) invalidScene();
    }
    var copy = JSON.parse(JSON.stringify(s)); copy.allowed = allowed; return copy;
  }

  function HeatmapSurfaceGraph(a, descriptor) {
    if (!exactKeys(a, ['schemaVersion','map','bspSha256','image','projection','grid','nodeCount','edgeCount','pixelData','heightData','edgeData'])
      || a.schemaVersion !== 1 || !SHA256.test(a.bspSha256) || !TOKEN.test(a.map)
      || !exactKeys(a.image, ['width','height','sha256']) || !positiveInteger(a.image.width) || !positiveInteger(a.image.height) || !SHA256.test(a.image.sha256)
      || !exactKeys(a.projection, ['xoffset','yoffset','scale','flipx','flipy','rotate','cropx1','cropx2','cropy1','cropy2'])
      || !Object.keys(a.projection).every(function (k) { return finiteNumber(a.projection[k]) || ((k === 'flipx' || k === 'flipy') && typeof a.projection[k] === 'boolean'); })
      || a.nodeCount !== descriptor.nodeCount || a.edgeCount !== descriptor.edgeCount
      || !exactKeys(a.grid, ['width','height']) || a.grid.width !== descriptor.grid.width || a.grid.height !== descriptor.grid.height
      || descriptor.url !== 'hlstatsimg/heatmap-surfaces/cstrike/' + a.map + '.json') throw new TypeError('invalid_surfaces');
    var n = a.nodeCount, e = a.edgeCount, w = a.grid.width, h = a.grid.height;
    if (!positiveInteger(n) || n > 196608 || !nonNegativeInteger(e) || e > 393216 || !positiveInteger(w) || w > 512 || !positiveInteger(h) || h > 384) throw new TypeError('invalid_surfaces');
    var pb = surfaceBytes(a.pixelData, n * 4), hb = surfaceBytes(a.heightData, n * 4), eb = surfaceBytes(a.edgeData, e * 8);
    var pv = new DataView(pb.buffer), hv = new DataView(hb.buffer), ev = new DataView(eb.buffer);
    this.pixels = new Uint32Array(n); this.heights = new Float32Array(n); this.edges = new Uint32Array(e * 2);
    var degrees = new Uint8Array(n), neighbors = new Int32Array(n * 4); neighbors.fill(-1);
    var i, j;
    for (i = 0; i < n; i++) {
      var p = pv.getUint32(i * 4, true), z = hv.getFloat32(i * 4, true);
      if (p >= w * h || !isFinite(z) || Math.abs(z) > 8388608 || (i && (p < this.pixels[i-1] || (p === this.pixels[i-1] && z <= this.heights[i-1])))) throw new TypeError('invalid_surfaces');
      this.pixels[i] = p; this.heights[i] = z;
    }
    for (i = 0; i < e; i++) {
      var left = ev.getUint32(i * 8, true), right = ev.getUint32(i * 8 + 4, true);
      if (left >= n || right >= n || left === right || degrees[left] >= 4 || degrees[right] >= 4) throw new TypeError('invalid_surfaces');
      var lp = this.pixels[left], rp = this.pixels[right];
      if (Math.abs(lp % w - rp % w) + Math.abs(Math.floor(lp / w) - Math.floor(rp / w)) !== 1) throw new TypeError('invalid_surfaces');
      for (j = 0; j < degrees[left]; j++) if (neighbors[left * 4 + j] === right) throw new TypeError('invalid_surfaces');
      neighbors[left * 4 + degrees[left]++] = right; neighbors[right * 4 + degrees[right]++] = left;
      this.edges[i * 2] = left; this.edges[i * 2 + 1] = right;
    }
    this.grid = {width:w,height:h}; this.image = a.image;
  }

  HeatmapSurfaceGraph.prototype.field = function (scene, layer, channel, appearance) {
    var s = scene.surfaces, n = this.pixels.length, g = this.grid, difference = layer === 'difference', both = channel === 'both';
    var allowed = new Uint8Array(s.allowed), values = new Float32Array(n * 4), next = new Float32Array(n * 4), i, c;
    var regions = sceneRegions(scene), blocked = sceneRegions(scene, 'blocked');
    var dx = scene.map.image.width / g.width, dy = scene.map.image.height / g.height;
    for (i = 0; (regions.length || blocked.length) && i < n; i++) {
      var x = this.pixels[i] % g.width * dx, y = Math.floor(this.pixels[i] / g.width) * dy;
      if ((regions.length && !regions.some(function (p) { return regionContains(p, x + dx/2, y + dy/2); }))
        || blocked.some(function (p) { return polygonTouchesCell(p, x, y, x + dx, y + dy); })) allowed[i] = 0;
    }
    s.rows.forEach(function (r) {
      if (!allowed[r[0]]) return;
      var total = channel === 'kills' ? r[1] : (channel === 'deaths' ? r[2] : r[1]+r[2]);
      var me = channel === 'kills' ? r[3] : (channel === 'deaths' ? r[4] : r[3]+r[4]);
      var value = difference ? me / Math.max(1, scene.summary.personalSample) - (total-me) / Math.max(1, scene.summary.otherSample)
        : (layer === 'me' ? me : (layer === 'others' ? total-me : total));
      var off = r[0] * 4, support = Math.abs(value);
      values[off] = Math.max(0,value); values[off+1] = Math.max(0,-value);
      if (both) {
        values[off] = layer === 'me' ? r[3] : (layer === 'others' ? r[1]-r[3] : r[1]);
        values[off+1] = layer === 'me' ? r[4] : (layer === 'others' ? r[2]-r[4] : r[2]);
      }
      values[off+2] = support; values[off+3] = support * (difference && me < 3 ? 0.22 : 1);
    });
    // Compact default; Difference retains its established support/confidence spread.
    var edges = this.edges, lanes = difference ? 4 : (both ? 2 : 1), steps = difference || appearance === 'soft' ? 24 : 8;
    var diffusionAlpha = difference ? 0.24 : 0.18;
    for (var step = 0; step < steps; step++) {
      next.set(values);
      for (i = 0; i < edges.length; i += 2) {
        var a = edges[i], b = edges[i+1];
        if (!allowed[a] || !allowed[b]) continue;
        a *= 4; b *= 4;
        for (c = 0; c < lanes; c++) { var flow = diffusionAlpha * (values[a+c] - values[b+c]); next[a+c] -= flow; next[b+c] += flow; }
      }
      var swap = values; values = next; next = swap;
    }
    var output = new Float32Array(g.width*g.height*2), opacity = new Float32Array(g.width*g.height), max = 0;
    for (i = 0; i < n; i++) {
      if (!allowed[i]) continue; // Final clip is independent of propagation barriers.
      var pixel = this.pixels[i], off = i*4, strength = Math.max(values[off],values[off+1]);
      // Choose one strongest surface, never sum or mix stacked floors.
      if (strength > Math.max(output[pixel*2],output[pixel*2+1])) {
        output[pixel*2] = values[off]; output[pixel*2+1] = values[off+1];
        opacity[pixel] = difference ? (values[off+2] > 0 ? values[off+3]/values[off+2] : 0) : 1;
      }
      max = Math.max(max,strength);
    }
    return {values:output,opacity:opacity,maxAbs:max,width:g.width,height:g.height,constrained:true};
  };

  var surfaceDownloads = new Map();
  function loadSurfaceGraph(fetcher, cryptography, descriptor) {
    var key = descriptor.url + '?' + descriptor.sha256;
    if (surfaceDownloads.has(key)) {
      var cached = surfaceDownloads.get(key); surfaceDownloads.delete(key); surfaceDownloads.set(key,cached); return cached;
    }
    if (!cryptography || !cryptography.subtle) return Promise.reject(new Error('surface_hash_unavailable'));
    var promise = Promise.resolve().then(function () { return fetcher(key, {credentials:'same-origin'}); }).then(function (response) {
      if (!response || response.ok === false || (response.headers && Number(response.headers.get('content-length')) > 6500000)) throw new Error('surface_unavailable');
      if (!response.body || !response.body.getReader) return response.text().then(function (text) {
        if (text.length > 6500000) throw new Error('surface_size'); return text;
      });
      var reader = response.body.getReader(), chunks = [], size = 0;
      function read() { return reader.read().then(function (part) {
        if (part.done) { var bytes = new Uint8Array(size), offset = 0; chunks.forEach(function (chunk) { bytes.set(chunk, offset); offset += chunk.length; }); return new TextDecoder().decode(bytes); }
        size += part.value.length;
        if (size > 6500000) { reader.cancel(); throw new Error('surface_size'); }
        chunks.push(part.value); return read();
      }); } return read();
    }).then(function (text) {
      return cryptography.subtle.digest('SHA-256', new TextEncoder().encode(text)).then(function (hash) {
        var hex = Array.from(new Uint8Array(hash)).map(function (v) { return v.toString(16).padStart(2,'0'); }).join('');
        if (hex !== descriptor.sha256) throw new Error('surface_identity');
        return new HeatmapSurfaceGraph(JSON.parse(text), descriptor);
      });
    }).catch(function (error) { if (surfaceDownloads.get(key) === promise) surfaceDownloads.delete(key); throw error; });
    // A small shared LRU bounds memory while retaining repeated filter requests.
    if (surfaceDownloads.size >= 3) surfaceDownloads.delete(surfaceDownloads.keys().next().value);
    surfaceDownloads.set(key,promise); return promise;
  }

  function presentationField(dense, width, height, smooth, difference, mask, appearance) {
    var n = dense.values.length, positive = new Float32Array(n), negative = new Float32Array(n);
    var support = new Float32Array(n), weighted = new Float32Array(n), i;
    for (i = 0; i < n; i++) {
      positive[i] = Math.max(0, dense.values[i]);
      negative[i] = dense.secondaryValues ? Math.max(0, dense.secondaryValues[i]) : Math.max(0, -dense.values[i]);
      support[i] = Math.abs(dense.values[i]);
      weighted[i] = support[i] * (difference ? dense.opacity[i] : 1);
    }
    if (smooth) {
      var compact = !difference && appearance === 'clear';
      var kernel = gaussianKernel1d(compact ? 0.65 : 1.25, compact ? 2 : 4);
      positive = gaussianSmooth(positive, width, height, kernel, mask);
      negative = gaussianSmooth(negative, width, height, kernel, mask);
      weighted = gaussianSmooth(weighted, width, height, kernel, mask);
      support = gaussianSmooth(support, width, height, kernel, mask);
    }
    var values = new Float32Array(n * 2), opacity = new Float32Array(n), max = 0;
    for (i = 0; i < n; i++) {
      values[i * 2] = positive[i]; values[i * 2 + 1] = negative[i];
      opacity[i] = difference ? (support[i] > 0 ? weighted[i] / support[i] : 0) : 1;
      max = Math.max(max, positive[i], negative[i]);
    }
    return {values: values, opacity: opacity, maxAbs: max};
  }

  function HeatmapPointGeometry(payload) {
    if (!exactKeys(payload, ['schemaVersion', 'operation', 'version', 'kind', 'state', 'query', 'map', 'fields', 'points', 'summary'])
      || payload.schemaVersion !== 2 || payload.operation !== 'geometry' || payload.version !== 1 || payload.kind !== 'points'
      || (payload.state !== 'ok' && payload.state !== 'empty')) throw new TypeError('invalid_geometry');
    validateQuery(payload.query); validateMap(payload.map, payload.query);
    var difference = payload.query.lens === 'difference';
    if (!exactStringArray(payload.fields, difference ? ['x', 'y', 'personal', 'others'] : ['x', 'y', 'kills', 'deaths'])
      || !compactArray(payload.points) || payload.points.length > 20000
      || !exactKeys(payload.summary, ['positions', 'sourceRows', 'personalSample', 'otherSample'])
      || payload.summary.positions !== payload.points.length) throw new TypeError('invalid_geometry');
    Object.keys(payload.summary).forEach(function (key) { if (!nonNegativeInteger(payload.summary[key])) throw new TypeError('invalid_geometry'); });
    var previous = null, personal = 0, others = 0;
    payload.points.forEach(function (row) {
      if (!compactArray(row) || row.length !== 4 || !row.every(nonNegativeInteger)
        || row[0] >= payload.map.image.width || row[1] >= payload.map.image.height || row[2] + row[3] === 0
        || (previous && (row[1] < previous[1] || (row[1] === previous[1] && row[0] <= previous[0])))) throw new TypeError('invalid_geometry');
      previous = row; personal += row[2]; others += row[3];
    });
    if ((payload.state === 'empty' && payload.points.length !== 0)
      || (difference && (personal !== payload.summary.personalSample || others !== payload.summary.otherSample))) throw new TypeError('invalid_geometry');
    this.payload = JSON.parse(JSON.stringify(payload));
  }

  HeatmapPointGeometry.prototype.matchesScene = function (scene) {
    return JSON.stringify(this.payload.query) === JSON.stringify(scene.query)
      && JSON.stringify(this.payload.map) === JSON.stringify(scene.map)
      && this.payload.summary.sourceRows === scene.summary.sourceRows
      && (this.payload.query.lens !== 'difference' || (this.payload.summary.personalSample === scene.summary.personalSample && this.payload.summary.otherSample === scene.summary.otherSample));
  };

  HeatmapPointGeometry.prototype.vertexData = function (scene) {
    var payload = this.payload, vertices = new Float32Array(payload.points.length * 4), max = 0;
    var cellOpacity = scene && payload.query.lens === 'difference' ? scene.dense('difference', payload.query.event).opacity : null;
    payload.points.forEach(function (point, index) {
      var value = payload.query.lens === 'difference'
        ? point[2] / Math.max(1, payload.summary.personalSample) - point[3] / Math.max(1, payload.summary.otherSample)
        : (payload.query.event === 'kills' ? point[2] : (payload.query.event === 'deaths' ? point[3] : point[2] + point[3]));
      vertices[index * 4] = (point[0] + 0.5) / payload.map.image.width;
      vertices[index * 4 + 1] = (point[1] + 0.5) / payload.map.image.height;
      vertices[index * 4 + 2] = value;
      var cellIndex = scene ? Math.floor(point[1] / scene.grid.bucketSize) * scene.grid.width + Math.floor(point[0] / scene.grid.bucketSize) : 0;
      vertices[index * 4 + 3] = cellOpacity ? cellOpacity[cellIndex] : (payload.query.lens === 'difference' && point[2] < 3 ? 0.22 : 1);
      if (payload.query.event === 'both') {
        // One vertex per exact XY: coincident kills/deaths mix instead of overwriting.
        vertices[index * 4 + 2] = point[2]; vertices[index * 4 + 3] = point[3];
        value = Math.max(point[2],point[3]);
      }
      max = Math.max(max, Math.abs(value));
    });
    return {values: vertices, maxAbs: max};
  };

  function HeatmapGlRenderer(rootElement, scene, options) {
    this.root = rootElement;
    this.scene = scene;
    this.options = isRecord(options) ? options : {};
    this._nodes = null;
    this._listeners = [];
    this._gl = null;
    this._program = null;
    this._buffer = null;
    this._texture = null;
    this._opacityTexture = null;
    this._uniforms = null;
    this._camera = null;
    this._selection = null;
    this._mounted = false;
    this._destroyed = false;
    this._fallback = false;
    this._contextLost = false;
    this._contextUi = null;
    this._ready = false;
    this._startedAt = 0;
    this._pointer = null;
    this._suppressClick = false;
    this._displayMode = 'smooth';
    this._appearance = this.options.appearance === 'soft' ? 'soft' : 'clear';
    this._fields = {};
    this._surfaceGraph = scene.surfaceGraph || null;
    this._uploadedField = null;
    this._pointGeometry = null;
    this._pointResources = null;
    this._resizeObserver = null;
  }

  HeatmapGlRenderer.prototype._now = function () {
    var clock = typeof this.options.now === 'function' ? this.options.now : Date.now;
    var value;
    try {
      value = clock();
    } catch (error) {
      value = 0;
    }
    return finiteNumber(value) ? value : 0;
  };

  HeatmapGlRenderer.prototype._pointerPanEnabled = function () {
    if (typeof this.options.pointerPan === 'function') {
      try {
        return this.options.pointerPan() === true;
      } catch (error) {
        return false;
      }
    }
    return this.options.pointerPan !== false;
  };

  HeatmapGlRenderer.prototype._clearPointer = function () {
    if (!this._pointer) {
      return;
    }
    var canvas = this._nodes && this._nodes.canvas;
    var pointerId = this._pointer.id;
    if (this._pointer.dragged) {
      this._suppressClick = true;
    }
    this._pointer = null;
    if (canvas && typeof canvas.releasePointerCapture === 'function' && finiteNumber(pointerId)) {
      try {
        canvas.releasePointerCapture(pointerId);
      } catch (error) {
        // Pointer capture release is best effort only.
      }
    }
  };

  HeatmapGlRenderer.prototype.consumeSuppressedClick = function () {
    var suppressed = this._suppressClick;
    this._suppressClick = false;
    return suppressed;
  };

  HeatmapGlRenderer.prototype._node = function (selector) {
    return this.root && typeof this.root.querySelector === 'function'
      ? this.root.querySelector(selector)
      : null;
  };

  HeatmapGlRenderer.prototype._listen = function (target, type, handler) {
    if (target && typeof target.addEventListener === 'function') {
      target.addEventListener(type, handler);
      this._listeners.push({target: target, type: type, handler: handler});
    }
  };

  HeatmapGlRenderer.prototype._removeListeners = function () {
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
    for (var index = 0; index < this._listeners.length; index += 1) {
      var item = this._listeners[index];
      if (item.target && typeof item.target.removeEventListener === 'function') {
        item.target.removeEventListener(item.type, item.handler);
      }
    }
    this._listeners = [];
  };

  HeatmapGlRenderer.prototype._setState = function (code) {
    if (this.root && typeof this.root.setAttribute === 'function') {
      this.root.setAttribute('data-heatmap-state', code);
    }
    if (this._nodes && this._nodes.status && typeof this.options.message === 'function') {
      var message = '';
      try {
        message = this.options.message(code);
      } catch (error) {
        message = '';
      }
      if (typeof message === 'string') {
        this._nodes.status.textContent = message;
      }
    }
    if (typeof this.options.onState === 'function') {
      try {
        this.options.onState(code);
      } catch (error) {
        return;
      }
    }
  };

  HeatmapGlRenderer.prototype._rememberContextUi = function () {
    if (this._contextUi) {
      return;
    }
    var state = null;
    if (this.root && typeof this.root.getAttribute === 'function') {
      var currentState = this.root.getAttribute('data-heatmap-state');
      state = typeof currentState === 'string' ? currentState : null;
    }
    var status = this._nodes && this._nodes.status && typeof this._nodes.status.textContent === 'string'
      ? this._nodes.status.textContent
      : '';
    this._contextUi = {state: state, status: status};
  };

  HeatmapGlRenderer.prototype._restoreContextUi = function () {
    var previous = this._contextUi;
    this._contextUi = null;
    if (!previous) {
      return;
    }
    if (this.root) {
      if (previous.state === null && typeof this.root.removeAttribute === 'function') {
        this.root.removeAttribute('data-heatmap-state');
      } else if (previous.state !== null && typeof this.root.setAttribute === 'function') {
        this.root.setAttribute('data-heatmap-state', previous.state);
      }
    }
    if (this._nodes && this._nodes.status) {
      this._nodes.status.textContent = previous.status;
    }
  };

  HeatmapGlRenderer.prototype._showStatic = function () {
    if (!this._nodes) {
      return;
    }
    if (this._nodes.interactive && this._nodes.interactive.style) {
      this._nodes.interactive.style.display = 'none';
    }
    if (this._nodes.static && this._nodes.static.style) {
      this._nodes.static.style.display = '';
    }
  };

  HeatmapGlRenderer.prototype._showInteractive = function () {
    if (!this._nodes) {
      return;
    }
    if (this._nodes.interactive && this._nodes.interactive.style) {
      this._nodes.interactive.style.display = '';
    }
    if (this._nodes.static && this._nodes.static.style) {
      this._nodes.static.style.display = 'none';
    }
  };

  HeatmapGlRenderer.prototype._releaseResources = function () {
    var gl = this._gl;
    if (!gl) {
      return;
    }
    try {
      if (this._pointResources) {
        gl.deleteBuffer(this._pointResources.buffer);
        gl.deleteProgram(this._pointResources.program);
        this._pointResources = null;
      }
      if (this._opacityTexture && typeof gl.deleteTexture === 'function') {
        gl.deleteTexture(this._opacityTexture);
      }
      if (this._texture && typeof gl.deleteTexture === 'function') {
        gl.deleteTexture(this._texture);
      }
      if (this._buffer && typeof gl.deleteBuffer === 'function') {
        gl.deleteBuffer(this._buffer);
      }
      if (this._program && typeof gl.deleteProgram === 'function') {
        gl.deleteProgram(this._program);
      }
    } catch (error) {
      // Cleanup is best effort and never changes a safe fallback decision.
    }
    this._opacityTexture = null;
    this._texture = null;
    this._buffer = null;
    this._program = null;
    this._uniforms = null;
    this._uploadedField = null;
  };

  HeatmapGlRenderer.prototype._fallbackToStatic = function () {
    this._fallback = true;
    this._mounted = false;
    this._contextLost = false;
    this._contextUi = null;
    this._releaseResources();
    this._gl = null;
    this._removeListeners();
    this._showStatic();
    this._setState('static_fallback');
  };

  HeatmapGlRenderer.prototype._createShader = function (gl, type, source) {
    var shader = gl.createShader(type);
    if (!shader) {
      throw new Error('shader_unavailable');
    }
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      if (typeof gl.deleteShader === 'function') {
        gl.deleteShader(shader);
      }
      throw new Error('shader_unavailable');
    }
    return shader;
  };

  HeatmapGlRenderer.prototype._createResources = function () {
    var gl = this._gl;
    if (!gl || typeof gl.createTexture !== 'function' || typeof gl.createBuffer !== 'function'
      || typeof gl.createProgram !== 'function') {
      throw new Error('webgl_unavailable');
    }

    var vertexSource = '#version 300 es\n'
      + 'in vec2 a_position;\n'
      + 'out vec2 v_uv;\n'
      + 'void main() {\n'
      + '  v_uv = a_position * 0.5 + 0.5;\n'
      + '  gl_Position = vec4(a_position, 0.0, 1.0);\n'
      + '}\n';
    var fragmentSource = '#version 300 es\n'
      + 'precision highp float;\n'
      + 'uniform sampler2D u_density;\n'
      + 'uniform sampler2D u_opacity;\n'
      + 'uniform vec2 u_gridSize;\n'
      + 'uniform vec2 u_gridExtent;\n'
      + 'uniform float u_maxAbs;\n'
      + 'uniform float u_displayMax;\n'
      + 'uniform int u_palette;\n'
      + 'uniform int u_contours;\n'
      + 'uniform int u_smooth;\n'
      + 'uniform int u_constrained;\n'
      + 'in vec2 v_uv;\n'
      + 'out vec4 outputColor;\n'
      + 'vec3 amberOrange(float amount) { return vec3(1.0, 0.45*(1.0-amount), 35.0/255.0); }\n'
      + 'vec3 cyanBlue(float amount) { return mix(vec3(0.02, 0.45, 1.0), vec3(0.15, 1.0, 1.0), amount); }\n'
      + 'vec3 bothHue(vec2 density, float amount) { float ratio=density.r/max(density.r+density.g,0.000001); return mix(mix(cyanBlue(amount),amberOrange(amount),ratio),vec3(1.0),0.45*4.0*ratio*(1.0-ratio)); }\n'
      + 'vec3 differenceBlueNeutralAmber(float value) {\n'
      + '  vec3 blue = vec3(0.10, 0.36, 0.95);\n'
      + '  vec3 neutral = vec3(0.94, 0.94, 0.94);\n'
      + '  vec3 amber = vec3(1.0, 0.56, 0.05);\n'
      + '  return value < 0.0 ? mix(neutral, blue, -value) : mix(neutral, amber, value);\n'
      + '}\n'
      + 'vec4 field(sampler2D source, vec2 uv) {\n'
      + '  vec2 p = clamp(uv * u_gridSize - 0.5, vec2(0.0), u_gridSize - 1.0);\n'
      + '  ivec2 a = ivec2(floor(p)); ivec2 b = min(a + 1, ivec2(u_gridSize) - 1);\n'
      + '  if (u_smooth == 0 || u_constrained == 1) return texture(source, uv);\n'
      + '  vec2 f = fract(p);\n'
      + '  return mix(mix(texelFetch(source,a,0),texelFetch(source,ivec2(b.x,a.y),0),f.x),mix(texelFetch(source,ivec2(a.x,b.y),0),texelFetch(source,b,0),f.x),f.y);\n'
      + '}\n'
      + 'void main() {\n'
      + '  vec2 sampleUv = vec2(v_uv.x, 1.0 - v_uv.y);\n'
      + '  sampleUv *= u_gridExtent;\n'
      + '  vec2 density = field(u_density, sampleUv).rg;\n'
      + '  float center = density.r - density.g;\n'
      + '  float value = max(density.r, density.g);\n'
      + '  float displayMax = max(u_displayMax, 0.000001);\n'
      + '  float amount = sqrt(clamp(value / displayMax, 0.0, 1.0));\n'
      + '  if (u_palette == 0 || u_palette == 3) amount = pow(clamp(value / displayMax, 0.0, 1.0), 0.45);\n'
      + '  float confidence = u_palette == 2 ? clamp(field(u_opacity, sampleUv).r, 0.0, 1.0) : 1.0;\n'
      + '  float differenceHue = center / max(density.r + density.g, 0.000001);\n'
      + '  float alpha = amount * confidence;\n'
      + '  if (u_palette == 0 || u_palette == 3) alpha *= 210.0/255.0;\n'
      + '  if (u_palette != 2) {\n'
      + '    if (value <= 0.003) discard;\n'
      + '    alpha = max(alpha, 0.42 * smoothstep(0.003, 0.012, value));\n'
      + '  }\n'
      + '  if (u_palette == 2 && u_smooth == 1) alpha = max(alpha, 0.26 * smoothstep(0.0, 0.20, amount));\n'
      + '  if (u_palette == 2 && u_smooth == 0 && center != 0.0) alpha = max(alpha, 0.22);\n'
      + '  vec3 color = u_palette == 2 ? differenceBlueNeutralAmber(differenceHue)\n'
      + '    : (u_palette == 3 ? bothHue(density, amount) : (u_palette == 1 ? cyanBlue(amount) : amberOrange(amount)));\n'
      + '  float contour = 0.0;\n'
      + '  if (u_contours == 1) {\n'
      + '    contour = step(0.245, amount) * 0.10 + step(0.495, amount) * 0.10 + step(0.745, amount) * 0.10;\n'
      + '  }\n'
      + '  outputColor = vec4(mix(color, vec3(1.0), contour), alpha);\n'
      + '}\n';

    var vertex = null;
    var fragment = null;
    var program = null;
    var buffer = null;
    var texture = null;
    var opacityTexture = null;
    function release(method, handle) {
      if (handle && typeof gl[method] === 'function') {
        try {
          gl[method](handle);
        } catch (error) {
          // Cleanup is best effort and the original initialization error wins.
        }
      }
    }
    function configureTexture(handle) {
      gl.bindTexture(gl.TEXTURE_2D, handle);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    }
    try {
      vertex = this._createShader(gl, gl.VERTEX_SHADER, vertexSource);
      fragment = this._createShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
      program = gl.createProgram();
      if (!program) {
        throw new Error('program_unavailable');
      }
      gl.attachShader(program, vertex);
      gl.attachShader(program, fragment);
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error('program_unavailable');
      }
      release('deleteShader', vertex);
      vertex = null;
      release('deleteShader', fragment);
      fragment = null;

      buffer = gl.createBuffer();
      if (!buffer) {
        throw new Error('resource_unavailable');
      }
      texture = gl.createTexture();
      if (!texture) {
        throw new Error('resource_unavailable');
      }
      opacityTexture = gl.createTexture();
      if (!opacityTexture) {
        throw new Error('resource_unavailable');
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      configureTexture(texture);
      configureTexture(opacityTexture);

      var uniforms = {
        gridSize: gl.getUniformLocation(program, 'u_gridSize'),
        gridExtent: gl.getUniformLocation(program, 'u_gridExtent'),
        maxAbs: gl.getUniformLocation(program, 'u_maxAbs'),
        displayMax: gl.getUniformLocation(program, 'u_displayMax'),
        palette: gl.getUniformLocation(program, 'u_palette'),
        contours: gl.getUniformLocation(program, 'u_contours'),
        smooth: gl.getUniformLocation(program, 'u_smooth'),
        constrained: gl.getUniformLocation(program, 'u_constrained'),
        density: gl.getUniformLocation(program, 'u_density'),
        opacity: gl.getUniformLocation(program, 'u_opacity')
      };
      var position = gl.getAttribLocation(program, 'a_position');
      if (position < 0) {
        throw new Error('attribute_unavailable');
      }

      this._program = program;
      program = null;
      this._buffer = buffer;
      buffer = null;
      this._texture = texture;
      texture = null;
      this._opacityTexture = opacityTexture;
      opacityTexture = null;
      this._uniforms = uniforms;
      this._position = position;
    } catch (error) {
      release('deleteTexture', opacityTexture);
      release('deleteTexture', texture);
      release('deleteBuffer', buffer);
      release('deleteProgram', program);
      release('deleteShader', fragment);
      release('deleteShader', vertex);
      throw error;
    }
  };

  HeatmapGlRenderer.prototype._selectionForScene = function () {
    return {
      layer: this.scene.query.lens === 'overview' ? 'total' : this.scene.query.lens,
      channel: this.scene.query.event
    };
  };

  HeatmapGlRenderer.prototype._normalSelection = function (selection) {
    var next = isRecord(selection) ? selection : (this._selection || this._selectionForScene());
    var layer = next.layer === 'overview' ? 'total' : next.layer;
    var channel = next.channel;
    if (layer !== 'total' && layer !== 'me' && layer !== 'others' && layer !== 'difference') {
      throw new Error('invalid_dense_selection');
    }
    if (channel !== 'kills' && channel !== 'deaths' && !(layer !== 'difference' && channel === 'both')) {
      throw new Error('invalid_dense_selection');
    }
    return {layer: layer, channel: channel};
  };

  HeatmapGlRenderer.prototype._readyAfterFrame = function (dense) {
    if (this._ready || dense.occupied.length === 0) {
      return;
    }
    var duration = this._now() - this._startedAt;
    if (!finiteNumber(duration) || duration < 0) {
      duration = 0;
    }
    this._ready = true;
    if (this.root && typeof this.root.setAttribute === 'function') {
      this.root.setAttribute('data-heatmap-render-ms', String(duration));
    }
    if (this.root && typeof this.root.dispatchEvent === 'function') {
      var view = this.options.window || (typeof window !== 'undefined' ? window : null);
      var event;
      if (view && typeof view.CustomEvent === 'function') {
        event = new view.CustomEvent('heatmap-explorer-ready', {detail: {durationMs: duration, renderMs: duration}});
      } else {
        event = {type: 'heatmap-explorer-ready', detail: {durationMs: duration, renderMs: duration}};
      }
      this.root.dispatchEvent(event);
    }
  };

  HeatmapGlRenderer.prototype.render = function (selection) {
    if (!this._mounted || this._destroyed || this._fallback || this._contextLost || !this._gl) {
      return false;
    }
    try {
      var next = this._normalSelection(selection);
      if (this._displayMode === 'points' && this._pointGeometry) {
        try { return this._renderPoints(next); } catch (pointError) {
          this._displayMode = 'cells';
          this.render(next);
          this._setState('pointsUnavailable');
          return false;
        }
      }
      var dense = this.scene.dense(next.layer, next.channel);
      var key = this._displayMode + ':' + next.layer + ':' + next.channel + ':' + (next.layer === 'difference' ? 'difference' : this._appearance);
      var field = this._fields[key];
      if (!field) {
        var fieldDense = next.channel === 'both' ? {values:this.scene.dense(next.layer,'kills').values,secondaryValues:this.scene.dense(next.layer,'deaths').values} : dense;
        try {
          if (typeof this._regionMask === 'undefined') this._regionMask = regionGridMask(this.scene);
          field = this._displayMode === 'smooth' && this._surfaceGraph
            ? this._surfaceGraph.field(this.scene, next.layer, next.channel, this._appearance)
            : presentationField(fieldDense, this.scene.grid.width, this.scene.grid.height, this._displayMode === 'smooth', next.layer === 'difference', this._regionMask, this._appearance);
        } catch (error) {
          this._displayMode = 'cells';
          field = presentationField(fieldDense || dense, this.scene.grid.width, this.scene.grid.height, false, next.layer === 'difference');
          this._setState('cells_fallback');
        }
        this._fields[key] = field;
      }
      var upload = field.values;
      var fieldWidth = field.width || this.scene.grid.width, fieldHeight = field.height || this.scene.grid.height;
      var opacityUpload = field.opacity;
      var displayMax = this.options.scaleMaximum ? this.options.scaleMaximum(field.maxAbs, this._displayMode) : field.maxAbs;
      var gl = this._gl;
      gl.useProgram(this._program);
      gl.bindBuffer(gl.ARRAY_BUFFER, this._buffer);
      gl.enableVertexAttribArray(this._position);
      gl.vertexAttribPointer(this._position, 2, gl.FLOAT, false, 0, 0);
      if (typeof gl.activeTexture === 'function' && typeof gl.TEXTURE0 === 'number') {
        gl.activeTexture(gl.TEXTURE0);
      }
      gl.bindTexture(gl.TEXTURE_2D, this._texture);
      if (this._uploadedField !== field) gl.texImage2D(
        gl.TEXTURE_2D, 0, gl.RG32F, fieldWidth, fieldHeight,
        0, gl.RG, gl.FLOAT, upload
      );
      if (typeof gl.activeTexture === 'function' && typeof gl.TEXTURE1 === 'number') {
        gl.activeTexture(gl.TEXTURE1);
      }
      gl.bindTexture(gl.TEXTURE_2D, this._opacityTexture);
      if (this._uploadedField !== field) gl.texImage2D(
        gl.TEXTURE_2D, 0, gl.R32F, fieldWidth, fieldHeight,
        0, gl.RED, gl.FLOAT, opacityUpload
      );
      this._uploadedField = field;
      gl.uniform1i(this._uniforms.smooth, this._displayMode === 'smooth' ? 1 : 0);
      gl.uniform1i(this._uniforms.constrained, field.constrained ? 1 : 0);
      if (typeof gl.activeTexture === 'function' && typeof gl.TEXTURE0 === 'number') {
        gl.activeTexture(gl.TEXTURE0);
      }
      if (this._uniforms.gridSize !== null) {
        gl.uniform2f(this._uniforms.gridSize, fieldWidth, fieldHeight);
      }
      gl.uniform2f(this._uniforms.gridExtent,
        field.constrained ? 1 : this.scene.map.image.width / (this.scene.grid.width * this.scene.grid.bucketSize),
        field.constrained ? 1 : this.scene.map.image.height / (this.scene.grid.height * this.scene.grid.bucketSize));
      if (this._uniforms.maxAbs !== null) {
        gl.uniform1f(this._uniforms.maxAbs, dense.maxAbs);
      }
      if (this._uniforms.displayMax !== null) {
        gl.uniform1f(this._uniforms.displayMax, displayMax);
      }
      if (this._uniforms.palette !== null) {
        gl.uniform1i(this._uniforms.palette, next.layer === 'difference' ? 2 : (next.channel === 'both' ? 3 : (next.channel === 'deaths' ? 1 : 0)));
      }
      if (this._uniforms.contours !== null) {
        gl.uniform1i(this._uniforms.contours, this.options.contours ? 1 : 0);
      }
      if (this._uniforms.density !== null) {
        gl.uniform1i(this._uniforms.density, 0);
      }
      if (this._uniforms.opacity !== null) {
        gl.uniform1i(this._uniforms.opacity, 1);
      }
      if (typeof gl.clearColor === 'function') {
        gl.clearColor(0, 0, 0, 0);
      }
      if (typeof gl.clear === 'function') {
        gl.clear(gl.COLOR_BUFFER_BIT);
      }
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      if (typeof gl.getError === 'function') {
        var errorCode = gl.getError();
        if (typeof errorCode === 'number' && errorCode !== 0) {
          throw new Error('draw_unavailable');
        }
      }
      this._selection = next;
      this._readyAfterFrame(dense);
      return true;
    } catch (error) {
      this._fallbackToStatic();
      return false;
    }
  };

  HeatmapGlRenderer.prototype.setDisplayMode = function (mode, geometry) {
    if (mode !== 'smooth' && mode !== 'cells' && mode !== 'points') return false;
    if (mode === 'points' && !(geometry instanceof HeatmapPointGeometry)) return false;
    this._displayMode = mode;
    if (geometry) this._pointGeometry = geometry;
    return this.render();
  };

  HeatmapGlRenderer.prototype.setAppearance = function (appearance) {
    if (appearance !== 'clear' && appearance !== 'soft') return false;
    this._appearance = appearance;
    return this.render();
  };

  HeatmapGlRenderer.prototype._renderPoints = function (selection) {
    var gl = this._gl;
    if (!this._pointResources) {
      var vertex = null, fragment = null, program = null, buffer = null;
      try {
        vertex = this._createShader(gl, gl.VERTEX_SHADER, '#version 300 es\n'
          + 'in vec4 a_point; uniform float u_size; out float v_value; out float v_confidence;\n'
          + 'void main(){ gl_Position=vec4(a_point.x*2.0-1.0,1.0-a_point.y*2.0,0.0,1.0); gl_PointSize=u_size; v_value=a_point.z; v_confidence=a_point.w; }');
        fragment = this._createShader(gl, gl.FRAGMENT_SHADER, '#version 300 es\nprecision highp float;\n'
          + 'in float v_value; in float v_confidence; uniform float u_max; uniform int u_palette; out vec4 color;\n'
          + 'void main(){float d=length(gl_PointCoord-0.5)*2.0;float strength=u_palette==3?max(v_value,v_confidence):abs(v_value);if(d>1.0 || strength==0.0) discard;'
          + 'float amount=sqrt(clamp(strength/max(u_max,0.000001),0.0,1.0));'
          + 'vec3 warm=vec3(1.0,0.62,0.08);vec3 cool=vec3(0.1,0.85,1.0);'
          + 'vec3 hue=u_palette==2?(v_value<0.0?cool:warm):(u_palette==1?cool:warm);'
          + 'float confidence=u_palette==3?1.0:v_confidence;'
          + 'if(u_palette==0 || u_palette==3){amount=pow(clamp(strength/max(u_max,0.000001),0.0,1.0),0.45);warm=vec3(1.0,0.45*(1.0-amount),35.0/255.0);hue=warm;}'
          + 'if(u_palette==3){float ratio=v_value/max(v_value+v_confidence,0.000001);hue=mix(mix(cool,warm,ratio),vec3(1.0),0.45*4.0*ratio*(1.0-ratio));}'
          + 'color=vec4(mix(hue,vec3(1.0),u_palette==2?amount*0.22:0.0),max(u_palette==2?0.35:0.42,amount*confidence)*(1.0-smoothstep(0.75,1.0,d)));}');
        program = gl.createProgram(); if (!program) throw new Error('points_unavailable');
        gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('points_unavailable');
        buffer = gl.createBuffer(); if (!buffer) throw new Error('points_unavailable');
        this._pointResources = {program: program, buffer: buffer, geometry: null,
          position: gl.getAttribLocation(program, 'a_point'), size: gl.getUniformLocation(program, 'u_size'),
          max: gl.getUniformLocation(program, 'u_max'), palette: gl.getUniformLocation(program, 'u_palette')};
      } catch (error) {
        if (buffer) gl.deleteBuffer(buffer); if (program) gl.deleteProgram(program); throw error;
      } finally {
        if (vertex) gl.deleteShader(vertex); if (fragment) gl.deleteShader(fragment);
      }
    }
    var resource = this._pointResources;
    gl.useProgram(resource.program); gl.bindBuffer(gl.ARRAY_BUFFER, resource.buffer);
    if (resource.geometry !== this._pointGeometry) {
      resource.data = this._pointGeometry.vertexData(this.scene); resource.geometry = this._pointGeometry;
      gl.bufferData(gl.ARRAY_BUFFER, resource.data.values, gl.STATIC_DRAW);
    }
    gl.enableVertexAttribArray(resource.position); gl.vertexAttribPointer(resource.position, 4, gl.FLOAT, false, 0, 0);
    var cssWidth = parseFloat(this._nodes.canvas.style.width) || this._nodes.canvas.width;
    gl.uniform1f(resource.size, 5 * this._nodes.canvas.width / cssWidth);
    gl.uniform1f(resource.max, this.options.scaleMaximum ? this.options.scaleMaximum(resource.data.maxAbs, 'points') : resource.data.maxAbs);
    gl.uniform1i(resource.palette, selection.layer === 'difference' ? 2 : (selection.channel === 'both' ? 3 : (selection.channel === 'deaths' ? 1 : 0)));
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.POINTS, 0, resource.data.values.length / 4);
    if (gl.getError() !== 0) throw new Error('points_unavailable');
    this._selection = selection;
    return true;
  };

  HeatmapGlRenderer.prototype.resize = function () {
    if (!this._mounted || this._destroyed || this._fallback || this._contextLost || !this._nodes || !this._gl) {
      return false;
    }
    try {
      var stage = this._nodes.stage;
      var width = Math.max(1, Math.round(numeric(stage.clientWidth, numeric(this._nodes.canvas.clientWidth, 1))));
      var height = Math.max(1, Math.round(numeric(stage.clientHeight, numeric(this._nodes.canvas.clientHeight, 1))));
      this._layoutWidth = width;
      this._layoutHeight = height;
      var image = this.scene && this.scene.map && this.scene.map.image ? this.scene.map.image : null;
      var contentWidth = Math.max(1, workspaceInteger(image && image.width, width));
      var contentHeight = Math.max(1, workspaceInteger(image && image.height, height));
      if (this._camera && typeof this._camera.setViewport === 'function') {
        this._camera.setViewport(width, height, contentWidth, contentHeight);
        this.setCamera(this._camera);
      }
      var view = this.options.window || (typeof window !== 'undefined' ? window : null);
      var ratio = view && finiteNumber(view.devicePixelRatio) ? view.devicePixelRatio : 1;
      ratio = Math.max(1, Math.min(2, ratio));
      this._nodes.canvas.width = Math.round(width * ratio);
      this._nodes.canvas.height = Math.round(height * ratio);
      if (this._nodes.canvas.style) {
        this._nodes.canvas.style.width = width + 'px';
        this._nodes.canvas.style.height = height + 'px';
      }
      this._gl.viewport(0, 0, this._nodes.canvas.width, this._nodes.canvas.height);
      return this.render();
    } catch (error) {
      this._fallbackToStatic();
      return false;
    }
  };

  HeatmapGlRenderer.prototype.setCamera = function (camera) {
    this._camera = camera || null;
    if (!this._nodes || !this._nodes.camera || !this._nodes.camera.style || !camera
      || typeof camera.transform !== 'function') {
      return;
    }
    var transform = camera.transform();
    if (!transform || typeof transform.css !== 'string') {
      return;
    }
    this._nodes.camera.style.transformOrigin = '0 0';
    this._nodes.camera.style.transform = transform.css;
    this._nodes.camera.style.transition = transform.animate ? 'transform 160ms ease-out' : 'none';
  };

  HeatmapGlRenderer.prototype._bindEvents = function () {
    var self = this;
    var canvas = this._nodes.canvas;
    var target = this._nodes.stage || canvas;
    this._listen(canvas, 'webglcontextlost', function (event) {
      if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
      }
      if (self._destroyed || !self._mounted) {
        return;
      }
      self._rememberContextUi();
      self._contextLost = true;
      self._releaseResources();
      self._showStatic();
      self._setState('context_lost');
    });
    this._listen(canvas, 'webglcontextrestored', function () {
      if (self._destroyed || !self._mounted) {
        return;
      }
      self._contextLost = false;
      try {
        self._createResources();
        self._showInteractive();
        if (self.resize()) {
          self._restoreContextUi();
        }
      } catch (error) {
        self._fallbackToStatic();
      }
    });
    this._listen(canvas, 'pointerdown', function (event) {
      if (!self._pointerPanEnabled()) {
        return;
      }
      if (!self._camera || !event) {
        return;
      }
      self._suppressClick = false;
      self._pointer = {
        id: finiteNumber(event.pointerId) ? event.pointerId : null,
        startX: numeric(event.clientX, 0),
        startY: numeric(event.clientY, 0),
        lastX: numeric(event.clientX, 0),
        lastY: numeric(event.clientY, 0),
        dragged: false
      };
      if (typeof canvas.setPointerCapture === 'function' && finiteNumber(event.pointerId)) {
        canvas.setPointerCapture(event.pointerId);
      }
    });
    this._listen(canvas, 'pointermove', function (event) {
      if (!self._pointerPanEnabled()) {
        return;
      }
      if (!self._pointer || !self._camera || !event || typeof self._camera.panBy !== 'function') {
        return;
      }
      if (self._pointer.id !== null && finiteNumber(event.pointerId) && event.pointerId !== self._pointer.id) {
        return;
      }
      var nextX = numeric(event.clientX, self._pointer.lastX);
      var nextY = numeric(event.clientY, self._pointer.lastY);
      if (!self._pointer.dragged) {
        var movedX = nextX - self._pointer.startX;
        var movedY = nextY - self._pointer.startY;
        if ((movedX * movedX) + (movedY * movedY) < 25) {
          return;
        }
        self._pointer.dragged = true;
      }
      if (typeof event.preventDefault === 'function') {
        event.preventDefault();
      }
      self._camera.panBy(nextX - self._pointer.lastX, nextY - self._pointer.lastY);
      self._pointer.lastX = nextX;
      self._pointer.lastY = nextY;
      self.setCamera(self._camera);
    });
    this._listen(canvas, 'pointerup', function () {
      self._clearPointer();
    });
    this._listen(canvas, 'pointercancel', function () {
      self._clearPointer();
    });
    this._listen(canvas, 'lostpointercapture', function () {
      self._clearPointer();
    });
    this._listen(target, 'keydown', function (event) {
      if (self.options.cameraKeys === false) {
        return;
      }
      if (!self._camera || !event || typeof self._camera.handleKey !== 'function') {
        return;
      }
      if (self._camera.handleKey(event.key)) {
        if (typeof event.preventDefault === 'function') {
          event.preventDefault();
        }
        self.setCamera(self._camera);
      }
    });
    var view = this.options.window || (typeof window !== 'undefined' ? window : null);
    this._listen(view, 'resize', function () {
      self.resize();
    });
    if (view && typeof view.ResizeObserver === 'function') {
      this._resizeObserver = new view.ResizeObserver(function () {
        var stage = self._nodes && self._nodes.stage;
        if (stage && (Math.round(stage.clientWidth) !== self._layoutWidth || Math.round(stage.clientHeight) !== self._layoutHeight)) self.resize();
      });
      this._resizeObserver.observe(this._nodes.stage);
    }
  };

  HeatmapGlRenderer.prototype.mount = function () {
    if (this._destroyed || this._mounted || this._fallback) {
      return this;
    }
    this._nodes = {
      interactive: this._node('[data-heatmap-interactive]'),
      stage: this._node('[data-heatmap-stage]'),
      camera: this._node('[data-heatmap-camera]'),
      image: this._node('[data-heatmap-image]'),
      canvas: this._node('[data-heatmap-canvas]'),
      static: this._node('[data-heatmap-static]'),
      status: this._node('[data-heatmap-status]')
    };
    if (!this.scene || typeof this.scene.dense !== 'function'
      || !this._nodes.interactive || !this._nodes.stage || !this._nodes.camera
      || !this._nodes.image || !this._nodes.canvas || !this._nodes.static || !this._nodes.status
      || typeof this._nodes.canvas.getContext !== 'function') {
      this._fallbackToStatic();
      return this;
    }
    this._startedAt = this._now();
    this._selection = this._selectionForScene();
    this._mounted = true;
    try {
      this._gl = this._nodes.canvas.getContext('webgl2', {alpha: true, antialias: false, premultipliedAlpha: false});
      if (!this._gl) {
        throw new Error('webgl_unavailable');
      }
      this._bindEvents();
      this._createResources();
      this._showInteractive();
      this.resize();
    } catch (error) {
      this._fallbackToStatic();
    }
    return this;
  };

  HeatmapGlRenderer.prototype.destroy = function () {
    if (this._destroyed) {
      return;
    }
    this._destroyed = true;
    this._mounted = false;
    this._contextLost = false;
    this._contextUi = null;
    this._pointer = null;
    this._suppressClick = false;
    this._removeListeners();
    this._releaseResources();
    this._gl = null;
  };

  function workspaceAttribute(rootElement, name, fallback) {
    if (!rootElement || typeof rootElement.getAttribute !== 'function') {
      return fallback;
    }
    var value = rootElement.getAttribute(name);
    return typeof value === 'string' && value !== '' ? value : fallback;
  }

  function workspaceInteger(value, fallback) {
    if (typeof value === 'number' && safeInteger(value)) {
      return value;
    }
    if (typeof value === 'string' && /^(?:0|[1-9][0-9]*)$/.test(value)) {
      var parsed = Number(value);
      return safeInteger(parsed) ? parsed : fallback;
    }
    return fallback;
  }

  function workspaceNode(rootElement, selector) {
    return rootElement && typeof rootElement.querySelector === 'function'
      ? rootElement.querySelector(selector)
      : null;
  }

  function workspaceNodes(rootElement, selector) {
    if (!rootElement || typeof rootElement.querySelectorAll !== 'function') {
      return [];
    }
    var selected = rootElement.querySelectorAll(selector);
    return selected && typeof selected.length === 'number' ? selected : [];
  }

  function workspaceSetText(node, value) {
    if (node) {
      node.textContent = typeof value === 'string' ? value : '';
    }
  }

  function workspaceSetAttribute(node, name, value) {
    if (node && typeof node.setAttribute === 'function') {
      node.setAttribute(name, String(value));
    }
  }

  function workspaceMessageAttribute(key) {
    return 'data-heatmap-message-' + String(key)
      .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
      .replace(/_/g, '-')
      .toLowerCase();
  }

  function workspaceUrlBase(endpoint) {
    if (typeof endpoint !== 'string' || endpoint === '') {
      return 'heatmap_points.php';
    }
    var question = endpoint.indexOf('?');
    return question >= 0 ? endpoint.slice(0, question) : endpoint;
  }

  function workspaceTextValue(value) {
    return typeof value === 'string' && value.length > 0 ? value : null;
  }

  function workspaceSceneImageSize(scene, imageNode) {
    var sceneImage = scene && scene.map && scene.map.image ? scene.map.image : null;
    var width = workspaceInteger(sceneImage && sceneImage.width, 0);
    var height = workspaceInteger(sceneImage && sceneImage.height, 0);
    if (!(width > 0)) {
      width = workspaceInteger(imageNode && own(imageNode, 'naturalWidth') ? imageNode.naturalWidth : null, 0);
    }
    if (!(height > 0)) {
      height = workspaceInteger(imageNode && own(imageNode, 'naturalHeight') ? imageNode.naturalHeight : null, 0);
    }
    if (!(width > 0)) {
      width = workspaceInteger(imageNode && typeof imageNode.getAttribute === 'function' ? imageNode.getAttribute('width') : null, 1);
    }
    if (!(height > 0)) {
      height = workspaceInteger(imageNode && typeof imageNode.getAttribute === 'function' ? imageNode.getAttribute('height') : null, 1);
    }
    return {
      width: width > 0 ? width : 1,
      height: height > 0 ? height : 1
    };
  }

  function legacyEventValue(value) {
    return value === 'kills' || value === 'deaths' || value === 'both' ? value : '';
  }

  function legacyMapValue(value) {
    return typeof value === 'string' && TOKEN.test(value) ? value : '';
  }

  function legacyHumanRoute(path, values, state) {
    if (path !== 'hlstats.php' || values.heatmapLegacy !== true) {
      return null;
    }
    if (values.mode === 'mapinfo') {
      var game = legacyMapValue(values.game);
      var map = legacyMapValue(state && state.map) || legacyMapValue(values.map);
      if (game === '' || map === '') {
        return '';
      }
      return path + '?mode=mapinfo&game=' + encodeURIComponent(game)
        + '&map=' + encodeURIComponent(map) + '&heatmap_legacy=1';
    }
    if (values.mode === 'playerinfo' && /^(?:[1-9][0-9]*)$/.test(values.player || '')) {
      return path + '?mode=playerinfo&player=' + encodeURIComponent(values.player)
        + '&heatmap_legacy=1';
    }
    return '';
  }

  function rewriteLegacyFallbackUrl(baseUrl, state) {
    if (typeof baseUrl !== 'string' || baseUrl === '' || /^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(baseUrl)
      || baseUrl.slice(0, 2) === '//') {
      return '';
    }
    var hashIndex = baseUrl.indexOf('#');
    var trimmed = hashIndex >= 0 ? baseUrl.slice(0, hashIndex) : baseUrl;
    var question = trimmed.indexOf('?');
    var path = question >= 0 ? trimmed.slice(0, question) : trimmed;
    if (path === '') {
      return '';
    }
    var values = {};
    if (question >= 0 && question + 1 < trimmed.length) {
      var parts = trimmed.slice(question + 1).split('&');
      for (var index = 0; index < parts.length; index += 1) {
        var raw = parts[index];
        if (raw === '') {
          continue;
        }
        var separator = raw.indexOf('=');
        var key = decodeQueryPart(separator === -1 ? raw : raw.slice(0, separator));
        var value = decodeQueryPart(separator === -1 ? '' : raw.slice(separator + 1));
        if (key === 'game' || key === 'map') {
          if (!own(values, key) && value !== '') {
            values[key] = value;
          }
        } else if (key === 'player') {
          if (!own(values, key) && /^(?:[1-9][0-9]*)$/.test(value)) {
            values[key] = value;
          }
        } else if (key === 'event') {
          var baseEvent = legacyEventValue(value);
          if (!own(values, key) && baseEvent !== '') {
            values[key] = baseEvent;
          }
        } else if (key === 'mode') {
          if (!own(values, key) && (value === 'mapinfo' || value === 'playerinfo')) {
            values[key] = value;
          }
        } else if (key === 'heatmap_legacy' && !own(values, 'heatmapLegacy') && value === '1') {
          values.heatmapLegacy = true;
        }
      }
    }
    var humanRoute = legacyHumanRoute(path, values, state);
    if (humanRoute !== null) {
      return humanRoute;
    }
    var currentMap = legacyMapValue(state && state.map);
    if (currentMap !== '') {
      values.map = currentMap;
    }
    var currentEvent = legacyEventValue(state && state.event);
    if (currentEvent !== '') {
      values.event = currentEvent;
    }
    var pairs = [];
    for (var keyIndex = 0; keyIndex < 4; keyIndex += 1) {
      var allowedKey = ['game', 'map', 'player', 'event'][keyIndex];
      if (own(values, allowedKey)) {
        pairs.push(encodeURIComponent(allowedKey) + '=' + encodeURIComponent(values[allowedKey]));
      }
    }
    return pairs.length ? path + '?' + pairs.join('&') : path;
  }

  function invalidInspect() {
    throw new Error('invalid_inspect');
  }

  function inspectText(value, maximum) {
    if (typeof value !== 'string' || value.length > maximum) {
      invalidInspect();
    }
    return value;
  }

  function inspectActor(value) {
    if (!isRecord(value) || !safeInteger(value.id) || value.id < 0) {
      invalidInspect();
    }
    return {id: value.id, name: inspectText(value.name, 256)};
  }

  function inspectRow(value) {
    if (!isRecord(value) || (value.event !== 'kill' && value.event !== 'death')
      || typeof value.headshot !== 'boolean' || typeof value.teamkill !== 'boolean') {
      invalidInspect();
    }
    return {
      eventTime: inspectText(value.eventTime, 64),
      event: value.event,
      killer: inspectActor(value.killer),
      victim: inspectActor(value.victim),
      weapon: inspectText(value.weapon, 64),
      headshot: value.headshot,
      teamkill: value.teamkill
    };
  }

  function inspectAggregates(value) {
    if (!isRecord(value) || !exactKeys(value, ['scope', 'sampleRows', 'topWeapons', 'participantCounts'])
      || value.scope !== 'returned_rows' || !nonNegativeInteger(value.sampleRows)
      || !compactArray(value.topWeapons) || value.topWeapons.length > 5
      || !isRecord(value.participantCounts)
      || !exactKeys(value.participantCounts, ['unique', 'killers', 'victims'])) {
      invalidInspect();
    }
    var participantKeys = ['unique', 'killers', 'victims'];
    var participantCounts = {};
    for (var participantIndex = 0; participantIndex < participantKeys.length; participantIndex += 1) {
      var participantKey = participantKeys[participantIndex];
      if (!nonNegativeInteger(value.participantCounts[participantKey])) {
        invalidInspect();
      }
      participantCounts[participantKey] = value.participantCounts[participantKey];
    }
    var topWeapons = [];
    for (var weaponIndex = 0; weaponIndex < value.topWeapons.length; weaponIndex += 1) {
      var weapon = value.topWeapons[weaponIndex];
      if (!isRecord(weapon) || !exactKeys(weapon, ['weapon', 'count'])
        || typeof weapon.weapon !== 'string' || weapon.weapon.length === 0 || weapon.weapon.length > 64
        || !nonNegativeInteger(weapon.count) || weapon.count === 0) {
        invalidInspect();
      }
      topWeapons.push({weapon: weapon.weapon, count: weapon.count});
    }
    return {
      scope: value.scope,
      sampleRows: value.sampleRows,
      topWeapons: topWeapons,
      participantCounts: participantCounts
    };
  }

  function HeatmapExplorerInspect(payload) {
    if (!isRecord(payload) || payload.schemaVersion !== 2 || payload.operation !== 'inspect'
      || payload.state !== 'ok' || !Array.isArray(payload.rows) || payload.rows.length > 100
      || typeof payload.truncated !== 'boolean' || !Array.isArray(payload.warnings)) {
      invalidInspect();
    }
    this.rows = payload.rows.map(inspectRow);
    this.aggregates = inspectAggregates(payload.aggregates);
    if (this.aggregates.sampleRows !== this.rows.length) {
      invalidInspect();
    }
    this.truncated = payload.truncated;
    this.warnings = payload.warnings.map(function (warning) {
      return inspectText(warning, 256);
    });
  }

  function HeatmapExplorerWorkspace(rootElement, options) {
    this.root = rootElement;
    this.options = isRecord(options) ? options : {};
    this.window = this.options.window || (typeof window !== 'undefined' ? window : null);
    this.document = this.options.document || (this.window && this.window.document ? this.window.document : null);
    this.Scene = typeof this.options.Scene === 'function' ? this.options.Scene : HeatmapExplorerScene;
    this.Renderer = typeof this.options.Renderer === 'function' ? this.options.Renderer : HeatmapGlRenderer;
    this.fetch = typeof this.options.fetch === 'function'
      ? this.options.fetch
      : (this.window && typeof this.window.fetch === 'function' ? this.window.fetch.bind(this.window) : null);
    this.messages = isRecord(this.options.messages)
      ? this.options.messages
      : (this.window && this.window.HLX_I18N && isRecord(this.window.HLX_I18N.heatmapExplorer)
        ? this.window.HLX_I18N.heatmapExplorer : {});
    this.endpoint = workspaceUrlBase(workspaceAttribute(rootElement, 'data-heatmap-endpoint', 'heatmap_points.php'));
    this.v1Url = workspaceAttribute(rootElement, 'data-heatmap-v1-url', '');
    this.lang = workspaceAttribute(rootElement, 'data-heatmap-lang', 'en') === 'ru' ? 'ru' : 'en';
    this.allowMe = workspaceAttribute(rootElement, 'data-heatmap-allow-me', '0') === '1';
    this.allowDifference = workspaceAttribute(rootElement, 'data-heatmap-allow-difference', '0') === '1';
    this.state = {
      game: workspaceAttribute(rootElement, 'data-heatmap-game', ''),
      map: workspaceAttribute(rootElement, 'data-heatmap-map', ''),
      player: workspaceInteger(workspaceAttribute(rootElement, 'data-heatmap-player', '0'), 0),
      range: '30d',
      from: null,
      to: null,
      lens: workspaceAttribute(rootElement, 'data-heatmap-initial-lens', 'overview'),
      event: 'both',
      floor: 'all',
      cell: null,
      focusedCell: null
    };
    this._mapStyle = 'color';
    this._appearance = 'clear';
    this._displayMode = 'smooth';
    this._pointGeometry = null;
    this._geometryGeneration = 0;
    this._geometryLoading = false;
    this._nodes = null;
    this._listeners = [];
    this._renderer = null;
    this._camera = null;
    this._scene = null;
    this._lastRequestUrl = null;
    this._lastReason = null;
    this._panMode = false;
    this._mounted = false;
    this._destroyed = false;
    this._loading = false;
    this._sceneGeneration = 0;
    this._inspectGeneration = 0;
    this._lastRequestType = null;
    this._lastInspectCell = null;
    this._mapImageReloadAttempted = false;
    this._initialUrlError = false;
    this._readUrlState();
    this._normalizeSelection(false);
  }

  HeatmapExplorerWorkspace.prototype._message = function (key) {
    if (key === 'static_fallback' || key === 'context_lost') {
      key = 'fallback';
    }
    var value = this.messages && this.messages[key];
    if (typeof value === 'string' && value !== '') {
      return value;
    }
    value = workspaceAttribute(this.root, workspaceMessageAttribute(key), '');
    return value !== '' ? value : key;
  };

  HeatmapExplorerWorkspace.prototype._listen = function (target, type, handler) {
    if (target && typeof target.addEventListener === 'function') {
      target.addEventListener(type, handler);
      this._listeners.push({target: target, type: type, handler: handler});
    }
  };

  HeatmapExplorerWorkspace.prototype._removeListeners = function () {
    for (var index = 0; index < this._listeners.length; index += 1) {
      var item = this._listeners[index];
      if (item.target && typeof item.target.removeEventListener === 'function') {
        item.target.removeEventListener(item.type, item.handler);
      }
    }
    this._listeners = [];
  };

  HeatmapExplorerWorkspace.prototype._search = function () {
    if (typeof this.options.search === 'string') {
      return this.options.search;
    }
    if (this.window && this.window.location && typeof this.window.location.search === 'string') {
      return this.window.location.search;
    }
    return '';
  };

  HeatmapExplorerWorkspace.prototype._nowSeconds = function () {
    return normalizeNowSeconds(this.options);
  };

  HeatmapExplorerWorkspace.prototype._readUrlState = function () {
    try {
      var parsed = parseUrlState(this._search(), {nowSeconds: this._nowSeconds()});
      var keys = ['range', 'from', 'to', 'lens', 'event', 'floor', 'cell'];
      for (var index = 0; index < keys.length; index += 1) {
        var key = keys[index];
        if (own(parsed, key)) {
          this.state[key] = parsed[key];
        }
      }
      this.state.focusedCell = this.state.cell;
      if (own(parsed, 'range')) {
        this.state.from = null;
        this.state.to = null;
      }
      if (own(parsed, 'from')) {
        this.state.range = null;
      }
    } catch (error) {
      this._initialUrlError = true;
    }
  };

  HeatmapExplorerWorkspace.prototype._urlState = function () {
    var state = {
      lens: this.state.lens,
      event: this.state.event,
      floor: this.state.floor,
      cell: this.state.cell
    };
    if (this.state.range) {
      state.range = this.state.range;
    } else if (safeInteger(this.state.from) && safeInteger(this.state.to)) {
      state.from = this.state.from;
      state.to = this.state.to;
    }
    return state;
  };

  HeatmapExplorerWorkspace.prototype._writeUrl = function () {
    var serialized;
    try {
      serialized = serializeUrlState(this._search(), this._urlState(), {nowSeconds: this._nowSeconds()});
    } catch (error) {
      this._showAlert('invalidUrl');
      return '';
    }
    var pathname = this.window && this.window.location && typeof this.window.location.pathname === 'string'
      ? this.window.location.pathname : '';
    var href = pathname + serialized;
    if (this._nodes && this._nodes.share) {
      workspaceSetAttribute(this._nodes.share, 'href', href);
    }
    if (this.window && this.window.history && typeof this.window.history.replaceState === 'function') {
      try {
        this.window.history.replaceState(null, '', href);
      } catch (error) {
        // The visible share URL remains useful if history is unavailable.
      }
    }
    return href;
  };

  HeatmapExplorerWorkspace.prototype._sceneState = function (inspectCell) {
    var state = {
      v: '2',
      game: this.state.game,
      map: this.state.map,
      event: this.state.event,
      lens: this.state.lens,
      floor: this.state.floor,
      lang: this.lang
    };
    if (this.state.player > 0) {
      state.player = String(this.state.player);
    }
    if (this.state.range) {
      state.range = this.state.range;
    } else {
      state.from = String(this.state.from);
      state.to = String(this.state.to);
    }
    if (inspectCell) {
      state.inspect = inspectCell;
    }
    return state;
  };

  HeatmapExplorerWorkspace.prototype._requestUrl = function (state) {
    var order = ['v', 'game', 'map', 'player', 'range', 'from', 'to', 'event', 'lens', 'floor', 'lang', 'inspect'];
    var pairs = [];
    for (var index = 0; index < order.length; index += 1) {
      var key = order[index];
      if (own(state, key)) {
        pairs.push(encodeURIComponent(key) + '=' + encodeURIComponent(state[key]));
      }
    }
    return this.endpoint + '?' + pairs.join('&');
  };

  HeatmapExplorerWorkspace.prototype.sceneUrl = function () {
    return this._requestUrl(this._sceneState(null));
  };

  HeatmapExplorerWorkspace.prototype.inspectUrl = function (cell) {
    var parsed = parseCellId(typeof cell === 'string' ? cell : this.state.cell);
    return parsed ? this._requestUrl(this._sceneState(parsed.cell)) : this.sceneUrl();
  };

  HeatmapExplorerWorkspace.prototype._setStatus = function (key) {
    if (this._nodes && this._nodes.status) {
      workspaceSetText(this._nodes.status, this._message(key));
    }
  };

  HeatmapExplorerWorkspace.prototype._clearAlert = function () {
    if (!this._nodes || !this._nodes.alert) {
      return;
    }
    workspaceSetText(this._nodes.alert, '');
    this._nodes.alert.hidden = true;
    while (this._nodes.alert.firstChild && typeof this._nodes.alert.removeChild === 'function') {
      this._nodes.alert.removeChild(this._nodes.alert.firstChild);
    }
  };

  HeatmapExplorerWorkspace.prototype._showAlert = function (key) {
    if (!this._nodes || !this._nodes.alert) {
      return;
    }
    workspaceSetText(this._nodes.alert, this._message(key));
    this._nodes.alert.hidden = false;
  };

  HeatmapExplorerWorkspace.prototype._knownFallbackUrl = function (scene) {
    var activeScene = scene || this._scene;
    var baseUrl = this.v1Url;
    if ((typeof baseUrl !== 'string' || baseUrl === '') && activeScene && activeScene.fallback
      && typeof activeScene.fallback.v1 === 'string' && activeScene.fallback.v1.length > 0) {
      baseUrl = activeScene.fallback.v1;
    }
    return rewriteLegacyFallbackUrl(baseUrl, this.state);
  };

  HeatmapExplorerWorkspace.prototype._appendAlertAction = function (factory) {
    if (!this._nodes || !this._nodes.alert || !this.document || typeof this.document.createElement !== 'function') {
      return null;
    }
    var alert = this._nodes.alert;
    var actions = this.document.createElement('div');
    actions.className = 'heatmap-explorer__alert-actions';
    actions.setAttribute('class', 'heatmap-explorer__alert-actions');
    var created = factory(actions);
    if (!created || typeof alert.appendChild !== 'function') {
      return null;
    }
    alert.appendChild(actions);
    return actions;
  };

  HeatmapExplorerWorkspace.prototype._showFailureActions = function () {
    if (!this._nodes || !this._nodes.alert || !this.document || typeof this.document.createElement !== 'function') {
      return;
    }
    var self = this;
    this._appendAlertAction(function (actions) {
      var retry = self.document.createElement('button');
      retry.type = 'button';
      retry.textContent = self._message('retry');
      self._listen(retry, 'click', function () {
        self.retry();
      });
      actions.appendChild(retry);
      var fallbackHref = self._knownFallbackUrl(null);
      if (fallbackHref !== '') {
        var openV1 = self.document.createElement('a');
        openV1.textContent = self._message('openV1');
        workspaceSetAttribute(openV1, 'href', fallbackHref);
        actions.appendChild(openV1);
      }
      return true;
    });
  };

  HeatmapExplorerWorkspace.prototype._showStateAlert = function (scene) {
    var self = this;
    this._showAlert(scene.state);
    this._appendAlertAction(function (actions) {
      var fallbackHref = self._knownFallbackUrl(scene);
      if (fallbackHref === '') {
        return false;
      }
      var openV1 = self.document.createElement('a');
      openV1.textContent = self._message('openV1');
      workspaceSetAttribute(openV1, 'href', fallbackHref);
      actions.appendChild(openV1);
      return true;
    });
  };

  HeatmapExplorerWorkspace.prototype._applyCustomWindow = function () {
    try {
      if (!this._nodes || !this._nodes.from || !this._nodes.to) {
        invalidUrl();
      }
      var from = utcInputSeconds(this._nodes.from.value);
      var to = utcInputSeconds(this._nodes.to.value);
      validateCustomWindow(from, to, this._nowSeconds());
      this._setState({range: null, from: from, to: to, cell: null}, 'range');
      return true;
    } catch (error) {
      this._showAlert('invalidUrl');
      this._setStatus('invalidUrl');
      return false;
    }
  };

  HeatmapExplorerWorkspace.prototype._normalizeSelection = function (announce) {
    if (!this.allowMe && (this.state.lens === 'me' || this.state.lens === 'difference')) {
      this.state.lens = 'overview';
    }
    if (!this.allowDifference && this.state.lens === 'difference') {
      this.state.lens = 'overview';
    }
    if (this.state.lens === 'difference' && this.state.event === 'both') {
      this.state.event = 'kills';
      if (announce) {
        this._setStatus('differenceBothCorrected');
      }
    }
  };

  HeatmapExplorerWorkspace.prototype._renderFloors = function (scene) {
    if (!this._nodes || !this._nodes.floorOptions || !this.document
      || typeof this.document.createElement !== 'function' || typeof this._nodes.floorOptions.appendChild !== 'function') {
      return;
    }
    var options = this._nodes.floorOptions;
    var activeElement = this.document.activeElement;
    var activeFloor = null;
    var existingControls = workspaceNodes(this.root, '[data-heatmap-floor]');
    for (var controlIndex = 0; controlIndex < existingControls.length; controlIndex += 1) {
      if (existingControls[controlIndex] === activeElement && typeof activeElement.getAttribute === 'function') {
        activeFloor = activeElement.getAttribute('data-heatmap-floor');
        break;
      }
    }
    while (options.firstChild && typeof options.removeChild === 'function') {
      options.removeChild(options.firstChild);
    }
    var self = this;
    var replacementFocus = null;
    function appendFloor(id, label, available, count) {
      var control = self.document.createElement('input');
      var wrapper = self.document.createElement('label');
      var description = id === 'all' ? label : label + ' (' + String(count) + ')';
      if (available === false) {
        description += ' - ' + self._message('unavailable');
        workspaceSetAttribute(wrapper, 'data-unavailable', '1');
      }
      wrapper.className = 'heatmap-explorer__floor-option';
      workspaceSetAttribute(wrapper, 'class', 'heatmap-explorer__floor-option');
      control.type = 'radio';
      control.name = 'heatmap-floor-' + self.state.player;
      control.value = id;
      control.disabled = available === false;
      workspaceSetAttribute(control, 'data-heatmap-floor', id);
      control.checked = id === self.state.floor;
      if (id === activeFloor && !control.disabled) {
        replacementFocus = control;
      }
      wrapper.appendChild(control);
      if (typeof self.document.createTextNode === 'function') {
        wrapper.appendChild(self.document.createTextNode(description));
      } else {
        workspaceSetText(wrapper, description);
      }
      options.appendChild(wrapper);
    }
    appendFloor('all', this._message('allFloors'), true, 0);
    for (var index = 0; index < scene.floors.length; index += 1) {
      var floor = scene.floors[index];
      appendFloor(floor.id, floor.label, floor.available, floor.count);
    }
    if (replacementFocus && typeof replacementFocus.focus === 'function') {
      replacementFocus.focus();
    }
  };

  HeatmapExplorerWorkspace.prototype._syncControls = function () {
    if (!this.root) {
      return;
    }
    var lensControls = workspaceNodes(this.root, '[data-heatmap-lens]');
    var eventControls = workspaceNodes(this.root, '[data-heatmap-event]');
    var mapStyleControls = workspaceNodes(this.root, '[data-heatmap-map-style-option]');
    var floorControls = workspaceNodes(this.root, '[data-heatmap-floor]');
    var index;
    workspaceSetAttribute(this.root, 'data-heatmap-map-style', this._mapStyle);
    workspaceSetAttribute(this.root, 'data-heatmap-display-mode', this._displayMode);
    var hasFloors = this._scene && this._scene.floors.length ? '1' : '0';
    var hasCell = this.state.cell ? '1' : '0';
    var layoutChanged = workspaceAttribute(this.root, 'data-heatmap-has-floors', '') !== hasFloors
      || workspaceAttribute(this.root, 'data-heatmap-has-cell', '') !== hasCell;
    workspaceSetAttribute(this.root, 'data-heatmap-has-floors', hasFloors);
    workspaceSetAttribute(this.root, 'data-heatmap-has-cell', hasCell);
    if (layoutChanged && this._renderer && this._renderer.resize) this._renderer.resize();
    var displayControls = workspaceNodes(this.root, '[data-heatmap-display-option]');
    for (index = 0; index < displayControls.length; index++) {
      var selectedDisplay = displayControls[index].getAttribute('data-heatmap-display-option') === this._displayMode;
      workspaceSetAttribute(displayControls[index], 'aria-pressed', selectedDisplay ? 'true' : 'false');
      if (displayControls[index].classList) displayControls[index].classList.toggle('is-selected', selectedDisplay);
    }
    var legend = workspaceNode(this.root, '[data-heatmap-legend]');
    workspaceSetText(legend, this._message(this.state.lens === 'difference' ? 'differenceLegend' : (this.state.event === 'both' ? 'bothLegend' : (this.state.event === 'deaths' ? 'deathsLegend' : 'densityLegend'))));
    var appearanceControls = workspaceNodes(this.root, '[data-heatmap-appearance-option]');
    for (index = 0; index < appearanceControls.length; index++) {
      var selectedAppearance = appearanceControls[index].getAttribute('data-heatmap-appearance-option') === (this.state.lens === 'difference' ? 'soft' : this._appearance);
      workspaceSetAttribute(appearanceControls[index], 'aria-pressed', selectedAppearance ? 'true' : 'false');
      if (appearanceControls[index].classList) appearanceControls[index].classList.toggle('is-selected',selectedAppearance);
      appearanceControls[index].disabled = this._displayMode !== 'smooth' || this.state.lens === 'difference';
    }
    for (index = 0; index < lensControls.length; index += 1) {
      var lens = lensControls[index].getAttribute ? lensControls[index].getAttribute('data-heatmap-lens') : '';
      var selectedLens = lens === this.state.lens;
      workspaceSetAttribute(lensControls[index], 'aria-pressed', selectedLens ? 'true' : 'false');
      if (lensControls[index].classList && typeof lensControls[index].classList.toggle === 'function') {
        lensControls[index].classList.toggle('is-selected', selectedLens);
      }
    }
    for (index = 0; index < eventControls.length; index += 1) {
      var event = eventControls[index].getAttribute ? eventControls[index].getAttribute('data-heatmap-event') : '';
      var selectedEvent = event === this.state.event;
      var disabled = this.state.lens === 'difference' && event === 'both';
      eventControls[index].disabled = disabled;
      workspaceSetAttribute(eventControls[index], 'aria-pressed', selectedEvent ? 'true' : 'false');
      if (eventControls[index].classList && typeof eventControls[index].classList.toggle === 'function') {
        eventControls[index].classList.toggle('is-selected', selectedEvent);
      }
    }
    for (index = 0; index < mapStyleControls.length; index += 1) {
      var style = mapStyleControls[index].getAttribute ? mapStyleControls[index].getAttribute('data-heatmap-map-style-option') : '';
      var selectedStyle = style === this._mapStyle;
      workspaceSetAttribute(mapStyleControls[index], 'aria-pressed', selectedStyle ? 'true' : 'false');
      if (mapStyleControls[index].classList && typeof mapStyleControls[index].classList.toggle === 'function') {
        mapStyleControls[index].classList.toggle('is-selected', selectedStyle);
      }
    }
    for (index = 0; index < floorControls.length; index += 1) {
      var floor = floorControls[index].getAttribute ? floorControls[index].getAttribute('data-heatmap-floor') : '';
      floorControls[index].checked = floor === this.state.floor;
    }
    if (this._nodes && this._nodes.range) {
      this._nodes.range.value = this.state.range || 'custom';
    }
    var windowFrom = this._scene && this._scene.query ? this._scene.query.from : this.state.from;
    var windowTo = this._scene && this._scene.query ? this._scene.query.to : this.state.to;
    if (this._nodes && this._nodes.from) {
      this._nodes.from.value = utcInputValue(windowFrom);
    }
    if (this._nodes && this._nodes.to) {
      this._nodes.to.value = utcInputValue(windowTo);
    }
    if (this._nodes && this._nodes.pan) {
      workspaceSetAttribute(this._nodes.pan, 'aria-pressed', this._panMode ? 'true' : 'false');
      workspaceSetText(this._nodes.pan, this._message(this._panMode ? 'pan' : 'navigation'));
    }
    var panActive = this._panMode ? '1' : '0';
    workspaceSetAttribute(this.root, 'data-heatmap-pan-active', panActive);
    if (this._nodes && this._nodes.stage) {
      workspaceSetAttribute(this._nodes.stage, 'data-heatmap-pan-active', panActive);
      if (this._nodes.stage.style) {
        this._nodes.stage.style.touchAction = this._panMode ? 'none' : 'auto';
      }
    }
    if (this._nodes && this._nodes.canvas) {
      workspaceSetAttribute(this._nodes.canvas, 'data-heatmap-pan-active', panActive);
      if (this._nodes.canvas.style) {
        this._nodes.canvas.style.touchAction = this._panMode ? 'none' : 'auto';
      }
    }
  };

  HeatmapExplorerWorkspace.prototype._setMapStyle = function (style) {
    if (style !== 'color' && style !== 'mono' && style !== 'inverse') {
      return false;
    }
    this._mapStyle = style;
    workspaceSetAttribute(this.root, 'data-heatmap-map-style', style);
    this._syncControls();
    return true;
  };

  HeatmapExplorerWorkspace.prototype._setAppearance = function (appearance) {
    if ((appearance !== 'clear' && appearance !== 'soft') || this.state.lens === 'difference') return false;
    this._appearance = appearance;
    if (this._renderer && this._renderer.setAppearance) this._renderer.setAppearance(appearance);
    this._syncControls();
    return true;
  };

  HeatmapExplorerWorkspace.prototype.pointGeometryUrl = function (scene) {
    var query = scene.query, pairs = ['v=2', 'geometry=points'];
    Object.keys(query).forEach(function (key) {
      if (key === 'player' && query[key] === 0) return;
      pairs.push(encodeURIComponent(key) + '=' + encodeURIComponent(query[key]));
    });
    return this.endpoint + '?' + pairs.join('&');
  };

  HeatmapExplorerWorkspace.prototype._setDisplayMode = function (mode) {
    if (['smooth', 'cells', 'points'].indexOf(mode) < 0) return false;
    if (mode === 'points' && this._displayMode === mode && this._geometryLoading) return this._geometryPromise;
    this._displayMode = mode;
    this._geometryGeneration++;
    this._geometryLoading = false;
    this._syncControls();
    if (mode === 'points') return this._loadPointGeometry();
    if (this._renderer && this._renderer.setDisplayMode) this._renderer.setDisplayMode(mode);
    if (this._scene) this._setCoverageStatus(this._scene);
    return true;
  };

  HeatmapExplorerWorkspace.prototype._fallbackFromPoints = function () {
    this._displayMode = 'cells'; this._geometryLoading = false;
    if (this._renderer && this._renderer.setDisplayMode) this._renderer.setDisplayMode('cells');
    this._syncControls(); this._setStatus('pointsUnavailable');
    return false;
  };

  HeatmapExplorerWorkspace.prototype._loadPointGeometry = function () {
    var self = this, scene = this._scene;
    if (!scene || !this.fetch || this._loading || BLOCKED_SCENE_STATES[scene.state]) return Promise.resolve(false);
    if (this._pointGeometry && this._pointGeometry.matchesScene(scene)) {
      if (this._renderer && this._renderer.setDisplayMode && this._renderer.setDisplayMode('points', this._pointGeometry) === false) return Promise.resolve(this._fallbackFromPoints());
      return Promise.resolve(true);
    }
    if (this._geometryLoading) return this._geometryPromise;
    var generation = ++this._geometryGeneration;
    this._geometryLoading = true; this._setStatus('loading');
    this._geometryPromise = Promise.resolve().then(function () {
      return self.fetch(self.pointGeometryUrl(scene), {credentials: 'same-origin'});
    }).then(function (response) {
      if (!response || response.ok === false || typeof response.json !== 'function') throw new Error('points_unavailable');
      return response.json();
    }).then(function (payload) {
      if (self._destroyed || generation !== self._geometryGeneration || self._displayMode !== 'points' || scene !== self._scene) return false;
      var geometry = new HeatmapPointGeometry(payload);
      if (!geometry.matchesScene(scene)) throw new Error('points_identity');
      self._pointGeometry = geometry; self._geometryLoading = false;
      if (self._renderer && self._renderer.setDisplayMode && self._renderer.setDisplayMode('points', geometry) === false) return self._fallbackFromPoints();
      self._setCoverageStatus(scene); return true;
    }).catch(function () {
      if (!self._destroyed && generation === self._geometryGeneration) return self._fallbackFromPoints();
      return false;
    });
    return this._geometryPromise;
  };

  function displayUtc(value) {
    var date = new Date(value * 1000);
    return isNaN(date.getTime()) ? String(value) : date.toISOString().slice(0, 16).replace('T', ' ');
  }

  HeatmapExplorerWorkspace.prototype._formatPercent = function (value) {
    if (!finiteNumber(value)) {
      return '0%';
    }
    return Math.round(value * 100) + '%';
  };

  HeatmapExplorerWorkspace.prototype._summaryText = function (scene) {
    var query = scene.query || {};
    var coverage = scene.coverage || {};
    var summary = scene.summary || {};
    return this._message('period') + ': ' + displayUtc(query.from) + ' – ' + displayUtc(query.to) + ' UTC; '
      + this._message('sample') + ': ' + String(summary.sourceRows || 0) + '; '
      + this._message('xyCoverage') + ': ' + this._formatPercent(coverage.xyCoverage);
  };

  HeatmapExplorerWorkspace.prototype._updateSceneText = function (scene) {
    var summary = this._summaryText(scene);
    workspaceSetText(this._nodes.summary, summary);
    workspaceSetText(this._nodes.period, this._message('period') + ': ' + displayUtc(scene.query.from) + ' – ' + displayUtc(scene.query.to) + ' UTC');
    workspaceSetText(this._nodes.window, this._message('utcWindow') + ': ' + displayUtc(scene.query.from) + ' – ' + displayUtc(scene.query.to));
    workspaceSetText(this._nodes.sample, this._message('sample') + ': ' + String(scene.summary.sourceRows || 0));
    workspaceSetText(this._nodes.coverage, this._message('coverage') + ': '
      + this._message('xyCoverage') + ' ' + this._formatPercent(scene.coverage.xyCoverage)
      + '; ' + this._message('zCoverage') + ' ' + this._formatPercent(scene.coverage.zCoverage)
      + '; ' + this._message('projectionCoverage') + ' ' + this._formatPercent(scene.coverage.projectionCoverage));
    workspaceSetText(this._nodes.freshness, this._message('freshness') + ': ' + this._message('loaded'));
  };

  HeatmapExplorerWorkspace.prototype._setCoverageStatus = function (scene) {
    if (scene.state === 'empty' || scene.state === 'insufficient_sample') {
      this._setStatus(scene.state);
      return;
    }
    if (!this._nodes || !this._nodes.status) {
      return;
    }
    var coverage = scene.coverage || {};
    var positions = scene.query.lens === 'difference'
      ? scene.summary.personalSample + scene.summary.otherSample
      : scene.dense(scene.query.lens === 'me' ? 'me' : 'total', scene.query.event).values.reduce(function (sum, value) { return sum + value; }, 0);
    workspaceSetText(
      this._nodes.status,
      this._message('loaded') + ' · ' + this._message('sample') + ': ' + String(scene.summary.sourceRows || 0)
        + ' · ' + this._message('visiblePositions') + ': ' + String(positions)
        + ' · ' + this._message('coverage') + ' ' + this._formatPercent(coverage.xyCoverage)
        + (scene.surfaces ? (' · ' + (scene.surfaceGraph
          ? (this._displayMode === 'smooth'
            ? (this.lang === 'ru' ? 'С учётом стен' : 'Walls respected')
            : (this.lang === 'ru' ? 'Учёт стен — в режиме «Плавно»' : 'Walls apply in Smooth mode'))
          : (scene.surfaces.state === 'low_coverage'
            ? (this.lang === 'ru' ? 'Обычная карта: недостаточно точек с надёжной привязкой' : 'Ordinary map: too few reliably located positions')
            : (this.lang === 'ru' ? 'Обычная карта: геометрия недоступна' : 'Ordinary map: geometry unavailable')))
          + (scene.surfaces.state !== 'low_coverage' && scene.surfaces.diagnostics.candidate ? ' (' + scene.surfaces.diagnostics.assigned + '/' + scene.surfaces.diagnostics.candidate + ')' : '')) : '')
    );
  };

  HeatmapExplorerWorkspace.prototype._syncAuthoritativeMap = function (scene, reason) {
    var changedMap = !this._scene || this._scene.map.name !== scene.map.name || this._scene.map.game !== scene.map.game;
    if (reason !== 'floor' || changedMap || !this._scene || this._scene.map.image.url !== scene.map.image.url) {
      workspaceSetAttribute(this._nodes.image, 'src', scene.map.image.url);
      workspaceSetAttribute(this._nodes.image, 'alt', scene.map.name);
      workspaceSetAttribute(this._nodes.staticLink, 'href', scene.fallback.jpeg);
      workspaceSetAttribute(this._nodes.jpegLink, 'href', scene.fallback.jpeg);
      workspaceSetAttribute(this._nodes.staticImage, 'src', scene.fallback.jpeg);
      workspaceSetAttribute(this._nodes.staticImage, 'alt', scene.map.name);
    }
    workspaceSetAttribute(this.root, 'data-heatmap-game', scene.map.game);
    workspaceSetAttribute(this.root, 'data-heatmap-map', scene.map.name);
    workspaceSetText(this._nodes.mapTitle, scene.map.name);
    if (this._nodes.mapSelect) {
      this._nodes.mapSelect.value = scene.map.name;
    }
  };

  HeatmapExplorerWorkspace.prototype._destroyRenderer = function () {
    if (this._renderer && typeof this._renderer.destroy === 'function') {
      this._renderer.destroy();
    }
    this._renderer = null;
  };

  HeatmapExplorerWorkspace.prototype._syncStageAspect = function (scene) {
    if (!this._nodes || !this._nodes.stage) {
      return workspaceSceneImageSize(scene, null);
    }
    var size = workspaceSceneImageSize(scene, this._nodes.image);
    if (this._nodes.stage.style) {
      this._nodes.stage.style.aspectRatio = size.width + ' / ' + size.height;
    }
    workspaceSetAttribute(this._nodes.stage, 'data-heatmap-sized', '1');
    if (this._nodes.image) {
      workspaceSetAttribute(this._nodes.image, 'width', size.width);
      workspaceSetAttribute(this._nodes.image, 'height', size.height);
    }
    return size;
  };

  HeatmapExplorerWorkspace.prototype._createRenderer = function (scene) {
    this._destroyRenderer();
    var self = this;
    var stage = this._nodes.stage;
    var size = this._syncStageAspect(scene);
    var width = size.width;
    var height = size.height;
    this._camera = new HeatmapExplorerCamera({
      viewportWidth: stage && finiteNumber(stage.clientWidth) ? stage.clientWidth : scene.map.image.width,
      viewportHeight: stage && finiteNumber(stage.clientHeight) ? stage.clientHeight : scene.map.image.height,
      contentWidth: width > 0 ? width : scene.map.image.width,
      contentHeight: height > 0 ? height : scene.map.image.height,
      reducedMotion: !!(this.window && this.window.matchMedia && this.window.matchMedia('(prefers-reduced-motion: reduce)').matches)
    });
    this._renderer = new this.Renderer(this.root, scene, {
      window: this.window,
      appearance: this._appearance,
      cameraKeys: false,
      pointerPan: function () {
        return self._panMode;
      },
      message: this._message.bind(this),
      // Mount may briefly draw Smooth/Cells before the requested view is ready.
      // That internal frame must not release a compatible Cells/Points lock.
      scaleMaximum: function (maximum, mode) { return mode === self._displayMode ? self._scaleMaximum(scene, maximum, mode) : maximum; }
    });
    if (typeof this._renderer.setCamera === 'function') {
      this._renderer.setCamera(this._camera);
    }
    this._renderer.mount();
    if (this._renderer.setDisplayMode) this._renderer.setDisplayMode(this._displayMode === 'points' ? 'cells' : this._displayMode);
    if (typeof this._renderer.setCamera === 'function') {
      this._renderer.setCamera(this._camera);
    }
  };

  HeatmapExplorerWorkspace.prototype._clipRegions = function (scene) {
    if (this._regionSvg && this._regionSvg.parentNode) this._regionSvg.parentNode.removeChild(this._regionSvg);
    this._regionSvg = null;
    if (!this._nodes.canvas.style) return;
    this._nodes.canvas.style.clipPath = '';
    this._nodes.canvas.style.mask = '';
    var regions = sceneRegions(scene), blocked = sceneRegions(scene, 'blocked');
    if ((!regions.length && !blocked.length) || !this.document.createElementNS) return;
    var ns = 'http://www.w3.org/2000/svg', svg = this.document.createElementNS(ns, 'svg');
    var clip = this.document.createElementNS(ns, 'clipPath');
    var id = 'hm-region-' + scene.query.player + '-' + scene.map.name;
    svg.setAttribute('width', '0'); svg.setAttribute('height', '0');
    svg.style.position = 'absolute'; svg.setAttribute('aria-hidden', 'true');
    clip.setAttribute('id', id); clip.setAttribute('clipPathUnits', 'objectBoundingBox');
    regions.forEach(function (p) {
      var polygon = this.document.createElementNS(ns, 'polygon');
      polygon.setAttribute('points', p.map(function (v) { return v[0] / scene.map.image.width + ',' + v[1] / scene.map.image.height; }).join(' '));
      clip.appendChild(polygon);
    }, this);
    svg.appendChild(clip); this.root.appendChild(svg); this._regionSvg = svg;
    if (regions.length) this._nodes.canvas.style.clipPath = 'url(#' + id + ')';
    if (blocked.length) {
      var mask = this.document.createElementNS(ns, 'mask'), white = this.document.createElementNS(ns, 'rect');
      mask.setAttribute('id', id + '-walls'); mask.setAttribute('maskUnits', 'objectBoundingBox'); mask.setAttribute('maskContentUnits', 'objectBoundingBox');
      mask.setAttribute('x', '0'); mask.setAttribute('y', '0'); mask.setAttribute('width', '1'); mask.setAttribute('height', '1');
      white.setAttribute('width', '1'); white.setAttribute('height', '1'); white.setAttribute('fill', 'white'); mask.appendChild(white);
      blocked.forEach(function (p) {
        var polygon = this.document.createElementNS(ns, 'polygon');
        polygon.setAttribute('points', p.map(function (v) { return v[0] / scene.map.image.width + ',' + v[1] / scene.map.image.height; }).join(' '));
        polygon.setAttribute('fill', 'black'); mask.appendChild(polygon);
      }, this);
      svg.appendChild(mask); this._nodes.canvas.style.mask = 'url(#' + id + '-walls)';
    }
  };

  HeatmapExplorerWorkspace.prototype._scaleMaximum = function (scene, maximum, mode) {
    var key = JSON.stringify([scene.map, scene.activeFloor, scene.query.player, scene.query.lens, scene.query.event, mode,
      mode === 'smooth' && scene.surfaceGraph ? scene.surfaces.asset.sha256 : 'ordinary',
      mode === 'smooth' && scene.query.lens !== 'difference' ? this._appearance : 'unchanged']);
    if (this._scaleReference && this._scaleReference.key !== key) {
      this._scaleReference = null;
      this._scaleReset = true;
    }
    this._scaleCurrent = {key: key, maximum: maximum};
    var limit = this._scaleReference ? this._scaleReference.maximum : maximum;
    var factor = scene.query.lens === 'difference' ? 100 : 1;
    var number = function (n) { return Number((n * factor).toPrecision(3)).toLocaleString(this.lang); }.bind(this);
    var unit = this._message(scene.query.lens === 'difference' ? 'scaleDifference' : (mode === 'smooth' ? 'scaleSmooth' : (mode === 'points' ? 'scalePoints' : 'scaleCells')));
    if (mode === 'smooth' && scene.grid) {
      var fieldGrid = scene.surfaceGraph ? scene.surfaceGraph.grid : scene.grid;
      var cellWidth = scene.surfaceGraph ? scene.map.image.width / fieldGrid.width : scene.grid.bucketSize;
      var cellHeight = scene.surfaceGraph ? scene.map.image.height / fieldGrid.height : scene.grid.bucketSize;
      unit += ' (' + Number(cellWidth.toFixed(2)).toLocaleString(this.lang) + ' × '
        + Number(cellHeight.toFixed(2)).toLocaleString(this.lang) + ' px)';
      if (scene.query.lens !== 'difference') unit += ' · ' + this._message(this._appearance === 'soft' ? 'soft' : 'clear');
    }
    var node = workspaceNode(this.root, '[data-heatmap-scale-values]');
    var label = (scene.query.lens === 'difference' ? '−' + number(limit) + ' ← 0 → +' : '0 → ') + number(limit) + ' ' + unit;
    label += ' · ' + this._message(this._scaleReference ? 'scaleLocked' : 'scaleAuto');
    if (this._scaleReset) label += ' · ' + this._message('scaleReset');
    if (node && node.textContent !== label) workspaceSetText(node, label);
    var control = workspaceNode(this.root, '[data-heatmap-scale-lock]');
    workspaceSetAttribute(control, 'aria-pressed', this._scaleReference ? 'true' : 'false');
    if (control) control.disabled = !(limit > 0);
    workspaceSetAttribute(this.root, 'data-heatmap-scale-palette', scene.query.lens === 'difference' ? 'difference' : scene.query.event);
    return limit;
  };

  HeatmapExplorerWorkspace.prototype._applyScene = function (scene, reason) {
    this._geometryGeneration++; this._geometryLoading = false; this._pointGeometry = null;
    if (reason !== 'map-image-retry') {
      this._mapImageReloadAttempted = false;
    }
    this._syncAuthoritativeMap(scene, reason);
    this.state.game = scene.map.game;
    this.state.map = scene.map.name;
    this.state.player = scene.query.player;
    this.state.lens = scene.query.lens;
    this.state.event = scene.query.event;
    this.state.floor = scene.activeFloor;
    if (!this.state.range) {
      this.state.from = scene.query.from;
      this.state.to = scene.query.to;
    }
    this._createRenderer(scene);
    this._scene = scene;
    this._clipRegions(scene);
    this._renderFloors(scene);
    this._updateSceneText(scene);
    this._syncControls();
    this._writeUrl();
    this._clearAlert();
    if (scene.state === 'empty' || scene.state === 'insufficient_sample') {
      this._setStatus(scene.state);
    } else if (BLOCKED_SCENE_STATES[scene.state]) {
      this._showStateAlert(scene);
      this._setStatus(scene.state);
    } else {
      this._setCoverageStatus(scene);
    }
    if (this.state.cell && !BLOCKED_SCENE_STATES[scene.state]) {
      this._renderPinnedCell(this.state.cell);
      this._loadInspect(this.state.cell);
    }
    if (this._displayMode === 'points') this._loadPointGeometry();
  };

  HeatmapExplorerWorkspace.prototype._loadScene = function (reason, exactUrl) {
    var self = this;
    var acceptsScene422 = false;
    if (this._destroyed || !this.fetch) {
      return Promise.resolve(false);
    }
    var requestUrl = typeof exactUrl === 'string' ? exactUrl : this.sceneUrl();
    var generation = ++this._sceneGeneration;
    this._geometryGeneration++; this._geometryLoading = false;
    this._inspectGeneration += 1;
    this._lastRequestUrl = requestUrl;
    this._lastReason = reason;
    this._lastRequestType = 'scene';
    this._lastInspectCell = null;
    this._loading = true;
    this._setStatus('loading');
    this._clearAlert();
    return Promise.resolve().then(function () {
      return self.fetch(requestUrl, {credentials: 'same-origin'});
    }).then(function (response) {
      acceptsScene422 = !!(response && response.ok === false && response.status === 422);
      if (!response || typeof response.json !== 'function' || (response.ok === false && !acceptsScene422)) {
        throw new Error('request_failed');
      }
      return response.json();
    }).then(function (payload) {
      if (self._destroyed || generation !== self._sceneGeneration) {
        return false;
      }
      var scene = new self.Scene(payload);
      if (acceptsScene422 && scene.state !== 'too_many_events') {
        throw new Error('request_failed');
      }
      var surface = scene.surfaces && scene.surfaces.state === 'ready' && !BLOCKED_SCENE_STATES[scene.state]
        ? loadSurfaceGraph(self.fetch.bind(self), self.window && self.window.crypto, scene.surfaces.asset).then(function (graph) {
          if (graph.image.width !== scene.map.image.width || graph.image.height !== scene.map.image.height) throw new Error('surface_image');
          scene.surfaceGraph = graph;
        }).catch(function () { scene.surfaceGraph = null; }) : Promise.resolve();
      return surface.then(function () {
        if (self._destroyed || generation !== self._sceneGeneration) return false;
        self._loading = false;
        self._applyScene(scene, reason);
        return true;
      });
    }).catch(function () {
      if (self._destroyed || generation !== self._sceneGeneration) {
        return false;
      }
      self._loading = false;
      self._showAlert('failed');
      self._showFailureActions();
      self._setStatus('failed');
      return false;
    });
  };

  HeatmapExplorerWorkspace.prototype._renderInspect = function (inspect) {
    if (!this._nodes || !this._nodes.inspectOutput) {
      return;
    }
    if (!inspect.rows.length) {
      workspaceSetText(this._nodes.inspectOutput, this._message('noCell'));
      return;
    }
    var rows = [];
    for (var index = 0; index < inspect.rows.length; index += 1) {
      var row = inspect.rows[index];
      var details = [];
      if (row.weapon) {
        details.push(row.weapon);
      }
      if (row.headshot) {
        details.push(this._message('headshot'));
      }
      if (row.teamkill) {
        details.push(this._message('teamkill'));
      }
      rows.push(row.eventTime + ' ' + this._message(row.event === 'kill' ? 'kills' : 'deaths') + ': '
        + row.killer.name + ' → ' + row.victim.name + (details.length ? ' (' + details.join(', ') + ')' : ''));
    }
    var topWeapons = inspect.aggregates.topWeapons.map(function (item) {
      return item.weapon + ' × ' + String(item.count);
    });
    var counts = inspect.aggregates.participantCounts;
    var sample = this._message('inspectSample') + ': ' + String(inspect.aggregates.sampleRows)
      + (inspect.truncated ? ' (' + this._message('truncated') + ')' : '');
    var participants = this._message('participants') + ': ' + String(counts.unique)
      + ' (' + this._message('killers') + ' ' + String(counts.killers)
      + ', ' + this._message('victims') + ' ' + String(counts.victims) + ')';
    var weapons = this._message('topWeapons') + ': ' + (topWeapons.length ? topWeapons.join(', ') : '—');
    workspaceSetText(this._nodes.inspectOutput, sample + '; ' + weapons + '; ' + participants + '. '
      + this._message('inspect') + ' ' + this.state.cell + ': ' + rows.join('; '));
  };

  HeatmapExplorerWorkspace.prototype._loadInspect = function (cell, exactUrl) {
    var self = this;
    var parsed = parseCellId(cell);
    if (this._destroyed || !this.fetch || !this._scene || !parsed) {
      return Promise.resolve(false);
    }
    var generation = ++this._inspectGeneration;
    var sceneGeneration = this._sceneGeneration;
    var requestUrl = typeof exactUrl === 'string' ? exactUrl : this.inspectUrl(parsed.cell);
    this._lastRequestUrl = requestUrl;
    this._lastReason = 'inspect';
    this._lastRequestType = 'inspect';
    this._lastInspectCell = parsed.cell;
    this._setStatus('loading');
    this._clearAlert();
    return Promise.resolve().then(function () {
      return self.fetch(requestUrl, {credentials: 'same-origin'});
    }).then(function (response) {
      if (!response || response.ok === false || typeof response.json !== 'function') {
        throw new Error('request_failed');
      }
      return response.json();
    }).then(function (payload) {
      if (self._destroyed || generation !== self._inspectGeneration
        || sceneGeneration !== self._sceneGeneration || self.state.cell !== parsed.cell) {
        return false;
      }
      var inspect = new HeatmapExplorerInspect(payload);
      if (self._destroyed || generation !== self._inspectGeneration
        || sceneGeneration !== self._sceneGeneration || self.state.cell !== parsed.cell) {
        return false;
      }
      self._renderInspect(inspect);
      self._clearAlert();
      self._setStatus('pinned');
      return true;
    }).catch(function () {
      if (self._destroyed || generation !== self._inspectGeneration
        || sceneGeneration !== self._sceneGeneration || self.state.cell !== parsed.cell) {
        return false;
      }
      self._showAlert('failed');
      self._showFailureActions();
      self._setStatus('failed');
      return false;
    });
  };

  HeatmapExplorerWorkspace.prototype.retry = function () {
    if (this._lastRequestType === 'inspect') {
      if (!this._lastInspectCell || this.state.cell !== this._lastInspectCell) {
        return Promise.resolve(false);
      }
      return this._loadInspect(this._lastInspectCell, this._lastRequestUrl || this.inspectUrl(this._lastInspectCell));
    }
    return this._loadScene(this._lastReason || 'retry', this._lastRequestUrl || this.sceneUrl());
  };

  HeatmapExplorerWorkspace.prototype.showFallback = function () {
    this._destroyRenderer();
    workspaceSetAttribute(this.root, 'data-heatmap-state', 'static_fallback');
    if (this._nodes && this._nodes.static && this._nodes.static.style) {
      this._nodes.static.style.display = '';
    }
    if (this._nodes && this._nodes.interactive && this._nodes.interactive.style) {
      this._nodes.interactive.style.display = 'none';
    }
    this._clearAlert();
    this._setStatus('fallback');
  };

  HeatmapExplorerWorkspace.prototype._showMapImageFallback = function () {
    this.showFallback();
    this._showAlert('failed');
    this._showFailureActions();
  };

  HeatmapExplorerWorkspace.prototype._handleMapImageError = function () {
    var self = this;
    if (this._destroyed || !this._mounted) {
      return;
    }
    if (this._mapImageReloadAttempted) {
      this._showMapImageFallback();
      return;
    }
    this._mapImageReloadAttempted = true;
    var failedUrl = workspaceAttribute(this._nodes.image, 'src', '');
    var recovery = this._loadScene('map-image-retry');
    var recoveryGeneration = this._sceneGeneration;
    recovery.then(function (loaded) {
      if (self._destroyed || self._sceneGeneration !== recoveryGeneration) {
        return;
      }
      var currentUrl = workspaceAttribute(self._nodes.image, 'src', '');
      if (!loaded || currentUrl === '' || currentUrl === failedUrl) {
        self._showMapImageFallback();
      }
    });
  };

  HeatmapExplorerWorkspace.prototype._renderPinnedCell = function (cell) {
    var hasPin = this.state.cell ? '1' : '0';
    if (workspaceAttribute(this.root, 'data-heatmap-has-cell', '') !== hasPin) {
      workspaceSetAttribute(this.root, 'data-heatmap-has-cell', hasPin);
      if (this._renderer && this._renderer.resize) this._renderer.resize();
    }
    if (!this._scene || !this._nodes || !this._nodes.inspectOutput) {
      return;
    }
    var summary = this._scene.cellSummary(cell);
    if (!summary) {
      workspaceSetText(this._nodes.inspectOutput, this._message('noCell'));
      return;
    }
    workspaceSetText(
      this._nodes.inspectOutput,
      this._message('inspect') + ' ' + summary.cell + ': '
        + this._message('kills') + ' ' + summary.total.kills + ', '
        + this._message('deaths') + ' ' + summary.total.deaths
    );
  };

  HeatmapExplorerWorkspace.prototype.pin = function (cell) {
    var parsed = parseCellId(cell);
    if (!parsed) {
      return false;
    }
    this.state.cell = parsed.cell;
    this.state.focusedCell = parsed.cell;
    this._renderPinnedCell(parsed.cell);
    this._writeUrl();
    this._setStatus('pinned');
    if (this._scene && !this._loading) {
      this._loadInspect(parsed.cell);
    }
    return true;
  };

  HeatmapExplorerWorkspace.prototype.clearPin = function () {
    this._inspectGeneration += 1;
    if (this._lastRequestType === 'inspect') {
      this._lastInspectCell = null;
      this._lastRequestUrl = null;
    }
    this.state.cell = null;
    this.state.focusedCell = null;
    workspaceSetAttribute(this.root, 'data-heatmap-has-cell', '0');
    if (this._renderer && this._renderer.resize) this._renderer.resize();
    if (this._nodes && this._nodes.inspectOutput) {
      workspaceSetText(this._nodes.inspectOutput, this._message('noCell'));
    }
    this._writeUrl();
    this._setStatus('unpinned');
  };

  HeatmapExplorerWorkspace.prototype._setState = function (changes, reason) {
    if (!isRecord(changes)) {
      return;
    }
    var keys = Object.keys(changes);
    for (var index = 0; index < keys.length; index += 1) {
      this.state[keys[index]] = changes[keys[index]];
    }
    this._normalizeSelection(reason === 'lens');
    this._syncControls();
    this._loadScene(reason);
  };

  HeatmapExplorerWorkspace.prototype._selectFocusedCell = function (direction) {
    if (!this._scene) {
      return false;
    }
    var layer = this.state.lens === 'overview' ? 'total' : this.state.lens;
    var channel = this.state.event;
    var next = this._scene.nextOccupied(this.state.focusedCell, direction, layer, channel);
    if (!next) {
      return false;
    }
    this.state.focusedCell = next.cell;
    this._renderPinnedCell(next.cell);
    return true;
  };

  HeatmapExplorerWorkspace.prototype._toggleSheet = function (name) {
    if (!this._nodes) {
      return;
    }
    var target = name === 'floors' ? this._nodes.floors : this._nodes.inspector;
    var other = name === 'floors' ? this._nodes.inspector : this._nodes.floors;
    if (!target || !target.classList || typeof target.classList.toggle !== 'function') {
      return;
    }
    var opening = !target.classList.contains('is-open');
    if (other && other.classList && typeof other.classList.remove === 'function') {
      other.classList.remove('is-open');
    }
    target.classList.toggle('is-open', opening);
    var toggles = workspaceNodes(this.root, '[data-heatmap-sheet-toggle]');
    for (var index = 0; index < toggles.length; index += 1) {
      var toggleName = toggles[index].getAttribute ? toggles[index].getAttribute('data-heatmap-sheet-toggle') : '';
      workspaceSetAttribute(toggles[index], 'aria-expanded', toggleName === name && opening ? 'true' : 'false');
    }
  };

  HeatmapExplorerWorkspace.prototype._handleStageKey = function (event) {
    if (!event) {
      return;
    }
    var key = event.key;
    var handled = false;
    if (key === '+' || key === '=' || key === '-' || key === 'Home') {
      if (this._camera && typeof this._camera.handleKey === 'function') {
        handled = this._camera.handleKey(key);
      }
    } else if (key === 'Escape') {
      this.clearPin();
      handled = true;
    } else if (key === 'Enter' || key === ' ') {
      if (this.state.focusedCell) {
        this.pin(this.state.focusedCell);
        handled = true;
      }
    } else if (key === 'ArrowLeft' || key === 'ArrowRight' || key === 'ArrowUp' || key === 'ArrowDown') {
      if (this._panMode && this._camera && typeof this._camera.handleKey === 'function') {
        handled = this._camera.handleKey(key);
      } else {
        var direction = key === 'ArrowLeft' ? 'left' : key === 'ArrowRight' ? 'right' : key === 'ArrowUp' ? 'up' : 'down';
        handled = this._selectFocusedCell(direction);
      }
    }
    if (handled && event.preventDefault) {
      event.preventDefault();
    }
    if (handled && this._renderer && this._camera && typeof this._renderer.setCamera === 'function') {
      this._renderer.setCamera(this._camera);
    }
  };

  HeatmapExplorerWorkspace.prototype._pointerCell = function (event) {
    if (!this._scene || !this._nodes || !this._nodes.canvas || !event
      || typeof this._nodes.canvas.getBoundingClientRect !== 'function') {
      return null;
    }
    return this._scene.cellFromPointer(
      numeric(event.clientX, -1), numeric(event.clientY, -1),
      this._nodes.canvas.getBoundingClientRect(), this._camera
    );
  };

  HeatmapExplorerWorkspace.prototype._bindEvents = function () {
    var self = this;
    var index;
    var lensControls = workspaceNodes(this.root, '[data-heatmap-lens]');
    var eventControls = workspaceNodes(this.root, '[data-heatmap-event]');
    var mapStyleControls = workspaceNodes(this.root, '[data-heatmap-map-style-option]');
    var sheetControls = workspaceNodes(this.root, '[data-heatmap-sheet-toggle]');
    this._listen(this._nodes.image, 'load', function () {
      self._mapImageReloadAttempted = false;
    });
    this._listen(this._nodes.image, 'error', function () {
      self._handleMapImageError();
    });
    for (index = 0; index < lensControls.length; index += 1) {
      this._listen(lensControls[index], 'click', function (event) {
        var lens = event && event.currentTarget && event.currentTarget.getAttribute
          ? event.currentTarget.getAttribute('data-heatmap-lens') : null;
        if (lens) {
          self._setState({lens: lens, cell: null}, 'lens');
        }
      });
    }
    for (index = 0; index < eventControls.length; index += 1) {
      this._listen(eventControls[index], 'click', function (event) {
        var channel = event && event.currentTarget && event.currentTarget.getAttribute
          ? event.currentTarget.getAttribute('data-heatmap-event') : null;
        if (channel && !(self.state.lens === 'difference' && channel === 'both')) {
          self._setState({event: channel, cell: null}, 'channel');
        }
      });
    }
    for (index = 0; index < mapStyleControls.length; index += 1) {
      this._listen(mapStyleControls[index], 'click', function (event) {
        var style = event && event.currentTarget && event.currentTarget.getAttribute
          ? event.currentTarget.getAttribute('data-heatmap-map-style-option') : null;
        self._setMapStyle(style);
      });
    }
    var displayControls = workspaceNodes(this.root, '[data-heatmap-display-option]');
    for (index = 0; index < displayControls.length; index++) {
      this._listen(displayControls[index], 'click', function (event) {
        self._setDisplayMode(event.currentTarget.getAttribute('data-heatmap-display-option'));
      });
    }
    var appearanceControls = workspaceNodes(this.root, '[data-heatmap-appearance-option]');
    for (index = 0; index < appearanceControls.length; index++) {
      this._listen(appearanceControls[index], 'click', function (event) {
        self._setAppearance(event.currentTarget.getAttribute('data-heatmap-appearance-option'));
      });
    }
    this._listen(this._nodes.floors, 'change', function (event) {
      var target = event && event.target;
      var floor = target && target.getAttribute ? target.getAttribute('data-heatmap-floor') : null;
      if (floor) {
        self._setState({floor: floor, cell: null}, 'floor');
      }
    });
    for (index = 0; index < sheetControls.length; index += 1) {
      this._listen(sheetControls[index], 'click', function (event) {
        var sheet = event && event.currentTarget && event.currentTarget.getAttribute
          ? event.currentTarget.getAttribute('data-heatmap-sheet-toggle') : null;
        if (sheet === 'floors' || sheet === 'inspector') {
          self._toggleSheet(sheet);
        }
      });
    }
    this._listen(this._nodes.mapSelect, 'change', function (event) {
      var map = event && event.currentTarget ? workspaceTextValue(event.currentTarget.value) : null;
      if (map) {
        self._setState({map: map, floor: 'all', cell: null}, 'map');
      }
    });
    this._listen(this._nodes.range, 'change', function (event) {
      var range = event && event.currentTarget ? workspaceTextValue(event.currentTarget.value) : null;
      if (range && own(RANGE_SECONDS, range)) {
        self._setState({range: range, from: null, to: null, cell: null}, 'range');
      }
    });
    this._listen(this._nodes.apply, 'click', function () {
      self._applyCustomWindow();
    });
    this._listen(workspaceNode(this.root, '[data-heatmap-scale-lock]'), 'click', function () {
      self._scaleReset = false;
      self._scaleReference = self._scaleReference ? null : self._scaleCurrent;
      if (self._renderer) self._renderer.render();
    });
    this._listen(this._nodes.zoomIn, 'click', function () {
      if (self._camera) {
        self._camera.zoomAt(1.25, 0, 0);
        if (self._renderer) self._renderer.setCamera(self._camera);
      }
    });
    this._listen(this._nodes.zoomOut, 'click', function () {
      if (self._camera) {
        self._camera.zoomAt(0.8, 0, 0);
        if (self._renderer) self._renderer.setCamera(self._camera);
      }
    });
    this._listen(this._nodes.reset, 'click', function () {
      if (self._camera) {
        self._camera.reset();
        if (self._renderer) self._renderer.setCamera(self._camera);
      }
    });
    this._listen(this._nodes.pan, 'click', function () {
      self._panMode = !self._panMode;
      self._syncControls();
    });
    this._listen(this._nodes.stage, 'keydown', function (event) {
      self._handleStageKey(event);
    });
    this._listen(this._nodes.canvas, 'pointermove', function (event) {
      if (self._panMode) {
        return;
      }
      var cell = self._pointerCell(event);
      if (cell) {
        self.state.focusedCell = cell.cell;
        self._renderPinnedCell(cell.cell);
      }
    });
    this._listen(this._nodes.canvas, 'click', function (event) {
      if (self._renderer && typeof self._renderer.consumeSuppressedClick === 'function'
        && self._renderer.consumeSuppressedClick()) {
        return;
      }
      var cell = self._pointerCell(event);
      if (cell) {
        self.pin(cell.cell);
      }
    });
  };

  HeatmapExplorerWorkspace.prototype.mount = function () {
    if (this._mounted || this._destroyed || !this.root) {
      return this;
    }
    this._nodes = {
      interactive: workspaceNode(this.root, '[data-heatmap-interactive]'),
      stage: workspaceNode(this.root, '[data-heatmap-stage]'),
      image: workspaceNode(this.root, '[data-heatmap-image]'),
      canvas: workspaceNode(this.root, '[data-heatmap-canvas]'),
      static: workspaceNode(this.root, '[data-heatmap-static]'),
      staticLink: workspaceNode(this.root, '[data-heatmap-static] a'),
      staticImage: workspaceNode(this.root, '[data-heatmap-static] img'),
      jpegLink: workspaceNode(this.root, '[data-heatmap-jpeg-link]'),
      status: workspaceNode(this.root, '[data-heatmap-status]'),
      alert: workspaceNode(this.root, '[data-heatmap-alert]'),
      summary: workspaceNode(this.root, '[data-heatmap-summary]'),
      period: workspaceNode(this.root, '[data-heatmap-period]'),
      window: workspaceNode(this.root, '[data-heatmap-window]'),
      sample: workspaceNode(this.root, '[data-heatmap-sample]'),
      coverage: workspaceNode(this.root, '[data-heatmap-coverage]'),
      freshness: workspaceNode(this.root, '[data-heatmap-freshness]'),
      inspectOutput: workspaceNode(this.root, '[data-heatmap-inspect-output]'),
      floors: workspaceNode(this.root, '[data-heatmap-floor-sheet]'),
      floorOptions: workspaceNode(this.root, '[data-heatmap-floor-options]'),
      inspector: workspaceNode(this.root, '[data-heatmap-inspector]'),
      mapTitle: workspaceNode(this.root, '[data-heatmap-map-title]'),
      mapSelect: workspaceNode(this.root, '[data-heatmap-map-select]'),
      range: workspaceNode(this.root, '[data-heatmap-range]'),
      from: workspaceNode(this.root, '[data-heatmap-from]'),
      to: workspaceNode(this.root, '[data-heatmap-to]'),
      apply: workspaceNode(this.root, '[data-heatmap-apply]'),
      zoomIn: workspaceNode(this.root, '[data-heatmap-zoom="in"]'),
      zoomOut: workspaceNode(this.root, '[data-heatmap-zoom="out"]'),
      reset: workspaceNode(this.root, '[data-heatmap-reset]'),
      pan: workspaceNode(this.root, '[data-heatmap-pan]'),
      share: workspaceNode(this.root, '[data-heatmap-share]')
    };
    if (!this._nodes.interactive || !this._nodes.stage || !this._nodes.image || !this._nodes.canvas
      || !this._nodes.static || !this._nodes.status || !this._nodes.alert || !this._nodes.summary) {
      this.showFallback();
      return this;
    }
    this._mounted = true;
    this._bindEvents();
    this._syncControls();
    this._writeUrl();
    if (!this.fetch) {
      this.showFallback();
      return this;
    }
    if (this._initialUrlError) {
      this._showAlert('invalidUrl');
      this._setStatus('invalidUrl');
      return this;
    }
    this._loadScene('initial');
    return this;
  };

  HeatmapExplorerWorkspace.prototype.destroy = function () {
    if (this._regionSvg && this._regionSvg.parentNode) this._regionSvg.parentNode.removeChild(this._regionSvg);
    this._regionSvg = null;
    if (this._destroyed) {
      return;
    }
    this._destroyed = true;
    this._mounted = false;
    this._removeListeners();
    this._destroyRenderer();
    if (this._camera && typeof this._camera.destroy === 'function') {
      this._camera.destroy();
    }
    this._camera = null;
  };

  HeatmapExplorerWorkspace.mountAll = function (documentRef, options) {
    if (!documentRef || typeof documentRef.querySelectorAll !== 'function') {
      return [];
    }
    var roots = documentRef.querySelectorAll('[data-heatmap-explorer]');
    var mounted = [];
    for (var index = 0; index < roots.length; index += 1) {
      if (roots[index] && roots[index].getAttribute && roots[index].getAttribute('data-heatmap-mounted') === '1') {
        continue;
      }
      var workspace = new HeatmapExplorerWorkspace(roots[index], options);
      workspace.mount();
      workspaceSetAttribute(roots[index], 'data-heatmap-mounted', '1');
      mounted.push(workspace);
    }
    return mounted;
  };

  return {
    HeatmapExplorerScene: HeatmapExplorerScene,
    HeatmapExplorerCamera: HeatmapExplorerCamera,
    HeatmapExplorerUrlState: HeatmapExplorerUrlState,
    HeatmapExplorerWorkspace: HeatmapExplorerWorkspace,
    HeatmapGlRenderer: HeatmapGlRenderer
    , HeatmapPointGeometry: HeatmapPointGeometry
    , gaussianKernel1d: gaussianKernel1d
    , gaussianSmooth: gaussianSmooth
    , presentationField: presentationField
    , HeatmapSurfaceGraph: HeatmapSurfaceGraph
    , loadSurfaceGraph: loadSurfaceGraph
    , utcInputValue: utcInputValue
    , utcInputSeconds: utcInputSeconds
    , regionContains: regionContains
    , regionGridMask: regionGridMask
  };
}));
