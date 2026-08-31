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
    root.HeatmapGlRenderer = api.HeatmapGlRenderer;
  }
}(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  var hasOwn = Object.prototype.hasOwnProperty;
  var TOKEN = /^[A-Za-z][A-Za-z0-9_-]{0,31}$/;
  var CELL = /^c(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;
  var HASH = /^[a-f0-9]{16}$/;
  var RANGE_SECONDS = {
    '7d': 604800,
    '30d': 2592000,
    '90d': 7776000,
    '365d': 31536000
  };
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
      if (!exactKeys(floor, ['id', 'label', 'count', 'available'])
        || typeof floor.id !== 'string' || !TOKEN.test(floor.id)
        || typeof floor.label !== 'string'
        || !nonNegativeInteger(floor.count)
        || typeof floor.available !== 'boolean'
        || own(seen, floor.id)) {
        invalidScene();
      }
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
    ]) || payload.schemaVersion !== 2
      || (payload.state !== 'ok' && payload.state !== 'empty' && payload.state !== 'insufficient_sample')) {
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
    validateMetricObject(payload.coverage, ['sourceRows', 'candidate', 'validXY']);
    validateMetricObject(payload.summary, ['rowsRead', 'sourceRows', 'personalSample', 'otherSample']);
    validateWarnings(payload.warnings);
    validateFallback(payload.fallback);

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
    this._layers = {total: total, me: me, others: others};
    this._comparison = comparison;
  }

  HeatmapExplorerScene.prototype.dense = function (layer, channel) {
    var allowedLayer = layer === 'total' || layer === 'me' || layer === 'others' || layer === 'difference';
    var allowedChannel = channel === 'kills' || channel === 'deaths' || (layer !== 'difference' && channel === 'both');
    if (!allowedLayer || !allowedChannel) {
      throw new Error('invalid_dense_selection');
    }

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
    return {values: values, opacity: opacity, maxAbs: maxAbs, occupied: occupied};
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

  function validateUrlValues(values, present) {
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
      if (from >= to || to - from > 315360000) {
        invalidUrl();
      }
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

  function parseUrlState(search) {
    var inspected = inspectSearch(search);
    var values = inspected.known;
    var present = {};
    for (var index = 0; index < URL_KEYS.length; index += 1) {
      present[URL_KEYS[index]] = own(values, URL_KEYS[index]);
    }
    return validateUrlValues(values, present);
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

  function serializeUrlState(search, state) {
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
    var normalized = validateUrlValues(values, present);
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
    this._uniforms = null;
    this._camera = null;
    this._selection = null;
    this._mounted = false;
    this._destroyed = false;
    this._fallback = false;
    this._contextLost = false;
    this._ready = false;
    this._startedAt = 0;
    this._pointer = null;
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
    this._texture = null;
    this._buffer = null;
    this._program = null;
    this._uniforms = null;
  };

  HeatmapGlRenderer.prototype._fallbackToStatic = function () {
    this._fallback = true;
    this._mounted = false;
    this._contextLost = false;
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
    if (!gl || typeof gl.getExtension !== 'function'
      || gl.getExtension('EXT_color_buffer_float') === null
      || typeof gl.createTexture !== 'function' || typeof gl.createBuffer !== 'function'
      || typeof gl.createProgram !== 'function') {
      throw new Error('webgl_unavailable');
    }

    var offsets = [];
    for (var offsetY = -1; offsetY <= 1; offsetY++) {
      for (var offsetX = -1; offsetX <= 1; offsetX++) {
        offsets.push([offsetX, offsetY]);
      }
    }
    this._kernelOffsets = offsets;

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
      + 'uniform vec2 u_gridSize;\n'
      + 'uniform float u_maxAbs;\n'
      + 'uniform int u_palette;\n'
      + 'uniform int u_contours;\n'
      + 'in vec2 v_uv;\n'
      + 'out vec4 outputColor;\n'
      + 'vec3 amberOrange(float amount) { return mix(vec3(0.20, 0.05, 0.01), vec3(1.0, 0.62, 0.05), amount); }\n'
      + 'vec3 cyanBlue(float amount) { return mix(vec3(0.01, 0.10, 0.18), vec3(0.10, 0.85, 1.0), amount); }\n'
      + 'vec3 differenceBlueNeutralAmber(float value) {\n'
      + '  vec3 blue = vec3(0.10, 0.36, 0.95);\n'
      + '  vec3 neutral = vec3(0.94, 0.94, 0.94);\n'
      + '  vec3 amber = vec3(1.0, 0.56, 0.05);\n'
      + '  return value < 0.0 ? mix(neutral, blue, -value) : mix(neutral, amber, value);\n'
      + '}\n'
      + 'void main() {\n'
      + '  vec2 texel = 1.0 / u_gridSize;\n'
      + '  float sum = 0.0;\n'
      + '  for (int offsetY = -1; offsetY <= 1; offsetY++) {\n'
      + '    for (int offsetX = -1; offsetX <= 1; offsetX++) {\n'
      + '      sum += texture(u_density, v_uv + vec2(float(offsetX), float(offsetY)) * texel).r;\n'
      + '    }\n'
      + '  }\n'
      + '  float value = sum / 9.0;\n'
      + '  float amount = clamp(abs(value) / max(u_maxAbs, 0.000001), 0.0, 1.0);\n'
      + '  vec3 color = u_palette == 2 ? differenceBlueNeutralAmber(clamp(value / max(u_maxAbs, 0.000001), -1.0, 1.0))\n'
      + '    : (u_palette == 1 ? cyanBlue(amount) : amberOrange(amount));\n'
      + '  float contour = 0.0;\n'
      + '  if (u_contours == 1) {\n'
      + '    contour = step(0.245, amount) * 0.10 + step(0.495, amount) * 0.10 + step(0.745, amount) * 0.10;\n'
      + '  }\n'
      + '  outputColor = vec4(mix(color, vec3(1.0), contour), amount);\n'
      + '}\n';

    var vertex = this._createShader(gl, gl.VERTEX_SHADER, vertexSource);
    var fragment = this._createShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
    var program = gl.createProgram();
    if (!program) {
      throw new Error('program_unavailable');
    }
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      if (typeof gl.deleteShader === 'function') {
        gl.deleteShader(vertex);
        gl.deleteShader(fragment);
      }
      if (typeof gl.deleteProgram === 'function') {
        gl.deleteProgram(program);
      }
      throw new Error('program_unavailable');
    }
    if (typeof gl.deleteShader === 'function') {
      gl.deleteShader(vertex);
      gl.deleteShader(fragment);
    }

    var buffer = gl.createBuffer();
    var texture = gl.createTexture();
    if (!buffer || !texture) {
      throw new Error('resource_unavailable');
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    this._program = program;
    this._buffer = buffer;
    this._texture = texture;
    this._uniforms = {
      gridSize: gl.getUniformLocation(program, 'u_gridSize'),
      maxAbs: gl.getUniformLocation(program, 'u_maxAbs'),
      palette: gl.getUniformLocation(program, 'u_palette'),
      contours: gl.getUniformLocation(program, 'u_contours'),
      density: gl.getUniformLocation(program, 'u_density')
    };
    this._position = gl.getAttribLocation(program, 'a_position');
    if (this._position < 0) {
      throw new Error('attribute_unavailable');
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
        event = new view.CustomEvent('heatmap-explorer-ready', {detail: {renderMs: duration}});
      } else {
        event = {type: 'heatmap-explorer-ready', detail: {renderMs: duration}};
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
      var dense = this.scene.dense(next.layer, next.channel);
      var upload = dense.values;
      if (next.layer === 'difference') {
        upload = new Float32Array(dense.values.length);
        for (var index = 0; index < upload.length; index += 1) {
          upload[index] = dense.values[index] * dense.opacity[index];
        }
      }
      var gl = this._gl;
      gl.useProgram(this._program);
      gl.bindBuffer(gl.ARRAY_BUFFER, this._buffer);
      gl.enableVertexAttribArray(this._position);
      gl.vertexAttribPointer(this._position, 2, gl.FLOAT, false, 0, 0);
      gl.bindTexture(gl.TEXTURE_2D, this._texture);
      gl.texImage2D(
        gl.TEXTURE_2D, 0, gl.R32F, this.scene.grid.width, this.scene.grid.height,
        0, gl.RED, gl.FLOAT, upload
      );
      if (this._uniforms.gridSize !== null) {
        gl.uniform2f(this._uniforms.gridSize, this.scene.grid.width, this.scene.grid.height);
      }
      if (this._uniforms.maxAbs !== null) {
        gl.uniform1f(this._uniforms.maxAbs, dense.maxAbs);
      }
      if (this._uniforms.palette !== null) {
        gl.uniform1i(this._uniforms.palette, next.layer === 'difference' ? 2 : (next.channel === 'deaths' ? 1 : 0));
      }
      if (this._uniforms.contours !== null) {
        gl.uniform1i(this._uniforms.contours, this.options.contours ? 1 : 0);
      }
      if (this._uniforms.density !== null) {
        gl.uniform1i(this._uniforms.density, 0);
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

  HeatmapGlRenderer.prototype.resize = function () {
    if (!this._mounted || this._destroyed || this._fallback || this._contextLost || !this._nodes || !this._gl) {
      return false;
    }
    try {
      var stage = this._nodes.stage;
      var width = Math.max(1, Math.round(numeric(stage.clientWidth, numeric(this._nodes.canvas.clientWidth, 1))));
      var height = Math.max(1, Math.round(numeric(stage.clientHeight, numeric(this._nodes.canvas.clientHeight, 1))));
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
        self.resize();
      } catch (error) {
        self._fallbackToStatic();
      }
    });
    this._listen(canvas, 'pointerdown', function (event) {
      if (!self._camera || !event) {
        return;
      }
      self._pointer = {x: numeric(event.clientX, 0), y: numeric(event.clientY, 0)};
      if (typeof canvas.setPointerCapture === 'function' && finiteNumber(event.pointerId)) {
        canvas.setPointerCapture(event.pointerId);
      }
    });
    this._listen(canvas, 'pointermove', function (event) {
      if (!self._pointer || !self._camera || !event || typeof self._camera.panBy !== 'function') {
        return;
      }
      var nextX = numeric(event.clientX, self._pointer.x);
      var nextY = numeric(event.clientY, self._pointer.y);
      self._camera.panBy(nextX - self._pointer.x, nextY - self._pointer.y);
      self._pointer = {x: nextX, y: nextY};
      self.setCamera(self._camera);
    });
    this._listen(canvas, 'pointerup', function () {
      self._pointer = null;
    });
    this._listen(target, 'keydown', function (event) {
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
      this._gl = this._nodes.canvas.getContext('webgl2', {alpha: true, antialias: false});
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
    this._pointer = null;
    this._removeListeners();
    this._releaseResources();
    this._gl = null;
  };

  return {
    HeatmapExplorerScene: HeatmapExplorerScene,
    HeatmapExplorerCamera: HeatmapExplorerCamera,
    HeatmapExplorerUrlState: HeatmapExplorerUrlState,
    HeatmapGlRenderer: HeatmapGlRenderer
  };
}));
