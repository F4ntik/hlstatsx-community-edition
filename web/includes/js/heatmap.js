var HeatmapProjection = (function() {
	function normalizeRotation(value) {
		value = isFinite(value) ? Math.round(value) % 4 : 0;
		return value < 0 ? value + 4 : value;
	}

	function rotate(x, y, steps) {
		steps = normalizeRotation(steps);
		if (steps === 1) {
			return {x: -y, y: x};
		}
		if (steps === 2) {
			return {x: -x, y: -y};
		}
		if (steps === 3) {
			return {x: y, y: -x};
		}
		return {x: x, y: y};
	}

	function unrotate(x, y, steps) {
		return rotate(x, y, 4 - normalizeRotation(steps));
	}

	return {
		normalize: normalizeRotation,
		rotate: rotate,
		unrotate: unrotate
	};
}());

if (typeof module !== 'undefined' && module.exports) {
	module.exports.HeatmapProjection = HeatmapProjection;
}

var HeatmapAdminGeometry = (function() {
	function canvasDelta(clientDx, clientDy, rect, canvasWidth, canvasHeight) {
		var width = Math.max(1, Number(rect.width) || 0);
		var height = Math.max(1, Number(rect.height) || 0);
		return [clientDx * canvasWidth / width, clientDy * canvasHeight / height];
	}

	function offsetDelta(clientDx, clientDy, rect, canvasWidth, canvasHeight, projectionScale, rotateSteps) {
		var nativeDelta = canvasDelta(clientDx, clientDy, rect, canvasWidth, canvasHeight);
		var moved = HeatmapProjection.unrotate(
			nativeDelta[0] * projectionScale,
			nativeDelta[1] * projectionScale,
			rotateSteps
		);
		return [moved.x, moved.y];
	}

	return {canvasDelta: canvasDelta, offsetDelta: offsetDelta};
}());

if (typeof module !== 'undefined' && module.exports) {
	module.exports.HeatmapAdminGeometry = HeatmapAdminGeometry;
}

var HeatmapRegistrationReport = {
	parse: function(text) {
		if (typeof text !== 'string' || text.length > 2000000) throw new Error('invalid_report');
		var report = JSON.parse(text), config = report && report.candidate_config;
		var keys = ['xoffset','yoffset','scale','flipx','flipy','rotate','cropx1','cropy1','cropx2','cropy2'];
		if (!config || Object.keys(config).length !== keys.length) throw new Error('invalid_report');
		var result = {};
		keys.forEach(function(key) {
			var value = config[key];
			if (key === 'flipx' || key === 'flipy') {
				if (value !== true && value !== false && value !== 0 && value !== 1) throw new Error('invalid_report');
				result[key] = value ? 1 : 0;
			} else {
				if (typeof value !== 'number' || !isFinite(value) || Math.abs(value) > 8388607
					|| (key !== 'scale' && Math.floor(value) !== value)
					|| (key === 'scale' && (value < 0.1 || value > 64))
					|| (key === 'rotate' && (value < 0 || value > 3))
					|| (key.indexOf('crop') === 0 && value < 0)) throw new Error('invalid_report');
				result[key] = value;
			}
		});
		var size = report.candidate_image === 'served_image' ? report.served_size : report.native_size;
		if (!Array.isArray(size) || size.length !== 2 || !size.every(function(n) { return typeof n === 'number' && Number.isInteger(n) && n > 0 && n <= 16384; })) throw new Error('invalid_report');
		return {config: result, size: size};
	}
};
if (typeof module !== 'undefined' && module.exports) module.exports.HeatmapRegistrationReport = HeatmapRegistrationReport;

var HeatmapLandmarkSolver = (function() {
	function finite(value) {
		return typeof value === 'number' && isFinite(value);
	}

	function median(values) {
		var sorted = values.slice().sort(function(left, right) { return left - right; });
		var middle = Math.floor(sorted.length / 2);
		return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
	}

	function orient(anchor, flipY, rotate) {
		var point = HeatmapProjection.rotate(anchor.worldX, flipY ? -anchor.worldY : anchor.worldY, rotate);
		return {x: point.x, y: point.y};
	}

	function integer(value) {
		return value < 0 ? Math.ceil(value) : Math.floor(value);
	}

	function project(anchor, config) {
		var scale = Number(config.scale);
		var x = Number(anchor.worldX);
		var y = Number(anchor.worldY);
		var rotated;
		if (!finite(scale) || scale <= 0 || !finite(x) || !finite(y)) {
			return {x: NaN, y: NaN};
		}
		if (config.flipX) {
			x *= -1;
		}
		if (config.flipY) {
			y *= -1;
		}
		x = integer((x + Number(config.xoffset || 0)) / scale);
		y = integer((y + Number(config.yoffset || 0)) / scale);
		rotated = HeatmapProjection.rotate(x, y, config.rotate || 0);
		return {x: rotated.x - Number(config.cropX || 0), y: rotated.y - Number(config.cropY || 0)};
	}

	function hasArea(anchors, flipY, rotate) {
		var first;
		var second;
		var third;
		var i;
		for (i = 0; i < anchors.length - 2; i += 1) {
			first = orient(anchors[i], flipY, rotate);
			for (var j = i + 1; j < anchors.length - 1; j += 1) {
				second = orient(anchors[j], flipY, rotate);
				for (var k = j + 1; k < anchors.length; k += 1) {
					third = orient(anchors[k], flipY, rotate);
					if (Math.abs((second.x - first.x) * (third.y - first.y) - (second.y - first.y) * (third.x - first.x)) > 1e-7) {
						return true;
					}
				}
			}
		}
		return false;
	}

	function fit(anchors, flipY, rotate) {
		var worldX = 0;
		var worldY = 0;
		var pixelX = 0;
		var pixelY = 0;
		var count = anchors.length;
		var i;
		var point;
		var numerator = 0;
		var denominator = 0;
		if (!hasArea(anchors, flipY, rotate)) {
			return null;
		}
		for (i = 0; i < count; i += 1) {
			point = orient(anchors[i], flipY, rotate);
			worldX += point.x;
			worldY += point.y;
			pixelX += anchors[i].pixelX;
			pixelY += anchors[i].pixelY;
		}
		worldX /= count;
		worldY /= count;
		pixelX /= count;
		pixelY /= count;
		for (i = 0; i < count; i += 1) {
			point = orient(anchors[i], flipY, rotate);
			numerator += (point.x - worldX) * (anchors[i].pixelX - pixelX) + (point.y - worldY) * (anchors[i].pixelY - pixelY);
			denominator += (point.x - worldX) * (point.x - worldX) + (point.y - worldY) * (point.y - worldY);
		}
		var a = numerator / denominator;
		if (!finite(a) || a <= 0 || denominator <= 1e-12) {
			return null;
		}
		return {a: a, xoffset: pixelX - a * worldX, yoffset: pixelY - a * worldY};
	}

	function residual(anchor, model, flipY, rotate) {
		var point = orient(anchor, flipY, rotate);
		var x = model.a * point.x + model.xoffset - anchor.pixelX;
		var y = model.a * point.y + model.yoffset - anchor.pixelY;
		return Math.sqrt(x * x + y * y);
	}

	function solve(rawAnchors, options) {
		options = options || {};
		var minimumAnchors = Math.max(4, Number(options.minimumAnchors) || 4);
		var tolerance = Math.max(1, Number(options.outlierPixels) || 10);
		var cropX = integer(Number(options.cropX) || 0);
		var cropY = integer(Number(options.cropY) || 0);
		var anchors = [];
		var calibration = [];
		var holdouts = [];
		var best = null;
		var i;
		if (!Array.isArray(rawAnchors)) {
			return {ok: false, reason: 'invalid_landmarks'};
		}
		for (i = 0; i < rawAnchors.length; i += 1) {
			var raw = rawAnchors[i] || {};
			var anchor = {worldX: Number(raw.worldX), worldY: Number(raw.worldY), pixelX: Number(raw.pixelX), pixelY: Number(raw.pixelY), holdout: raw.holdout === true || raw.holdout === 1 || raw.holdout === '1', index: i};
			if (!finite(anchor.worldX) || !finite(anchor.worldY) || !finite(anchor.pixelX) || !finite(anchor.pixelY)) {
				return {ok: false, reason: 'invalid_landmarks'};
			}
			anchors.push(anchor);
			(anchor.holdout ? holdouts : calibration).push(anchor);
		}
		if (calibration.length < minimumAnchors || holdouts.length < 2) {
			return {ok: false, reason: 'landmarks_required'};
		}
		for (var flip = 0; flip < 2; flip += 1) {
			for (var rotate = 0; rotate < 4; rotate += 1) {
				var seedGroups = [calibration];
				for (var omitted = 0; omitted < calibration.length; omitted += 1) {
					seedGroups.push(calibration.filter(function(anchor, index) { return index !== omitted; }));
				}
				var model = null;
				var seedScore = Infinity;
				for (var seedIndex = 0; seedIndex < seedGroups.length; seedIndex += 1) {
					var seedModel = fit(seedGroups[seedIndex], Boolean(flip), rotate);
					if (!seedModel) {
						continue;
					}
					var seedResiduals = calibration.map(function(anchor) { return residual(anchor, seedModel, Boolean(flip), rotate); }).sort(function(left, right) { return left - right; });
					var score = seedResiduals.slice(0, minimumAnchors).reduce(function(sum, value) { return sum + value * value; }, 0);
					if (score < seedScore) {
						seedScore = score;
						model = seedModel;
					}
				}
				if (!model) {
					continue;
				}
				var calibrationResiduals = calibration.map(function(anchor) { return residual(anchor, model, Boolean(flip), rotate); });
				var cutoff = Math.max(tolerance, median(calibrationResiduals) * 3);
				var kept = calibration.filter(function(anchor, index) { return calibrationResiduals[index] <= cutoff; });
				if (kept.length < minimumAnchors || !hasArea(kept, Boolean(flip), rotate)) {
					continue;
				}
				model = fit(kept, Boolean(flip), rotate);
				if (!model) {
					continue;
				}
				var scale = 1 / model.a;
				var unrotatedOffset = HeatmapProjection.unrotate(model.xoffset + cropX, model.yoffset + cropY, rotate);
				var candidate = {xoffset: Math.round(unrotatedOffset.x * scale), yoffset: Math.round(unrotatedOffset.y * scale), scale: scale, flipX: false, flipY: Boolean(flip), rotate: rotate, cropX: cropX, cropY: cropY};
				var allResiduals = anchors.map(function(anchor) {
					var projected = project(anchor, candidate);
					return Math.sqrt(Math.pow(projected.x - anchor.pixelX, 2) + Math.pow(projected.y - anchor.pixelY, 2));
				});
				var calibrationInliers = anchors.filter(function(anchor, index) { return !anchor.holdout && allResiduals[index] <= cutoff; });
				var inliers = anchors.filter(function(anchor, index) { return allResiduals[index] <= cutoff; });
				var holdoutResiduals = holdouts.map(function(anchor) {
					return allResiduals[anchor.index];
				});
				var holdoutRmse = Math.sqrt(holdoutResiduals.reduce(function(sum, value) { return sum + value * value; }, 0) / holdoutResiduals.length);
				var maximumResidual = allResiduals.reduce(function(maximum, value) { return Math.max(maximum, value); }, 0);
				candidate.ok = calibrationInliers.length >= minimumAnchors && holdoutResiduals.every(function(value) { return value <= tolerance; });
				candidate.rmse = holdoutRmse;
				candidate.maximumResidual = maximumResidual;
				candidate.inliers = inliers.map(function(anchor) { return anchor.index; });
				candidate.holdouts = holdouts.map(function(anchor) { return anchor.index; });
				candidate.residuals = allResiduals;
				if (!best || candidate.rmse < best.rmse || (candidate.rmse === best.rmse && candidate.maximumResidual < best.maximumResidual)) {
					best = candidate;
				}
			}
		}
		if (best && !best.ok) {
			best.reason = 'candidate_refused';
		}
		return best || {ok: false, reason: 'candidate_refused'};
	}

	return {solve: solve, project: project};
}());

if (typeof module !== 'undefined' && module.exports) {
	module.exports.HeatmapLandmarkSolver = HeatmapLandmarkSolver;
}

var HeatmapAdminPayload = (function() {
	function build(action, identity, controls, useCurrentControls, configHash, previewToken) {
		var payload = {
			action: action || 'preview',
			game: identity.game,
			map: identity.map
		};
		var name;
		if (useCurrentControls) {
			for (name in controls) {
				if (Object.prototype.hasOwnProperty.call(controls, name)) {
					payload[name] = controls[name];
				}
			}
		}
		if ((payload.action === 'save' || payload.action === 'upload') && /^[a-f0-9]{64}$/i.test(configHash || '')) {
			payload.configHash = configHash;
		}
		if (payload.action === 'save' && /^[a-f0-9]{64}$/i.test(previewToken || '')) {
			payload.previewToken = previewToken;
		}
		return payload;
	}

	return {build: build};
}());

if (typeof module !== 'undefined' && module.exports) {
	module.exports.HeatmapAdminPayload = HeatmapAdminPayload;
}

var heatmapI18n = (typeof window !== 'undefined' && window.HLX_I18N) || {};
function heatmapText(name, fallback) {
	return heatmapI18n[name] || fallback;
}

function heatmapSafeImageUrl(value) {
	if (typeof value !== 'string' || value.length === 0 || value.length > 512 || value.indexOf('..') !== -1) {
		return '';
	}
	if (value.indexOf('heatmap_map.php?') === 0 && /^heatmap_map\.php\?[A-Za-z0-9_=&%.-]+$/.test(value)) {
		return value;
	}
	if (value.indexOf('./hlstatsimg/games/') === 0 && /^\.\/hlstatsimg\/games\/[A-Za-z0-9_./%-]+\.(?:jpg|jpeg|png|gif)(?:\?[A-Za-z0-9_=&%.-]+)?$/i.test(value)) {
		return value;
	}
	return '';
}

function heatmapSafeImageDimension(value, fallback) {
	value = Number(value);
	if (isFinite(value) && value > 0 && value <= 8192 && Math.floor(value) === value) {
		return value;
	}
	fallback = Number(fallback);
	return isFinite(fallback) && fallback > 0 && fallback <= 8192 ? Math.floor(fallback) : 1;
}

window.addEvent('domready', function() {
 
	/**
	 * You can run this code as first code to set default options
	 * SqueezeBox.initialize({ ... });
	 */
 
 
	SqueezeBox.assign($$('a[rel=boxed]'));
	setupInlineHeatmaps();
});

function HeatmapCanvas(canvas) {
	this.canvas = canvas;
	this.ctx = canvas.getContext('2d', {willReadFrequently: true});
	this.points = [];
	this.max = 1;
	this.options = {mode: 'thermal', normalization: 'sqrt', alpha: {min: 0.05, max: 0.82}};
	this.radiusValue = 34;
	this.blurValue = 18;
	this.circle = null;
	this.gradients = {};
}

HeatmapCanvas.prototype.data = function(points, max, options) {
	this.points = points || [];
	this.max = Math.max(1, max || 1);
	this.options = options || this.options;
	return this;
};

HeatmapCanvas.prototype.radius = function(radius, blur) {
	this.radiusValue = radius;
	this.blurValue = blur;
	this.circle = null;
	return this;
};

HeatmapCanvas.prototype._circle = function() {
	if (this.circle) {
		return this.circle;
	}

	var radius = this.radiusValue;
	var blur = this.blurValue;
	var size = radius + blur;
	var circle = document.createElement('canvas');
	var ctx = circle.getContext('2d', {willReadFrequently: true});
	circle.width = circle.height = size * 2;
	ctx.shadowOffsetX = ctx.shadowOffsetY = size * 2;
	ctx.shadowBlur = blur;
	ctx.shadowColor = 'black';
	ctx.beginPath();
	ctx.arc(-size, -size, radius, 0, Math.PI * 2, true);
	ctx.closePath();
	ctx.fill();
	this.circle = circle;
	return circle;
};

HeatmapCanvas.prototype._gradient = function(palette) {
	var key = palette || 'kills';
	var stops;
	if (this.gradients[key]) {
		return this.gradients[key];
	}

	var canvas = document.createElement('canvas');
	var ctx = canvas.getContext('2d', {willReadFrequently: true});
	var gradient;
	var pixels;
	canvas.width = 1;
	canvas.height = 256;
	gradient = ctx.createLinearGradient(0, 0, 0, 256);
	stops = key === 'thermal'
		? [
			[0.00, 'rgba(0, 0, 0, 0)'],
			[0.12, 'rgba(0, 24, 190, 1)'],
			[0.32, 'rgba(0, 210, 255, 1)'],
			[0.55, 'rgba(245, 255, 0, 1)'],
			[0.78, 'rgba(255, 120, 0, 1)'],
			[1.00, 'rgba(255, 20, 0, 1)']
		]
		: key === 'deaths'
		? [
			[0.00, 'rgba(220, 255, 255, 1)'],
			[0.35, 'rgba(0, 220, 255, 1)'],
			[0.70, 'rgba(0, 92, 255, 1)'],
			[1.00, 'rgba(92, 0, 210, 1)']
		]
		: [
			[0.00, 'rgba(255, 255, 180, 1)'],
			[0.35, 'rgba(255, 230, 0, 1)'],
			[0.70, 'rgba(255, 128, 0, 1)'],
			[1.00, 'rgba(255, 32, 0, 1)']
		];
	for (var i = 0; i < stops.length; i++) {
		gradient.addColorStop(stops[i][0], stops[i][1]);
	}
	ctx.fillStyle = gradient;
	ctx.fillRect(0, 0, 1, 256);
	pixels = ctx.getImageData(0, 0, 1, 256).data;
	this.gradients[key] = pixels;
	return pixels;
};

HeatmapCanvas.prototype._normalized = function(value, max) {
	var raw = Math.max(0, value || 0);
	var ceiling = Math.max(1, max || 1);
	var mode = this.options && this.options.normalization ? this.options.normalization : 'sqrt';
	if (mode === 'linear') {
		return Math.min(1, raw / ceiling);
	}
	if (mode === 'log') {
		return Math.log(1 + raw) / Math.log(1 + ceiling);
	}
	return Math.sqrt(raw / ceiling);
};

HeatmapCanvas.prototype._alpha = function(value, max) {
	var alpha = this.options && this.options.alpha ? this.options.alpha : {};
	var min = typeof alpha.min === 'number' ? alpha.min : 0.05;
	var maxAlpha = typeof alpha.max === 'number' ? alpha.max : 0.82;
	return Math.max(0, Math.min(1, min + ((maxAlpha - min) * this._normalized(value, max))));
};

HeatmapCanvas.prototype._drawLayer = function(points, max, palette) {
	var layer = document.createElement('canvas');
	var ctx = layer.getContext('2d', {willReadFrequently: true});
	var circle = this._circle();
	var size = this.radiusValue + this.blurValue;
	var i;
	var point;
	var alpha;
	var image;
	var data;
	var gradient;
	var offset;

	layer.width = this.canvas.width;
	layer.height = this.canvas.height;
	ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
	for (i = 0; i < points.length; i++) {
		point = points[i];
		alpha = this._alpha(point.value || 1, max);
		ctx.globalAlpha = alpha;
		ctx.drawImage(circle, Math.round(point.x - size), Math.round(point.y - size));
	}

	ctx.globalAlpha = 1;
	image = ctx.getImageData(0, 0, layer.width, layer.height);
	data = image.data;
	gradient = this._gradient(palette);

	for (i = 0; i < data.length; i += 4) {
		if (data[i + 3] === 0) {
			continue;
		}
		offset = data[i + 3] * 4;
		data[i] = gradient[offset];
		data[i + 1] = gradient[offset + 1];
		data[i + 2] = gradient[offset + 2];
		data[i + 3] = Math.max(1, data[i + 3]);
	}
	ctx.putImageData(image, 0, 0);

	return layer;
};

HeatmapCanvas.prototype.draw = function() {
	var ctx = this.ctx;
	var killPoints = [];
	var deathPoints = [];
	var maxKill = 0;
	var maxDeath = 0;
	var hasChannels = false;
	var mode = this.options && this.options.mode ? this.options.mode : 'thermal';
	var i;
	var point;

	for (i = 0; i < this.points.length; i++) {
		point = this.points[i];
		if (point.killValue || point.deathValue) {
			hasChannels = true;
		}
		if (point.killValue) {
			killPoints.push({x: point.x, y: point.y, value: point.killValue});
			maxKill = Math.max(maxKill, point.killValue);
		}
		if (point.deathValue) {
			deathPoints.push({x: point.x, y: point.y, value: point.deathValue});
			maxDeath = Math.max(maxDeath, point.deathValue);
		}
	}

	ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
	if (mode === 'semantic' && hasChannels) {
		if (deathPoints.length) {
			ctx.drawImage(this._drawLayer(deathPoints, maxDeath, 'deaths'), 0, 0);
		}
		if (killPoints.length) {
			ctx.globalCompositeOperation = deathPoints.length ? 'screen' : 'source-over';
			ctx.drawImage(this._drawLayer(killPoints, maxKill, 'kills'), 0, 0);
			ctx.globalCompositeOperation = 'source-over';
		}
		return;
	}

	ctx.drawImage(this._drawLayer(this.points, this.max, 'thermal'), 0, 0);
};

HeatmapCanvas.prototype.drawPoints = function(points) {
	var ctx = this.ctx;
	var i;
	var point;
	var x;
	var y;
	var inBounds;
	ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
	for (i = 0; i < points.length; i++) {
		point = points[i];
		x = Number(point[3]);
		y = Number(point[4]);
		inBounds = point[7] === true;
		if (!isFinite(x) || !isFinite(y)) {
			continue;
		}
		ctx.strokeStyle = point[5] === 'deaths' ? '#007cff' : '#ff4d00';
		ctx.fillStyle = ctx.strokeStyle;
		ctx.lineWidth = 1.5;
		if (inBounds) {
			ctx.beginPath();
			ctx.arc(x, y, 3, 0, Math.PI * 2, true);
			ctx.fill();
			ctx.beginPath();
			ctx.moveTo(x - 5, y);
			ctx.lineTo(x + 5, y);
			ctx.moveTo(x, y - 5);
			ctx.lineTo(x, y + 5);
			ctx.stroke();
		} else {
			x = Math.max(3, Math.min(this.canvas.width - 3, x));
			y = Math.max(3, Math.min(this.canvas.height - 3, y));
			ctx.beginPath();
			ctx.moveTo(x - 4, y - 4);
			ctx.lineTo(x + 4, y + 4);
			ctx.moveTo(x + 4, y - 4);
			ctx.lineTo(x - 4, y + 4);
			ctx.stroke();
		}
	}
	return this;
};

function setupInlineHeatmaps() {
	var viewers = document.querySelectorAll('.heatmap-viewer[data-heatmap-endpoint]:not(.heatmap-viewer-admin)');
	var i;

	if (!window.fetch) {
		return;
	}

	for (i = 0; i < viewers.length; i++) {
		if (!viewers[i].getAttribute('data-heatmap-ready')) {
			setupInlineHeatmap(viewers[i]);
		}
	}
	setupPlayerHeatmapControls();
	setupHeatmapAdminWizards();
}

function setupInlineHeatmap(viewer) {
	var endpoint = viewer.getAttribute('data-heatmap-endpoint');
	var image = viewer.querySelector('.heatmap-map-base');
	var canvas = viewer.querySelector('.heatmap-overlay');
	var status = viewer.querySelector('.heatmap-status');
	var toggle = viewer.querySelector('[data-heatmap-toggle]');
	var tooltip = viewer.querySelector('.heatmap-tooltip');
	var renderer = new HeatmapCanvas(canvas);
	var overlayVisible = true;
	var lastPayload = null;
	var hitRadius = 36;
	viewer.setAttribute('data-heatmap-ready', '1');

	function setStatus(text, warning) {
		if (status) {
			status.textContent = text || '';
			status.className = warning ? 'heatmap-status is-warning' : 'heatmap-status';
		}
	}

	function syncCanvasSize(payload) {
		var width = heatmapSafeImageDimension(payload.image && payload.image.width, image.naturalWidth);
		var height = heatmapSafeImageDimension(payload.image && payload.image.height, image.naturalHeight);
		canvas.width = width;
		canvas.height = height;
		renderer.data([], 1, payload.renderer || renderer.options).draw();
		canvas.style.display = overlayVisible ? 'block' : 'none';
	}

	function appendTooltipLine(label, value, strong) {
		var line = document.createElement('div');
		var labelNode;
		var valueNode;
		if (label) {
			labelNode = document.createElement('b');
			labelNode.textContent = String(label) + ':';
			line.appendChild(labelNode);
			line.appendChild(document.createTextNode(' '));
		}
		valueNode = strong ? document.createElement('b') : document.createTextNode('');
		valueNode.textContent = value == null ? '' : String(value);
		line.appendChild(valueNode);
		tooltip.appendChild(line);
	}

	function appendTooltipActors(label, actors) {
		var i;
		var rows = [];
		if (!actors || !actors.length) {
			return;
		}
		for (i = 0; i < Math.min(3, actors.length); i++) {
			rows.push(String(actors[i].name == null ? '' : actors[i].name) + ' (' + String(actors[i].count == null ? 0 : actors[i].count) + ')');
		}
		appendTooltipLine(label, rows.join(', '), false);
	}

	function hideTooltip() {
		if (tooltip) {
			tooltip.style.display = 'none';
		}
	}

	function showTooltip(event) {
		var rect;
		var scaleX;
		var scaleY;
		var x;
		var y;
		var points;
		var nearest = null;
		var nearestDistance = Infinity;
		var i;
		var point;
		var distance;

		if (!tooltip || !lastPayload || !lastPayload.points || !lastPayload.points.length || !overlayVisible) {
			hideTooltip();
			return;
		}

		rect = canvas.getBoundingClientRect();
		scaleX = canvas.width / Math.max(1, rect.width);
		scaleY = canvas.height / Math.max(1, rect.height);
		x = (event.clientX - rect.left) * scaleX;
		y = (event.clientY - rect.top) * scaleY;
		points = lastPayload.points;

		for (i = 0; i < points.length; i++) {
			point = points[i];
			distance = Math.sqrt(Math.pow(point.x - x, 2) + Math.pow(point.y - y, 2));
			if (distance < nearestDistance) {
				nearest = point;
				nearestDistance = distance;
			}
		}

		if (!nearest || nearestDistance > hitRadius * scaleX) {
			hideTooltip();
			return;
		}

		tooltip.textContent = '';
		appendTooltipLine('', String(nearest.value || 0) + ' ' + heatmapText('heatmapEvents', 'events'), true);
		appendTooltipLine(
			heatmapText('kills', 'Kills'),
			String(nearest.killValue || 0) + ' / ' + heatmapText('deaths', 'Deaths') + ': ' + String(nearest.deathValue || 0),
			false
		);
		appendTooltipActors(heatmapText('heatmapKillers', 'Killers'), nearest.topKillers);
		appendTooltipActors(heatmapText('heatmapVictims', 'Victims'), nearest.topVictims);
		appendTooltipActors(heatmapText('players', 'Players'), nearest.topPlayers);
		tooltip.style.left = Math.min(rect.width - 12, Math.max(8, event.clientX - rect.left + 12)) + 'px';
		tooltip.style.top = Math.min(rect.height - 12, Math.max(8, event.clientY - rect.top + 12)) + 'px';
		tooltip.style.display = 'block';
	}

	function render(payload) {
		var side = Math.sqrt(canvas.width * canvas.height);
		var radius = payload.points.length <= 5 ? 46 : Math.max(24, Math.min(54, Math.round(side / 38)));
		lastPayload = payload;
		hitRadius = radius;
		renderer.radius(radius, Math.round(radius * 0.55)).data(payload.points, payload.max, payload.renderer).draw();
		canvas.style.display = overlayVisible ? 'block' : 'none';
		if (payload.diagnostics && payload.diagnostics.queried > 0) {
			var ratio = payload.diagnostics.inBoundsRatio;
			var warning = payload.diagnostics.manualRequired || payload.diagnostics.inBounds === 0 || ratio < 0.3;
			if (payload.diagnostics.outOfBounds > 0 || warning) {
				setStatus(
					payload.diagnostics.inBounds + '/' + payload.diagnostics.queried + ' ' + heatmapText('heatmapInBounds', 'in bounds'),
					warning
				);
			} else {
				setStatus('');
			}
		} else {
			setStatus('');
		}
	}

	if (toggle) {
		toggle.onclick = function() {
			overlayVisible = !overlayVisible;
			canvas.style.display = overlayVisible ? 'block' : 'none';
			toggle.className = overlayVisible ? 'heatmap-toggle is-active' : 'heatmap-toggle';
			hideTooltip();
		};
		toggle.className = 'heatmap-toggle is-active';
	}

	if (canvas) {
		canvas.style.pointerEvents = 'auto';
		canvas.addEventListener('mousemove', showTooltip);
		canvas.addEventListener('mouseleave', hideTooltip);
	}

	function loadHeatmap(nextEndpoint) {
		endpoint = nextEndpoint || viewer.getAttribute('data-heatmap-endpoint');
		hideTooltip();
		setStatus('', false);
		fetch(endpoint, {credentials: 'same-origin'})
		.then(function(response) {
			if (!response.ok) {
				throw new Error(heatmapText('heatmapRequestFailed', 'Heatmap request failed'));
			}
			return response.json();
		})
		.then(function(payload) {
			if (!payload.points || !payload.points.length || !payload.image || !payload.image.url) {
				var warningText = '';
				var warning = false;
				if (payload.diagnostics && payload.diagnostics.queried > 0) {
					warningText = payload.diagnostics.inBounds + '/' + payload.diagnostics.queried + ' ' + heatmapText('heatmapInBounds', 'in bounds');
					warning = true;
				}
				lastPayload = payload;
				if (payload.image && payload.image.url && heatmapSafeImageUrl(payload.image.url)) {
					image.onload = function() {
						syncCanvasSize(payload);
						renderer.data([], 1, payload.renderer || renderer.options).draw();
						setStatus(warningText || '0', warning);
					};
					image.src = heatmapSafeImageUrl(payload.image.url);
					if (image.complete) {
						syncCanvasSize(payload);
						renderer.data([], 1, payload.renderer || renderer.options).draw();
						setStatus(warningText || '0', warning);
					}
				} else {
					setStatus(warningText || '0', warning);
				}
				return;
			}
			image.onload = function() {
				syncCanvasSize(payload);
				render(payload);
			};
			image.src = heatmapSafeImageUrl(payload.image.url);
			if (image.complete) {
				syncCanvasSize(payload);
				render(payload);
			}
		})
		.catch(function() {
			setStatus('');
		});
	}

	viewer.heatmapReload = loadHeatmap;
	loadHeatmap(endpoint);
}

function setupPlayerHeatmapControls() {
	var panels = document.querySelectorAll('.heatmap-player-panel[data-heatmap-player]');
	var i;

	for (i = 0; i < panels.length; i++) {
		setupPlayerHeatmapControl(panels[i]);
	}
}

function setupPlayerHeatmapControl(panel) {
	var viewer = panel.querySelector('.heatmap-viewer[data-heatmap-endpoint]');
	var mapSelect = panel.querySelector('[data-heatmap-map-select]');
	var buttons = panel.querySelectorAll('[data-heatmap-event]');
	var game = panel.getAttribute('data-heatmap-game');
	var player = panel.getAttribute('data-heatmap-player');
	var eventMode = panel.getAttribute('data-heatmap-current-event') || 'kills';
	var i;

	function endpointFor(mapName, eventName) {
		return 'heatmap_points.php?game=' + encodeURIComponent(game) +
			'&map=' + encodeURIComponent(mapName) +
			'&player=' + encodeURIComponent(player) +
			'&event=' + encodeURIComponent(eventName) +
			'&renderer=' + encodeURIComponent(eventName === 'both' ? 'semantic' : 'thermal');
	}

	function activateButtons() {
		var j;
		for (j = 0; j < buttons.length; j++) {
			buttons[j].className = buttons[j].getAttribute('data-heatmap-event') === eventMode
				? 'heatmap-mode is-active'
				: 'heatmap-mode';
		}
	}

	function reload() {
		var mapName = mapSelect ? mapSelect.value : panel.getAttribute('data-heatmap-map');
		var endpoint = endpointFor(mapName, eventMode);
		viewer.setAttribute('data-heatmap-endpoint', endpoint);
		if (viewer.heatmapReload) {
			viewer.heatmapReload(endpoint);
		}
		activateButtons();
	}

	if (!viewer) {
		return;
	}

	if (mapSelect) {
		mapSelect.onchange = reload;
	}
	for (i = 0; i < buttons.length; i++) {
		buttons[i].onclick = function() {
			eventMode = this.getAttribute('data-heatmap-event') || 'kills';
			reload();
		};
	}
	activateButtons();
}

function setupHeatmapAdminWizards() {
	var wizards = document.querySelectorAll('.heatmap-admin-wizard[data-heatmap-admin]');
	var i;
	for (i = 0; i < wizards.length; i++) {
		if (!wizards[i].getAttribute('data-heatmap-admin-ready')) {
			setupHeatmapAdminWizard(wizards[i]);
		}
	}
}

function setupHeatmapAdminWizard(wizard) {
	var viewer = wizard.querySelector('.heatmap-viewer');
	var image = wizard.querySelector('.heatmap-map-base');
	var canvas = wizard.querySelector('.heatmap-overlay');
	var status = wizard.querySelector('.heatmap-status');
	var renderer = new HeatmapCanvas(canvas);
	var mapSelect = wizard.querySelector('[data-heatmap-admin-map]');
	var newMap = wizard.querySelector('[data-heatmap-admin-new-map]');
	var log = wizard.querySelector('[data-heatmap-admin-log]');
	var mapImage = wizard.querySelector('[data-heatmap-map-image]');
	var overviewFile = wizard.querySelector('[data-heatmap-overview-file]');
	var overviewText = wizard.querySelector('[data-heatmap-overview]');
	var floorSelect = wizard.querySelector('[data-heatmap-admin-floor]');
	var eventSelect = wizard.querySelector('[data-heatmap-admin-event]');
	var floorRows = wizard.querySelector('[data-heatmap-floor-rows]');
	var diagnosticFrom = wizard.querySelector('[data-heatmap-diagnostic-from]');
	var diagnosticTo = wizard.querySelector('[data-heatmap-diagnostic-to]');
	var diagnosticCounts = wizard.querySelector('[data-heatmap-diagnostic-counts]');
	var zHistogram = wizard.querySelector('[data-heatmap-z-histogram]');
	var floorSuggestButton = wizard.querySelector('[data-heatmap-floor-suggest]');
	var csrfToken = wizard.getAttribute('data-heatmap-csrf') || '';
	var adminLanguage = wizard.getAttribute('data-heatmap-lang') === 'ru' ? 'ru' : 'en';
	var toggle = wizard.querySelector('[data-heatmap-toggle]');
	var overlayVisible = true;
	var lastPayload = null;
	var previewTimer = null;
	var requestSeq = 0;
	var dragState = null;
	var resizeState = null;
	var guides = null;
	var layerGuide = null;
	var transformToolbar = null;
	var originMarker = null;
	var cropGuide = null;
	var lastGuideRadius = 24;
	var currentConfigHash = '';
	var currentPreviewToken = '';
	var landmarkResult = null;
	var landmarkRows = wizard.querySelector('[data-heatmap-landmark-rows]');
	var landmarkTolerance = wizard.querySelector('[data-heatmap-landmark-tolerance]');
	var landmarkStatus = wizard.querySelector('[data-heatmap-landmark-status]');
	var landmarkApply = wizard.querySelector('[data-heatmap-landmark-apply]');
	var saveButton = wizard.querySelector('[data-heatmap-admin-save]');
	var appliedCandidateKey = '';
	var serverRegistration = null;
	var suggestedFloors = [];
	var drawingFloor = null, drawingPoints = [], drawingKind = 'regions', pickingLandmark = null, geometryOverlay = null;
	var geometryKey = '', geometryGeneration = 0, geometryVisible = false, geometryManifest;
	var geometryToggle = wizard.querySelector('[data-heatmap-clear-geometry]');
	var geometryStatus = wizard.querySelector('[data-heatmap-geometry-status]');
	var settingsOnly = false, editorToolbar, editorHint, contourList;
	var currentConfig = {
		xoffset: 0,
		yoffset: 0,
		scale: 1,
		flipx: 0,
		flipy: 1,
		rotate: 0,
		cropx1: 0,
		cropy1: 0,
		cropx2: 0,
		cropy2: 0,
		renderer: 'thermal',
		normalization: 'sqrt'
	};
	wizard.setAttribute('data-heatmap-admin-ready', '1');

	function setLog(text) {
		if (log) {
			log.textContent = text || '';
		}
	}

	function readLandmarks() {
		var rows = landmarkRows ? landmarkRows.querySelectorAll('[data-heatmap-landmark-row]') : [];
		var landmarks = [];
		for (var rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
			var row = rows[rowIndex];
			var worldX = row.querySelector('[data-heatmap-landmark="worldX"]');
			var worldY = row.querySelector('[data-heatmap-landmark="worldY"]');
			var pixelX = row.querySelector('[data-heatmap-landmark="pixelX"]');
			var pixelY = row.querySelector('[data-heatmap-landmark="pixelY"]');
			var holdout = row.querySelector('[data-heatmap-landmark="holdout"]');
			if (!worldX || !worldY || !pixelX || !pixelY || (worldX.value === '' && worldY.value === '' && pixelX.value === '' && pixelY.value === '')) {
				continue;
			}
			landmarks.push({label: (row.querySelector('[data-heatmap-landmark="label"]') || {}).value || '', worldX: worldX.value === '' ? NaN : Number(worldX.value), worldY: worldY.value === '' ? NaN : Number(worldY.value), pixelX: pixelX.value === '' ? NaN : Number(pixelX.value), pixelY: pixelY.value === '' ? NaN : Number(pixelY.value), holdout: Boolean(holdout && holdout.checked)});
		}
		return landmarks;
	}

	function evaluateLandmarks() {
		return HeatmapLandmarkSolver.solve(readLandmarks(), {
			minimumAnchors: 4,
			outlierPixels: landmarkTolerance ? Number(landmarkTolerance.value) : 10,
			cropX: intConfig('cropx2') > 0 && intConfig('cropy2') > 0 ? intConfig('cropx1') : 0,
			cropY: intConfig('cropx2') > 0 && intConfig('cropy2') > 0 ? intConfig('cropy1') : 0
		});
	}

	function candidateKey(candidate) {
		if (!candidate) {
			return '';
		}
		return [candidate.xoffset, candidate.yoffset, Number(candidate.scale).toPrecision(12), candidate.flipX ? 1 : 0, candidate.flipY ? 1 : 0, candidate.rotate, candidate.cropX, candidate.cropY].join('|');
	}

	function currentCandidateKey() {
		return candidateKey({
			xoffset: intConfig('xoffset'), yoffset: intConfig('yoffset'), scale: scaleConfig(),
			flipX: boolConfig('flipx'), flipY: boolConfig('flipy'), rotate: rotationSteps(),
			cropX: intConfig('cropx2') > 0 && intConfig('cropy2') > 0 ? intConfig('cropx1') : 0,
			cropY: intConfig('cropx2') > 0 && intConfig('cropy2') > 0 ? intConfig('cropy1') : 0
		});
	}

	function candidateIsApplied() {
		return landmarkResult && landmarkResult.ok && appliedCandidateKey !== '' && appliedCandidateKey === candidateKey(landmarkResult) && appliedCandidateKey === currentCandidateKey();
	}

	function renderLandmarkResiduals(registration) {
		var rows = landmarkRows ? landmarkRows.querySelectorAll('[data-heatmap-landmark-row]') : [];
		var residuals = registration && Array.isArray(registration.residuals) ? registration.residuals : [];
		for (var index = 0; index < rows.length; index += 1) {
			var cell = rows[index].querySelector('[data-heatmap-landmark-residual]');
			var residual = residuals[index] && Number(residuals[index].residual);
			if (cell) {
				cell.textContent = isFinite(residual) ? residual.toFixed(2) + ' px' : '—';
				cell.setAttribute('data-accepted', isFinite(residual) && residual <= Number((registration || {}).tolerance || 0) ? '1' : '0');
			}
		}
	}

	function syncSaveGate() {
		var accepted = (settingsOnly || candidateIsApplied() && serverRegistration && serverRegistration.ok === true) && /^[a-f0-9]{64}$/i.test(currentPreviewToken) && !drawingFloor;
		if (saveButton) {
			saveButton.disabled = !accepted;
		}
		if (landmarkStatus) {
			landmarkStatus.textContent = settingsOnly ? (adminLanguage === 'ru' ? 'Привязка карты не менялась. Этажи и стены можно сохранить без повторного ввода ориентиров.' : 'Map alignment is unchanged. Floors and walls can be saved without re-entering landmarks.') : accepted
				? adminText('registration-accepted', 'Landmark registration accepted.') + ' ' + adminText('registration-coverage', 'Registration is separate from coverage.')
				: (!candidateIsApplied() && landmarkResult && landmarkResult.ok
					? (landmarkApply ? landmarkApply.textContent : 'Apply landmark candidate')
					: (landmarkResult && landmarkResult.reason === 'candidate_refused'
					? adminText('candidate-refused', 'The landmark residuals do not fit one uniform projection.')
					: adminText('landmarks-required', 'Add four landmarks and two holdouts, then preview.')));
		}
	}

	function invalidatePreviewToken() {
		currentPreviewToken = '';
		serverRegistration = null;
		landmarkResult = evaluateLandmarks();
		syncSaveGate();
	}

	function adminText(name, fallback) {
		var value = wizard.getAttribute('data-heatmap-admin-text-' + name);
		return value || fallback;
	}

	function isConfigHash(value) {
		return typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value);
	}

	function clearChildren(element) {
		if (element) {
			element.textContent = '';
		}
	}

	function dateTimeValue(date) {
		function pad(value) {
			return String(value).length < 2 ? '0' + String(value) : String(value);
		}
		return date.getUTCFullYear() + '-' + pad(date.getUTCMonth() + 1) + '-' + pad(date.getUTCDate())
			+ 'T' + pad(date.getUTCHours()) + ':' + pad(date.getUTCMinutes());
	}

	function diagnosticSeconds(field) {
		var value = field ? field.value : '';
		var milliseconds;
		if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
			return null;
		}
		milliseconds = Date.parse(value + ':00Z');
		return isFinite(milliseconds) ? Math.floor(milliseconds / 1000) : null;
	}

	function seedDiagnosticWindow() {
		var to;
		var from;
		if (!diagnosticFrom || !diagnosticTo || (diagnosticFrom.value && diagnosticTo.value)) {
			return;
		}
		to = new Date();
		from = new Date(to.getTime() - 30 * 86400000);
		diagnosticFrom.value = dateTimeValue(from);
		diagnosticTo.value = dateTimeValue(to);
	}

	function createFloorCell(row, name, value, type) {
		var cell = document.createElement('td');
		var input = document.createElement('input');
		input.type = type || 'text';
		input.value = value == null ? '' : String(value);
		input.setAttribute('data-heatmap-floor-field', name);
		var names = {id: ['Код', 'ID'], label_en: ['Название EN', 'Name EN'], label_ru: ['Название RU', 'Name RU'], z_min: ['Высота от', 'Height from'], z_max: ['Высота до', 'Height to']};
		cell.setAttribute('data-label', names[name][adminLanguage === 'ru' ? 0 : 1]);
		input.setAttribute('aria-label', cell.getAttribute('data-label'));
		if (name === 'id') {
			input.maxLength = 32;
		}
		if (name === 'label_en' || name === 'label_ru') {
			input.maxLength = 64;
		}
		if (type === 'number') {
			input.step = '1';
		}
		cell.appendChild(input);
		row.appendChild(cell);
	}

	function addFloorRow(floor) {
		var row;
		var removeCell;
		var removeButton;
		if (!floorRows || floorRows.children.length >= 8) {
			return;
		}
		floor = floor || {};
		row = document.createElement('tr');
		row._regions = floor.regions || [];
		row._blocked = floor.blocked || [];
		row._floorImage = floor.image === true;
		createFloorCell(row, 'id', floor.id || '', 'text');
		createFloorCell(row, 'label_en', floor.label_en || '', 'text');
		createFloorCell(row, 'label_ru', floor.label_ru || '', 'text');
		createFloorCell(row, 'z_min', floor.z_min == null ? 0 : floor.z_min, 'number');
		createFloorCell(row, 'z_max', floor.z_max == null ? 1 : floor.z_max, 'number');
		removeCell = document.createElement('td');
		removeButton = document.createElement('button');
		removeButton.type = 'button';
		removeButton.textContent = '×';
		removeButton.title = adminText('remove-floor', 'Remove floor');
		removeButton.onclick = function() {
			if (drawingFloor === row) { drawingFloor = null; drawingPoints = []; }
			floorRows.removeChild(row);
			schedulePreview();
		};
		removeCell.appendChild(removeButton);
		row.appendChild(removeCell);
		var regionCell = document.createElement('td'); regionCell.className = 'heatmap-floor-card-actions';
		var edit = editorButton(adminLanguage === 'ru' ? 'Редактировать на карте' : 'Edit on map', function() {
			cancelDrawing(); renderFloorSelect(readFloors()); floorSelect.value = row.querySelector('[data-heatmap-floor-field="id"]').value;
			schedulePreview(); refreshEditor(); viewer.scrollIntoView({block:'start', behavior:'smooth'});
		});
		var imageLabel = document.createElement('label'), floorImage = document.createElement('input');
		floorImage.type = 'checkbox'; floorImage.checked = row._floorImage;
		floorImage.onchange = function() { row._floorImage = floorImage.checked; schedulePreview(); };
		imageLabel.appendChild(floorImage); imageLabel.appendChild(document.createTextNode(adminLanguage === 'ru' ? 'Отдельная картинка' : 'Separate image'));
		var file = document.createElement('input'); file.type = 'file'; file.accept = 'image/jpeg'; file.setAttribute('aria-label', adminLanguage === 'ru' ? 'Картинка этажа JPEG' : 'Floor image JPEG');
		file.onchange = function() { if (file.files[0]) uploadFloorImage(row, file); };
		regionCell.appendChild(edit); regionCell.appendChild(imageLabel); regionCell.appendChild(file); row.appendChild(regionCell);
		floorRows.appendChild(row);
		var fields = row.querySelectorAll('[data-heatmap-floor-field]');
		for (var fieldIndex = 0; fieldIndex < fields.length; fieldIndex += 1) {
			fields[fieldIndex].oninput = schedulePreview;
			fields[fieldIndex].onchange = schedulePreview;
		}
	}

	function readFloors() {
		var rows = floorRows ? floorRows.querySelectorAll('tr') : [];
		var floors = [];
		var index;
		var fields;
		var floor;
		for (index = 0; index < rows.length; index++) {
			fields = rows[index].querySelectorAll('[data-heatmap-floor-field]');
			if (fields.length !== 5) {
				continue;
			}
			floor = {};
			for (var fieldIndex = 0; fieldIndex < fields.length; fieldIndex++) {
				var fieldName = fields[fieldIndex].getAttribute('data-heatmap-floor-field');
				floor[fieldName] = fieldName === 'z_min' || fieldName === 'z_max'
					? Number(fields[fieldIndex].value)
					: fields[fieldIndex].value;
			}
			floors.push(floor);
			if (rows[index]._regions && rows[index]._regions.length) floor.regions = rows[index]._regions;
			if (rows[index]._blocked && rows[index]._blocked.length) floor.blocked = rows[index]._blocked;
			if (rows[index]._floorImage) floor.image = true;
		}
		return floors;
	}

	function renderFloors(floors) {
		var index;
		clearChildren(floorRows);
		for (index = 0; Array.isArray(floors) && index < floors.length && index < 8; index++) {
			addFloorRow(floors[index]);
		}
	}

	function renderFloorSelect(floors) {
		var selected = floorSelect ? floorSelect.value : 'all';
		var index;
		var option;
		if (!floorSelect) {
			return;
		}
		clearChildren(floorSelect);
		option = document.createElement('option');
		option.value = 'all';
		option.textContent = adminText('all-floors', 'All floors');
		floorSelect.appendChild(option);
		for (index = 0; Array.isArray(floors) && index < floors.length; index++) {
			if (!floors[index] || typeof floors[index].id !== 'string') {
				continue;
			}
			option = document.createElement('option');
			option.value = floors[index].id;
			option.textContent = adminLanguage === 'ru' ? floors[index].label_ru : floors[index].label_en;
			floorSelect.appendChild(option);
		}
		floorSelect.value = selected;
		if (floorSelect.value !== selected) {
			floorSelect.value = 'all';
		}
	}

	function renderDiagnostics(payload) {
		var diagnostics = payload && payload.diagnostics ? payload.diagnostics : {};
		var histogram = diagnostics.zHistogram;
		var index;
		var row;
		var item;
		if (diagnosticCounts) {
			diagnosticCounts.textContent = (adminLanguage === 'ru' ? 'Событий: ' : 'Events: ') + Number(diagnostics.sourceRows || 0)
				+ (adminLanguage === 'ru' ? '; позиций: ' : '; positions: ') + Number(diagnostics.candidate || 0)
				+ (adminLanguage === 'ru' ? '; с высотой: ' : '; with height: ') + Number(diagnostics.validZ || 0)
				+ (adminLanguage === 'ru' ? '; на этажах: ' : '; assigned to floors: ') + Number(diagnostics.assigned || 0);
		}
		clearChildren(zHistogram);
		for (index = 0; zHistogram && Array.isArray(histogram) && index < histogram.length; index++) {
			row = histogram[index];
			if (!row || !isFinite(Number(row.z)) || !isFinite(Number(row.count))) {
				continue;
			}
			item = document.createElement('li');
			item.textContent = String(Math.round(Number(row.z))) + '…' + String(Math.round(Number(row.z)) + 31) + ': ' + String(Math.max(0, Math.round(Number(row.count))));
			zHistogram.appendChild(item);
		}
		suggestedFloors = Array.isArray(payload && payload.suggestedFloors) ? payload.suggestedFloors : [];
		if (floorSuggestButton) {
			floorSuggestButton.disabled = suggestedFloors.length === 0;
		}
	}

	function clamp(value, min, max) {
		value = Number(value);
		if (!isFinite(value)) {
			value = min;
		}
		return Math.max(min, Math.min(max, value));
	}

	function scaleToSlider(scale) {
		return Math.round(Math.log(clamp(scale, 0.1, 64)) / Math.log(2) * 100);
	}

	function sliderToScale(value) {
		return clamp(Math.pow(2, Number(value) / 100), 0.1, 64).toFixed(2);
	}

	function intConfig(name) {
		var field = wizard.querySelector('[data-heatmap-number="' + name + '"]');
		return field ? parseInt(field.value || 0, 10) || 0 : parseInt(currentConfig[name] || 0, 10) || 0;
	}

	function scaleConfig() {
		var field = wizard.querySelector('[data-heatmap-number="scale"]');
		return clamp(field ? field.value : currentConfig.scale, 0.1, 64);
	}

	function boolConfig(name) {
		var field = wizard.querySelector('[data-heatmap-check="' + name + '"]');
		return field ? field.checked : Boolean(Number(currentConfig[name] || 0));
	}

	function rotationSteps() {
		var field = wizard.querySelector('[data-heatmap-number="rotate"]');
		var value = field ? Number(field.value || 0) : Number(currentConfig.rotate || 0);
		return normalizeRotation(value);
	}

	function normalizeRotation(value) {
		return HeatmapProjection.normalize(value);
	}

	function rotateCoordinate(x, y, steps) {
		return HeatmapProjection.rotate(x, y, steps);
	}

	function unrotateCoordinate(x, y, steps) {
		return HeatmapProjection.unrotate(x, y, steps);
	}

	function setNumberField(name, value) {
		var number = wizard.querySelector('[data-heatmap-number="' + name + '"]');
		var range = wizard.querySelector('[data-heatmap-field="' + name + '"]');
		if (number) {
			number.value = name === 'scale' ? String(Number(clamp(value, 0.1, 64).toFixed(8))) : Math.round(value);
		}
		if (range) {
			range.value = range.getAttribute('data-heatmap-scale-slider') ? scaleToSlider(value) : Math.round(value);
		}
		currentConfig[name] = name === 'scale' ? clamp(value, 0.1, 64) : Math.round(value);
	}

	function syncTransformButtons() {
		var buttons = wizard.querySelectorAll('[data-heatmap-toggle-check]');
		var rotateButtons = wizard.querySelectorAll('.heatmap-transform-button[data-heatmap-rotate-step]');
		var i;
		var name;
		var check;
		for (i = 0; i < buttons.length; i++) {
			name = buttons[i].getAttribute('data-heatmap-toggle-check');
			check = wizard.querySelector('[data-heatmap-check="' + name + '"]');
			buttons[i].className = check && check.checked ? 'heatmap-transform-button is-active' : 'heatmap-transform-button';
		}
		for (i = 0; i < rotateButtons.length; i++) {
			rotateButtons[i].className = rotationSteps() ? 'heatmap-transform-button is-active' : 'heatmap-transform-button';
			rotateButtons[i].textContent = heatmapText('heatmapRotate', 'Rotate') + ' ' + (rotationSteps() ? (rotationSteps() * 90) : 90) + '°';
		}
	}

	function toggleTransform(name) {
		var check = wizard.querySelector('[data-heatmap-check="' + name + '"]');
		if (check) {
			check.checked = !check.checked;
			syncTransformButtons();
			schedulePreview();
		}
	}

	function rotateLayer(step) {
		var field = wizard.querySelector('[data-heatmap-number="rotate"]');
		var previous = rotationSteps();
		var stepValue = Number(step);
		var next = normalizeRotation(previous + (isFinite(stepValue) && stepValue !== 0 ? stepValue : 1));
		var bounds = layerBounds();
		var scale = scaleConfig();
		var cropX = intConfig('cropx2') > 0 && intConfig('cropy2') > 0 ? intConfig('cropx1') : 0;
		var cropY = intConfig('cropx2') > 0 && intConfig('cropy2') > 0 ? intConfig('cropy1') : 0;
		var center;
		var previousCenter;
		var nextCenter;
		if (bounds) {
			center = {
				x: bounds.left + bounds.width / 2 + cropX,
				y: bounds.top + bounds.height / 2 + cropY
			};
			previousCenter = unrotateCoordinate(center.x, center.y, previous);
			nextCenter = unrotateCoordinate(center.x, center.y, next);
			setNumberField('xoffset', intConfig('xoffset') + (nextCenter.x - previousCenter.x) * scale);
			setNumberField('yoffset', intConfig('yoffset') + (nextCenter.y - previousCenter.y) * scale);
		}
		if (field) {
			field.value = next;
		}
		currentConfig.rotate = next;
		syncTransformButtons();
		schedulePreview();
	}

	function projectedOrigin() {
		var x = intConfig('xoffset') / scaleConfig();
		var y = intConfig('yoffset') / scaleConfig();
		var rotated = rotateCoordinate(x, y, rotationSteps());
		x = rotated.x;
		y = rotated.y;
		if (intConfig('cropx2') > 0 && intConfig('cropy2') > 0) {
			x -= intConfig('cropx1');
			y -= intConfig('cropy1');
		}
		return {x: x, y: y};
	}

	function ensureGuides() {
		var wrap = viewer ? viewer.querySelector('.heatmap-canvas-wrap') : null;
		var stage = wrap ? (wrap.querySelector('.heatmap-map-stage') || wrap) : null;
		if (!stage || guides) {
			return;
		}
		guides = document.createElement('div');
		guides.className = 'heatmap-admin-guides';
		layerGuide = document.createElement('div');
		layerGuide.className = 'heatmap-layer-guide';
		var resizeNames = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
		var handle;
		var rotateControls = document.createElement('span');
		var rotateLeft = document.createElement('button');
		var rotateRight = document.createElement('button');
		for (var handleIndex = 0; handleIndex < resizeNames.length; handleIndex++) {
			handle = document.createElement('span');
			handle.className = 'heatmap-layer-handle heatmap-layer-handle-' + resizeNames[handleIndex];
			handle.setAttribute('data-heatmap-resize', resizeNames[handleIndex]);
			layerGuide.appendChild(handle);
		}
		rotateControls.className = 'heatmap-layer-rotate-controls';
		rotateLeft.type = 'button';
		rotateLeft.className = 'heatmap-layer-rotate-button';
		rotateLeft.setAttribute('data-heatmap-rotate-step', '-1');
		rotateLeft.title = heatmapText('heatmapRotateLeft90', 'Rotate left 90 degrees');
		rotateLeft.textContent = '↺';
		rotateRight.type = 'button';
		rotateRight.className = 'heatmap-layer-rotate-button';
		rotateRight.setAttribute('data-heatmap-rotate-step', '1');
		rotateRight.title = heatmapText('heatmapRotateRight90', 'Rotate right 90 degrees');
		rotateRight.textContent = '↻';
		rotateControls.appendChild(rotateLeft);
		rotateControls.appendChild(rotateRight);
		layerGuide.appendChild(rotateControls);
		var frameRotateButtons = rotateControls.querySelectorAll('.heatmap-layer-rotate-button');
		for (var rb = 0; rb < frameRotateButtons.length; rb++) {
			frameRotateButtons[rb].onclick = function(event) {
				rotateLayer(this.getAttribute('data-heatmap-rotate-step'));
				if (event.preventDefault) {
					event.preventDefault();
				}
				if (event.stopPropagation) {
					event.stopPropagation();
				}
			};
		}
		transformToolbar = document.createElement('div');
		transformToolbar.className = 'heatmap-transform-overlay';
		var flipXButton = document.createElement('button');
		var flipYButton = document.createElement('button');
		var toolbarRotateButton = document.createElement('button');
		flipXButton.type = 'button';
		flipXButton.className = 'heatmap-transform-button';
		flipXButton.setAttribute('data-heatmap-toggle-check', 'flipx');
		flipXButton.textContent = heatmapText('heatmapFlipX', 'Flip X');
		flipYButton.type = 'button';
		flipYButton.className = 'heatmap-transform-button';
		flipYButton.setAttribute('data-heatmap-toggle-check', 'flipy');
		flipYButton.textContent = heatmapText('heatmapFlipY', 'Flip Y');
		toolbarRotateButton.type = 'button';
		toolbarRotateButton.className = 'heatmap-transform-button';
		toolbarRotateButton.setAttribute('data-heatmap-rotate-step', '1');
		toolbarRotateButton.textContent = heatmapText('heatmapRotate', 'Rotate') + ' 90°';
		transformToolbar.appendChild(flipXButton);
		transformToolbar.appendChild(flipYButton);
		transformToolbar.appendChild(toolbarRotateButton);
		originMarker = document.createElement('div');
		originMarker.className = 'heatmap-origin-marker';
		cropGuide = document.createElement('div');
		cropGuide.className = 'heatmap-crop-guide';
		transformToolbar.onclick = function(event) {
			var target = event.target || event.srcElement;
			var name = target ? target.getAttribute('data-heatmap-toggle-check') : '';
			if (name) {
				toggleTransform(name);
				if (event.preventDefault) {
					event.preventDefault();
				}
				if (event.stopPropagation) {
					event.stopPropagation();
				}
				return;
			}
			if (target && target.getAttribute('data-heatmap-rotate-step')) {
				rotateLayer(target.getAttribute('data-heatmap-rotate-step'));
				if (event.preventDefault) {
					event.preventDefault();
				}
				if (event.stopPropagation) {
					event.stopPropagation();
				}
			}
		};
		layerGuide.onclick = function(event) {
			var target = event.target || event.srcElement;
			if (target && target.getAttribute('data-heatmap-rotate-step')) {
				rotateLayer(target.getAttribute('data-heatmap-rotate-step'));
				if (event.preventDefault) {
					event.preventDefault();
				}
				if (event.stopPropagation) {
					event.stopPropagation();
				}
				return;
			}
		};
		layerGuide.onmousedown = function(event) {
			var target = event.target || event.srcElement;
			var handle = target ? target.getAttribute('data-heatmap-resize') : '';
			if (target && target.getAttribute('data-heatmap-rotate-step')) {
				if (event.preventDefault) {
					event.preventDefault();
				}
				if (event.stopPropagation) {
					event.stopPropagation();
				}
				return;
			}
			if (handle) {
				beginResize(event, handle);
			}
		};
		document.addEventListener('mousemove', resizeMove);
		document.addEventListener('mouseup', endResize);
		guides.appendChild(layerGuide);
		guides.appendChild(transformToolbar);
		guides.appendChild(cropGuide);
		guides.appendChild(originMarker);
		stage.appendChild(guides);
		syncTransformButtons();
	}

	function layerBounds() {
		var points = lastPayload && lastPayload.points ? lastPayload.points : [];
		var transformed = lastPayload && lastPayload.diagnostics ? lastPayload.diagnostics.transformed : null;
		var width = canvas.width || 0;
		var height = canvas.height || 0;
		var radius = Math.max(8, lastGuideRadius || 0);
		var minX = Infinity;
		var minY = Infinity;
		var maxX = -Infinity;
		var maxY = -Infinity;
		var i;
		var point;
		var fromDiagnostics = transformed &&
			typeof transformed.minX === 'number' &&
			typeof transformed.maxX === 'number' &&
			typeof transformed.minY === 'number' &&
			typeof transformed.maxY === 'number';

		if (fromDiagnostics) {
			minX = transformed.minX - radius;
			minY = transformed.minY - radius;
			maxX = transformed.maxX + radius;
			maxY = transformed.maxY + radius;
		} else {
			for (i = 0; i < points.length; i++) {
				point = points[i];
				if (typeof point.x !== 'number' || typeof point.y !== 'number') {
					continue;
				}
				minX = Math.min(minX, point.x - radius);
				minY = Math.min(minY, point.y - radius);
				maxX = Math.max(maxX, point.x + radius);
				maxY = Math.max(maxY, point.y + radius);
			}
		}
		if (!isFinite(minX) || !isFinite(minY) || !isFinite(maxX) || !isFinite(maxY)) {
			return null;
		}
		return {
			left: minX,
			top: minY,
			right: Math.max(minX + 1, maxX),
			bottom: Math.max(minY + 1, maxY),
			width: Math.max(1, maxX - minX),
			height: Math.max(1, maxY - minY),
			empty: points.length === 0
		};
	}

	function setLayerGuideBounds(bounds) {
		var width = Math.max(1, canvas.width || 0);
		var height = Math.max(1, canvas.height || 0);
		var rotateControls;
		var visibleRotateX;
		layerGuide.style.left = (bounds.left / width * 100) + '%';
		layerGuide.style.top = (bounds.top / height * 100) + '%';
		layerGuide.style.width = (bounds.width / width * 100) + '%';
		layerGuide.style.height = (bounds.height / height * 100) + '%';
		layerGuide.setAttribute('data-empty', bounds.empty ? '1' : '0');
		rotateControls = layerGuide.querySelector('.heatmap-layer-rotate-controls');
		if (rotateControls) {
			visibleRotateX = clamp(bounds.left + bounds.width / 2, 40, width - 40);
			rotateControls.style.left = ((visibleRotateX - bounds.left) / Math.max(1, bounds.width) * 100) + '%';
			rotateControls.style.top = bounds.top < 42 ? '8px' : '-38px';
		}
		transformToolbar.style.left = Math.max(8, Math.min(width - 160, bounds.left)) / width * 100 + '%';
		transformToolbar.style.top = Math.max(8, bounds.top - 36) / height * 100 + '%';
	}

	function canvasPoint(event) {
		var rect = canvas.getBoundingClientRect();
		return {
			x: (event.clientX - rect.left) * canvas.width / Math.max(1, rect.width),
			y: (event.clientY - rect.top) * canvas.height / Math.max(1, rect.height)
		};
	}

	function anchorForHandle(bounds, handle) {
		var centerX = bounds.left + bounds.width / 2;
		var centerY = bounds.top + bounds.height / 2;
		return {
			x: handle.indexOf('w') !== -1 ? bounds.right : handle.indexOf('e') !== -1 ? bounds.left : centerX,
			y: handle.indexOf('n') !== -1 ? bounds.bottom : handle.indexOf('s') !== -1 ? bounds.top : centerY
		};
	}

	function setScaleAroundPoint(anchor, nextScale, state) {
		var point = unrotateCoordinate(anchor.x + state.cropX, anchor.y + state.cropY, state.rotate);
		setNumberField('xoffset', state.xoffset + point.x * (nextScale - state.scale));
		setNumberField('yoffset', state.yoffset + point.y * (nextScale - state.scale));
		setNumberField('scale', nextScale);
	}

	function beginResize(event, handle) {
		var bounds = layerBounds();
		var anchor;
		var point;
		var distance;
		if (!bounds) {
			return;
		}
		anchor = anchorForHandle(bounds, handle);
		point = canvasPoint(event);
		distance = Math.max(1, Math.sqrt(Math.pow(point.x - anchor.x, 2) + Math.pow(point.y - anchor.y, 2)));
		resizeState = {
			handle: handle,
			anchor: anchor,
			distance: distance,
			xoffset: intConfig('xoffset'),
			yoffset: intConfig('yoffset'),
			scale: scaleConfig(),
			rotate: rotationSteps(),
			cropX: intConfig('cropx2') > 0 ? intConfig('cropx1') : 0,
			cropY: intConfig('cropy2') > 0 ? intConfig('cropy1') : 0
		};
		layerGuide.className = 'heatmap-layer-guide is-resizing';
		if (event.preventDefault) {
			event.preventDefault();
		}
		if (event.stopPropagation) {
			event.stopPropagation();
		}
	}

	function resizeMove(event) {
		var point;
		var distance;
		var factor;
		var nextScale;
		if (!resizeState) {
			return;
		}
		point = canvasPoint(event);
		distance = Math.max(1, Math.sqrt(Math.pow(point.x - resizeState.anchor.x, 2) + Math.pow(point.y - resizeState.anchor.y, 2)));
		factor = clamp(distance / resizeState.distance, 0.05, 20);
		nextScale = clamp(resizeState.scale / factor, 0.1, 64);
		setScaleAroundPoint(resizeState.anchor, nextScale, resizeState);
		schedulePreview();
		if (event.preventDefault) {
			event.preventDefault();
		}
	}

	function endResize() {
		if (!resizeState) {
			return;
		}
		resizeState = null;
		if (layerGuide) {
			layerGuide.className = 'heatmap-layer-guide';
		}
	}

	function updateGuides() {
		var origin;
		var width;
		var height;
		var bounds;
		var cropWidth;
		var cropHeight;
		ensureGuides();
		if (!guides || !canvas.width || !canvas.height) {
			return;
		}
		width = canvas.width;
		height = canvas.height;
		layerGuide.style.display = 'block';
		bounds = layerBounds();
		if (bounds) {
			setLayerGuideBounds(bounds);
		} else {
			layerGuide.style.left = '0';
			layerGuide.style.top = '0';
			layerGuide.style.width = '100%';
			layerGuide.style.height = '100%';
			layerGuide.setAttribute('data-empty', '1');
		}
		transformToolbar.style.display = 'none';

		origin = projectedOrigin();
		originMarker.style.left = (origin.x / Math.max(1, width) * 100) + '%';
		originMarker.style.top = (origin.y / Math.max(1, height) * 100) + '%';
		originMarker.setAttribute('data-outside', origin.x < 0 || origin.y < 0 || origin.x > width || origin.y > height ? '1' : '0');

		cropWidth = intConfig('cropx2');
		cropHeight = intConfig('cropy2');
		if (cropWidth > 0 && cropHeight > 0) {
			cropGuide.style.display = 'block';
			if (lastPayload && lastPayload.image && lastPayload.image.crop) {
				cropGuide.style.left = '0';
				cropGuide.style.top = '0';
				cropGuide.style.width = '100%';
				cropGuide.style.height = '100%';
			} else {
				cropGuide.style.left = (intConfig('cropx1') / Math.max(1, width) * 100) + '%';
				cropGuide.style.top = (intConfig('cropy1') / Math.max(1, height) * 100) + '%';
				cropGuide.style.width = (cropWidth / Math.max(1, width) * 100) + '%';
				cropGuide.style.height = (cropHeight / Math.max(1, height) * 100) + '%';
			}
		} else {
			cropGuide.style.display = 'none';
		}
	}

	function schedulePreview() {
		if (arguments[0] !== false) {
			invalidatePreviewToken();
		}
		var token = ++requestSeq;
		if (previewTimer) {
			clearTimeout(previewTimer);
		}
		updateGuides();
		previewTimer = setTimeout(function() {
			previewTimer = null;
			request('preview', token);
		}, 120);
	}

	function activeMap() {
		var typed = newMap && newMap.value ? newMap.value : '';
		return typed || (mapSelect ? mapSelect.value : wizard.getAttribute('data-heatmap-map'));
	}

	function syncFieldsFromConfig(config) {
		var fields = wizard.querySelectorAll('[data-heatmap-number]');
		var checks = wizard.querySelectorAll('[data-heatmap-check]');
		var ranges = wizard.querySelectorAll('[data-heatmap-field]');
		var i;
		currentConfig = config || currentConfig;
		for (i = 0; i < fields.length; i++) {
			if (currentConfig[fields[i].getAttribute('data-heatmap-number')] !== undefined) {
				fields[i].value = currentConfig[fields[i].getAttribute('data-heatmap-number')];
			}
		}
		for (i = 0; i < checks.length; i++) {
			checks[i].checked = Boolean(Number(currentConfig[checks[i].getAttribute('data-heatmap-check')]));
		}
		syncTransformButtons();
		for (i = 0; i < ranges.length; i++) {
			if (currentConfig[ranges[i].getAttribute('data-heatmap-field')] !== undefined) {
				if (ranges[i].getAttribute('data-heatmap-scale-slider')) {
					ranges[i].value = scaleToSlider(currentConfig[ranges[i].getAttribute('data-heatmap-field')]);
				} else {
					ranges[i].value = currentConfig[ranges[i].getAttribute('data-heatmap-field')];
				}
			}
		}
	}

	function collectConfig(action, useCurrentControls) {
		var controls = {
			overviewText: overviewText ? overviewText.value : '',
			floors: readFloors(),
			floor: floorSelect ? floorSelect.value : 'all',
			event: eventSelect ? eventSelect.value : 'both',
			lang: adminLanguage
		};
		var fields = wizard.querySelectorAll('[data-heatmap-number]');
		var checks = wizard.querySelectorAll('[data-heatmap-check]');
		var from = diagnosticSeconds(diagnosticFrom);
		var to = diagnosticSeconds(diagnosticTo);
		var i;
		if ((from === null) !== (to === null) || (from !== null && to !== null && from >= to)) {
			setLog(adminText('diagnostic-window-invalid', 'Choose a valid UTC diagnostic window.'));
			return null;
		}
		if (from !== null && to !== null) {
			controls.diagnosticFrom = from;
			controls.diagnosticTo = to;
		}
		if (useCurrentControls) {
			for (i = 0; i < fields.length; i++) {
				controls[fields[i].getAttribute('data-heatmap-number')] = fields[i].value;
			}
			for (i = 0; i < checks.length; i++) {
				controls[checks[i].getAttribute('data-heatmap-check')] = checks[i].checked ? 1 : 0;
			}
		}
		landmarkResult = evaluateLandmarks();
		controls.landmarks = readLandmarks();
		controls.landmarkTolerance = landmarkTolerance ? landmarkTolerance.value : 10;
		if (candidateIsApplied()) {
			controls.registrationRequested = 1;
		}
		return HeatmapAdminPayload.build(action, {
			game: wizard.getAttribute('data-heatmap-game'),
			map: activeMap()
		}, controls, useCurrentControls, currentConfigHash, currentPreviewToken);
	}

	function responseMessage(data, fallback) {
		return data && typeof data.message === 'string' && data.message.length <= 512
			? data.message
			: fallback;
	}

	function render(payload, replaceFloors) {
		var side;
		var radius;
		var imageUrl;
		var points;
		lastPayload = payload;
		serverRegistration = payload.registration || null;
		renderLandmarkResiduals(serverRegistration);
		settingsOnly = payload.settingsOnly === true;
		currentPreviewToken = (settingsOnly || candidateIsApplied() && serverRegistration && serverRegistration.ok) && /^[a-f0-9]{64}$/i.test(payload.previewToken || '') ? payload.previewToken : '';
		syncSaveGate();
		if (isConfigHash(payload.configHash)) {
			currentConfigHash = payload.configHash;
		}
		if (payload.projection) {
			currentConfig = payload.projection;
			currentConfig.renderer = payload.renderer ? payload.renderer.mode : 'thermal';
			currentConfig.normalization = payload.renderer ? payload.renderer.normalization : 'sqrt';
			syncFieldsFromConfig(currentConfig);
			if (replaceFloors) {
				renderFloors(currentConfig.floors || []);
			}
			renderFloorSelect(currentConfig.floors || []);
		}
		points = Array.isArray(payload.points) ? payload.points : [];
		imageUrl = payload.image && heatmapSafeImageUrl(payload.image.url);
		if (imageUrl) {
			image.onload = function() {
				canvas.width = heatmapSafeImageDimension(payload.image.width, image.naturalWidth);
				canvas.height = heatmapSafeImageDimension(payload.image.height, image.naturalHeight);
				side = Math.sqrt(canvas.width * canvas.height);
				radius = points.length <= 5 ? 46 : Math.max(24, Math.min(54, Math.round(side / 38)));
				lastGuideRadius = radius + Math.round(radius * 0.55);
				if (payload.renderer && payload.renderer.mode === 'points') {
					renderer.drawPoints(payload.exact && Array.isArray(payload.exact.points) ? payload.exact.points : []);
				} else {
					renderer.radius(radius, Math.round(radius * 0.55)).data(points, payload.max || 1, payload.renderer).draw();
				}
				canvas.style.display = overlayVisible ? 'block' : 'none';
				updateGuides();
				drawReviewOverlay();
				drawSpatialPreview(payload);
				loadDefaultGeometry(payload);
			};
			image.src = imageUrl;
			if (image.complete) {
				image.onload();
			}
		}
		if (status && payload.diagnostics) {
			status.textContent = payload.diagnostics.inBounds + '/' + payload.diagnostics.candidate + ' ' + heatmapText('heatmapInBounds', 'in bounds');
			status.className = payload.diagnostics.manualRequired ? 'heatmap-status is-warning' : 'heatmap-status';
		}
		renderDiagnostics(payload);
		refreshEditor();
		setLog(responseMessage(payload, adminText('preview-ready', 'Preview ready.')));
	}

	function request(action, token, useCurrentControls) {
		var payload = collectConfig(action, useCurrentControls !== false);
		var headers = {
			'Content-Type': 'application/json',
			'X-HLX-CSRF': csrfToken
		};
		if (!payload) {
			return Promise.resolve(null);
		}
		if (action === 'save' && (!isConfigHash(currentConfigHash) || (!settingsOnly && (!landmarkResult || !landmarkResult.ok)) || drawingFloor || !/^[a-f0-9]{64}$/i.test(currentPreviewToken))) {
			setLog(adminText('load-before-save', 'Load the calibration before saving.'));
			return Promise.resolve(null);
		}
		if (!token) {
			token = ++requestSeq;
		}
		if (previewTimer) {
			clearTimeout(previewTimer);
			previewTimer = null;
		}
		setLog(heatmapText('loading', 'Loading...'));
		return fetch('heatmap_admin.php', {
			method: 'POST',
			credentials: 'same-origin',
			headers: headers,
			body: JSON.stringify(payload)
		})
		.then(function(response) {
			return response.json().then(function(data) {
				if (!response.ok) {
					throw data;
				}
				return data;
			});
		})
		.then(function(data) {
			if (token !== requestSeq) {
				return data;
			}
			if (action === 'save') {
				if (isConfigHash(data.configHash)) {
					currentConfigHash = data.configHash;
				}
				if (data.projection) {
					syncFieldsFromConfig(data.projection);
					renderFloors(data.floors || data.projection.floors || []);
					renderFloorSelect(data.floors || data.projection.floors || []);
				}
				setLog(responseMessage(data, adminText('saved', 'Calibration saved.')));
				return request('preview');
			}
			render(data, useCurrentControls === false);
			return data;
		})
		.catch(function(error) {
			setLog(responseMessage(error, heatmapText('heatmapRequestFailed', 'Heatmap request failed')));
			if (error && error.code === 'preview_required') {
				invalidatePreviewToken();
			}
			if (error && error.code === 'stale_config') {
				requestStoredConfig();
			}
		});
	}

	function requestStoredConfig() {
		geometryKey = ''; geometryGeneration++; syncGeometryToggle(false);
		if (geometryStatus) geometryStatus.textContent = adminLanguage === 'ru' ? 'Геометрия не загружена' : 'Geometry not loaded';
		image.onload = null;
		image.src = 'hlstatsimg/nomap.png';
		canvas.width = canvas.width;
		canvas.style.display = 'none';
		drawingFloor = null; drawingPoints = []; pickingLandmark = null;
		if (geometryOverlay && geometryOverlay.parentNode) geometryOverlay.parentNode.removeChild(geometryOverlay);
		geometryOverlay = null;
		return request('preview', null, false);
	}

	function upload() {
		var form = new FormData();
		if (!isConfigHash(currentConfigHash)) {
			setLog(adminText('load-before-save', 'Load the calibration before saving files.'));
			return;
		}
		form.append('action', 'upload');
		form.append('game', wizard.getAttribute('data-heatmap-game'));
		form.append('map', activeMap());
		form.append('configHash', currentConfigHash);
		form.append('lang', adminLanguage);
		if (mapImage && mapImage.files && mapImage.files[0]) {
			form.append('mapImage', mapImage.files[0]);
		}
		if (overviewFile && overviewFile.files && overviewFile.files[0]) {
			form.append('overviewFile', overviewFile.files[0]);
		}
		if (overviewText && overviewText.value) {
			form.append('overviewText', overviewText.value);
		}
		setLog(heatmapText('uploading', 'Uploading...'));
		fetch('heatmap_admin.php', {
			method: 'POST',
			credentials: 'same-origin',
			headers: {'X-HLX-CSRF': csrfToken},
			body: form
		})
		.then(function(response) {
			return response.json().then(function(data) {
				if (!response.ok) {
					throw data;
				}
				return data;
			});
		})
		.then(function(data) {
			if (isConfigHash(data.configHash)) {
				currentConfigHash = data.configHash;
			}
			if (data.projection) {
				syncFieldsFromConfig(data.projection);
			}
			setLog(responseMessage(data, adminText('uploaded', 'Upload saved.')));
			request('preview');
		})
		.catch(function(error) {
			setLog(responseMessage(error, heatmapText('heatmapRequestFailed', 'Heatmap request failed')));
			if (error && error.code === 'stale_config') {
				requestStoredConfig();
			}
		});
	}

	function bindClick(selector, fn) {
		var button = wizard.querySelector(selector);
		if (button) {
			button.onclick = fn;
		}
	}

	function drawReviewOverlay() {
		if (!canvas || !canvas.parentNode || !document.createElementNS) return;
		var ns = 'http://www.w3.org/2000/svg';
		if (!geometryOverlay) {
			geometryOverlay = document.createElementNS(ns, 'svg');
			geometryOverlay.setAttribute('class', 'heatmap-admin-review-overlay');
			geometryOverlay.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:5';
			canvas.parentNode.appendChild(geometryOverlay);
		}
		geometryOverlay.setAttribute('viewBox', '0 0 ' + canvas.width + ' ' + canvas.height);
		var previous = geometryOverlay.querySelector('[data-annotations]');
		if (previous) geometryOverlay.removeChild(previous);
		var group = document.createElementNS(ns, 'g'); group.setAttribute('data-annotations', '1');
		var projectConfig = {xoffset:intConfig('xoffset'), yoffset:intConfig('yoffset'), scale:scaleConfig(), flipX:boolConfig('flipx'), flipY:boolConfig('flipy'), rotate:rotationSteps(), cropX:intConfig('cropx1'), cropY:intConfig('cropy1')};
		var regions = readFloors().filter(function(floor) { return !floorSelect || floorSelect.value === 'all' || floor.id === floorSelect.value; }).reduce(function(all, floor) {
			return all.concat((floor.regions || []).map(function(p) { return {points:p, wall:false}; }), (floor.blocked || []).map(function(p) { return {points:p, wall:true}; }));
		}, []);
		if (drawingPoints.length) regions.push({points:drawingPoints, wall:drawingKind === 'blocked'});
		regions.forEach(function(item) {
			var p = item.points;
			var shape = document.createElementNS(ns, 'polyline');
			var points = p.map(function(v) { var q = HeatmapLandmarkSolver.project({worldX:v[0],worldY:v[1]}, projectConfig); return q.x + ',' + q.y; });
			if (p !== drawingPoints && points.length) points.push(points[0]);
			shape.setAttribute('points', points.join(' ')); shape.setAttribute('fill',item.wall ? '#ff526533' : 'none'); shape.setAttribute('stroke',item.wall ? '#ff5265' : '#ffdc65'); shape.setAttribute('stroke-width','3'); group.appendChild(shape);
		});
		readLandmarks().forEach(function(p, index) {
			if (!isFinite(p.pixelX) || !isFinite(p.pixelY)) return;
			var circle = document.createElementNS(ns, 'circle'); circle.setAttribute('cx',p.pixelX); circle.setAttribute('cy',p.pixelY);
			circle.setAttribute('r','6'); circle.setAttribute('fill',p.holdout ? '#ff8956' : '#4adbd2'); group.appendChild(circle);
			var label = document.createElementNS(ns,'text'); label.setAttribute('x',p.pixelX + 9); label.setAttribute('y',p.pixelY - 8); label.setAttribute('fill','#fff'); label.setAttribute('font-size','16'); label.textContent=String(index+1); group.appendChild(label);
		});
		geometryOverlay.appendChild(group);
	}

	function editorButton(text, action) {
		var button = document.createElement('button'); button.type = 'button'; button.textContent = text; button.onclick = action; return button;
	}

	function selectedFloorRow() {
		return Array.prototype.filter.call(floorRows.children, function(row) { return row.querySelector('[data-heatmap-floor-field="id"]').value === floorSelect.value; })[0];
	}

	function cancelDrawing() {
		drawingFloor = null; drawingPoints = []; viewer.classList.remove('is-drawing-floor'); refreshEditor(); drawReviewOverlay(); syncSaveGate();
	}

	function startDrawing(kind) {
		var row = selectedFloorRow();
		if (!row || !lastPayload) { setLog(adminLanguage === 'ru' ? 'Добавьте и выберите этаж.' : 'Add and select a floor.'); return; }
		if (row['_' + kind].length >= 8) { setLog(adminLanguage === 'ru' ? 'Не более 8 контуров каждого вида на этаж.' : 'Up to 8 outlines of each kind per floor.'); return; }
		drawingFloor = row; drawingKind = kind; drawingPoints = []; pickingLandmark = null;
		viewer.classList.add('is-drawing-floor'); invalidatePreviewToken(); refreshEditor();
	}

	function refreshEditor() {
		if (!editorHint) return;
		var row = selectedFloorRow();
		editorHint.textContent = drawingFloor
			? (adminLanguage === 'ru' ? 'Отмечайте углы на карте. Точек: ' : 'Click corners on the map. Points: ') + drawingPoints.length + '/32'
			: (adminLanguage === 'ru' ? 'Жёлтый — допустимая область. Красный — стена: события и заливка внутри исключаются. Выберите этаж для предпросмотра ограничений.' : 'Yellow: allowed region. Red: wall; events and fill inside are excluded. Select a floor to preview its boundaries.');
		Array.prototype.forEach.call(editorToolbar.querySelectorAll('[data-drawing-action]'), function(button) {
			var action = button.getAttribute('data-drawing-action'); button.disabled = action === 'start' ? !row || !!drawingFloor : !drawingFloor;
		});
		clearChildren(contourList);
		if (row) ['regions', 'blocked'].forEach(function(kind) {
			row['_' + kind].forEach(function(p, index) {
				var name = (kind === 'blocked' ? (adminLanguage === 'ru' ? 'Стена ' : 'Wall ') : (adminLanguage === 'ru' ? 'Область ' : 'Region ')) + (index + 1);
				var button = editorButton(name + ' ×', function() { row['_' + kind].splice(index, 1); cancelDrawing(); schedulePreview(); });
				button.title = (adminLanguage === 'ru' ? 'Удалить: ' : 'Remove: ') + name; contourList.appendChild(button);
			});
		});
	}

	function uploadFloorImage(row, input) {
		var form = new FormData(), map = activeMap(), floorId = row.querySelector('[data-heatmap-floor-field="id"]').value;
		form.append('action', 'upload'); form.append('game', wizard.getAttribute('data-heatmap-game')); form.append('map', map);
		form.append('imageFloor', floorId); form.append('mapImage', input.files[0]); form.append('configHash', currentConfigHash); form.append('lang', adminLanguage);
		invalidatePreviewToken(); input.disabled = true;
		fetch('heatmap_admin.php', {method:'POST', credentials:'same-origin', headers:{'X-HLX-CSRF':csrfToken}, body:form})
			.then(function(response) { return response.json().then(function(data) { if (!response.ok) throw data; return data; }); })
			.then(function(data) {
				if (map !== activeMap() || !row.isConnected) return;
				currentConfigHash = data.configHash; row._floorImage = true; row.querySelector('input[type=checkbox]').checked = true;
				renderFloorSelect(readFloors()); floorSelect.value = floorId; schedulePreview();
			})
			.catch(function(error) { setLog(responseMessage(error, heatmapText('heatmapRequestFailed', 'Upload failed'))); })
			.then(function() { input.disabled = false; input.value = ''; });
	}

	function drawSpatialPreview(payload) {
		var floor = (payload.floors || []).filter(function(f) { return f.id === payload.activeFloor; })[0];
		if (!floor || (!(floor.regions || []).length && !(floor.blocked || []).length)) return;
		var ctx = canvas.getContext('2d');
		if (payload.renderer.mode !== 'points' && typeof presentationField === 'function') {
			// Reuse the public grid and smoothing; keep the calibration canvas in 2D.
			var grid = payload.grid, n = grid.width * grid.height, values = new Float32Array(n);
			payload.layers.total.forEach(function(r) { values[r[2] * grid.width + r[1]] = payload.query.event === 'kills' ? r[3] : payload.query.event === 'deaths' ? r[4] : r[3] + r[4]; });
			var mask = regionGridMask({floors:payload.floors, activeFloor:payload.activeFloor, grid:grid, cellSummary:function() { return null; }});
			var field = presentationField({values:values}, grid.width, grid.height, true, false, mask);
			var temp = document.createElement('canvas'); temp.width = grid.width; temp.height = grid.height;
			var small = temp.getContext('2d'), pixels = small.createImageData(grid.width, grid.height);
			for (var i = 0; i < n; i++) { var amount = Math.sqrt(field.values[i * 2] / Math.max(field.maxAbs, 0.00001)); pixels.data[i * 4] = 255; pixels.data[i * 4 + 1] = Math.round(190 - 115 * amount); pixels.data[i * 4 + 2] = 40; pixels.data[i * 4 + 3] = Math.round(210 * amount); }
			small.putImageData(pixels, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.drawImage(temp, 0, 0, grid.width * grid.bucketSize, grid.height * grid.bucketSize);
		}
		function path(p) { ctx.moveTo(p[0][0], p[0][1]); for (var j = 1; j < p.length; j++) ctx.lineTo(p[j][0], p[j][1]); ctx.closePath(); }
		ctx.save(); ctx.fillStyle = '#fff';
		if ((floor.regions || []).length) {
			var maskCanvas = document.createElement('canvas'); maskCanvas.width = canvas.width; maskCanvas.height = canvas.height;
			var target = ctx; ctx = maskCanvas.getContext('2d'); floor.regions.forEach(function(p) { ctx.beginPath(); path(p); ctx.fill(); }); ctx = target;
			ctx.globalCompositeOperation = 'destination-in'; ctx.drawImage(maskCanvas, 0, 0);
		}
		ctx.globalCompositeOperation = 'destination-out'; (floor.blocked || []).forEach(function(p) { ctx.beginPath(); path(p); ctx.fill(); }); ctx.restore();
	}

	function mountFloorEditor() {
		var panel = wizard.querySelector('.heatmap-admin-panel'), fieldset = wizard.querySelector('.heatmap-admin-floors');
		editorToolbar = document.createElement('div'); editorToolbar.className = 'heatmap-floor-editor-toolbar';
		editorToolbar.appendChild(floorSelect.parentNode);
		[['Допустимая область', 'Allowed region', function() { startDrawing('regions'); }, 'start'], ['Стена / исключить область', 'Wall / excluded area', function() { startDrawing('blocked'); }, 'start'],
		 ['Завершить', 'Finish', function() {
			if (drawingPoints.length < 3) { setLog(adminLanguage === 'ru' ? 'Нужны минимум три точки.' : 'At least three points are required.'); return; }
			drawingFloor['_' + drawingKind].push(drawingPoints); cancelDrawing(); schedulePreview();
		 }, 'finish'], ['Убрать точку', 'Undo point', function() { drawingPoints.pop(); drawReviewOverlay(); refreshEditor(); }, 'undo'], ['Отменить', 'Cancel', function() { cancelDrawing(); schedulePreview(); }, 'cancel']].forEach(function(item) {
			var button = editorButton(item[adminLanguage === 'ru' ? 0 : 1], item[2]); button.setAttribute('data-drawing-action', item[3]); editorToolbar.appendChild(button);
		});
		editorToolbar.appendChild(saveButton);
		editorHint = document.createElement('p'); editorHint.className = 'heatmap-floor-editor-hint'; editorHint.setAttribute('aria-live', 'polite');
		contourList = document.createElement('div'); contourList.className = 'heatmap-floor-contours';
		viewer.insertBefore(editorToolbar, viewer.firstChild); viewer.insertBefore(editorHint, editorToolbar.nextSibling);
		viewer.appendChild(contourList); viewer.appendChild(fieldset); viewer.appendChild(log);
		var diagnostic = wizard.querySelector('.heatmap-admin-diagnostic'); fieldset.appendChild(diagnostic);
		var advanced = document.createElement('details'), summary = document.createElement('summary'); advanced.className = 'heatmap-admin-advanced';
		summary.textContent = adminLanguage === 'ru' ? 'Привязка карты и дополнительные настройки' : 'Map alignment and advanced settings';
		panel.parentNode.insertBefore(advanced, panel); advanced.appendChild(summary); advanced.appendChild(panel);
		advanced.ontoggle = function() { viewer.classList.toggle('is-calibrating', advanced.open); };
		wizard.classList.add('heatmap-floor-editor'); refreshEditor();
	}

	function chooseMapPoint(event) {
		if (!drawingFloor && !pickingLandmark) return false;
		var rect = canvas.getBoundingClientRect();
		var x = Math.round((event.clientX - rect.left) * canvas.width / rect.width);
		var y = Math.round((event.clientY - rect.top) * canvas.height / rect.height);
		if (x < 0 || y < 0 || x >= canvas.width || y >= canvas.height) return true;
		if (pickingLandmark) {
			pickingLandmark.querySelector('[data-heatmap-landmark="pixelX"]').value = x;
			pickingLandmark.querySelector('[data-heatmap-landmark="pixelY"]').value = y;
			pickingLandmark = null; schedulePreview();
		} else if (drawingPoints.length < 32) {
			var raw = HeatmapProjection.unrotate(x + intConfig('cropx1'), y + intConfig('cropy1'), rotationSteps());
			drawingPoints.push([Math.round((raw.x * scaleConfig() - intConfig('xoffset')) * (boolConfig('flipx') ? -1 : 1)), Math.round((raw.y * scaleConfig() - intConfig('yoffset')) * (boolConfig('flipy') ? -1 : 1))]);
		}
		drawReviewOverlay(); refreshEditor(); if (event.preventDefault) event.preventDefault(); return true;
	}

	var reportFile = wizard.querySelector('[data-heatmap-registration-report]');
	if (reportFile) reportFile.onchange = function() {
		var file = reportFile.files && reportFile.files[0];
		if (!file || file.size > 2000000 || !lastPayload) { setLog(adminLanguage === 'ru' ? 'Сначала загрузите карту. Отчёт — не более 2 МБ.' : 'Load a map first. Report limit: 2 MB.'); return; }
		var selectedMap = activeMap();
		file.text().then(function(text) {
			if (selectedMap !== activeMap()) return;
			var report = HeatmapRegistrationReport.parse(text);
			if (report.size[0] !== lastPayload.image.width || report.size[1] !== lastPayload.image.height) throw new Error('image_size');
			Object.keys(report.config).forEach(function(key) {
				if (key === 'flipx' || key === 'flipy') wizard.querySelector('[data-heatmap-check="'+key+'"]').checked = !!report.config[key];
				else setNumberField(key, report.config[key]);
			});
			appliedCandidateKey = ''; invalidatePreviewToken(); syncTransformButtons(); schedulePreview();
			setLog(adminLanguage === 'ru' ? 'Настройки подставлены. Проверьте независимые ориентиры; импорт ничего не сохраняет.' : 'Candidate loaded. Check independent landmarks; importing does not save anything.');
		}).catch(function() { setLog(adminLanguage === 'ru' ? 'Отчёт не подходит: проверьте формат и размер изображения.' : 'Report rejected: check format and image dimensions.'); });
	};
	var geometryFile = wizard.querySelector('[data-heatmap-registration-geometry]');
	function syncGeometryToggle(available) {
		if (!geometryToggle) return;
		geometryToggle.disabled = !available;
		geometryToggle.setAttribute('aria-pressed', available && geometryVisible ? 'true' : 'false');
		geometryToggle.textContent = adminLanguage === 'ru'
			? (available && geometryVisible ? 'Скрыть геометрию BSP' : 'Показать геометрию BSP')
			: (available && geometryVisible ? 'Hide BSP geometry' : 'Show BSP geometry');
		var layer = geometryOverlay && geometryOverlay.querySelector('[data-bsp-outlines]');
		if (layer) layer.style.display = geometryVisible ? '' : 'none';
	}
	function loadDefaultGeometry(payload) {
		var map = activeMap(), game = wizard.getAttribute('data-heatmap-game');
		var key = map + '|' + payload.image.url;
		if (geometryKey === key) return;
		geometryKey = key;
		var generation = ++geometryGeneration;
		var old = geometryOverlay && geometryOverlay.querySelector('[data-bsp-outlines]');
		if (old) old.parentNode.removeChild(old);
		syncGeometryToggle(false);
		if (!/^[a-z0-9_-]+$/i.test(game) || !/^[a-z0-9_-]+$/i.test(map)) return;
		var base = 'hlstatsimg/heatmap-geometry/' + encodeURIComponent(game) + '/';
		if (geometryStatus) geometryStatus.textContent = adminLanguage === 'ru' ? 'Загрузка геометрии…' : 'Loading geometry…';
		if (!geometryManifest) geometryManifest = fetch(base + 'manifest.json').then(function(response) {
			if (!response.ok) throw new Error('missing'); return response.json();
		});
		geometryManifest.then(function(manifest) {
			var entry = manifest[map];
			if (!entry || new URL(payload.image.url, window.location.href).searchParams.get('v') !== entry.imageHash) throw new Error('missing');
			return fetch(base + encodeURIComponent(map) + '.svg');
		}).then(function(response) {
			if (!response.ok) throw new Error('missing'); return response.text();
		}).then(function(text) {
			if (generation !== geometryGeneration || map !== activeMap()) return;
			installGeometry(text); syncGeometryToggle(true);
			if (geometryStatus) geometryStatus.textContent = adminLanguage === 'ru' ? 'Шаблон карты готов' : 'Map template ready';
		}).catch(function() {
			if (generation !== geometryGeneration) return;
			if (geometryStatus) geometryStatus.textContent = adminLanguage === 'ru' ? 'Для этого изображения нет шаблона BSP' : 'No BSP template for this image';
		});
	}
	function installGeometry(text) {
			if (text.length > 4000000) throw new Error('limit');
			var doc = new DOMParser().parseFromString(text, 'image/svg+xml');
			if (doc.querySelector('parsererror') || doc.documentElement.localName !== 'svg') throw new Error('svg');
			var view = (doc.documentElement.getAttribute('viewBox') || '').trim().split(/\s+/).map(Number);
			if (view.length !== 4 || view[0] !== 0 || view[1] !== 0 || view[2] !== canvas.width || view[3] !== canvas.height) throw new Error('size');
			var shapes = doc.querySelectorAll('polygon,polyline'); if (shapes.length > 20000) throw new Error('limit');
			var group = document.createElementNS('http://www.w3.org/2000/svg','g'); group.setAttribute('data-bsp-outlines','1');
			for (var i=0; i<shapes.length; i++) {
				var values = (shapes[i].getAttribute('points') || '').trim().split(/[\s,]+/).map(Number);
				if (values.length < 6 || values.length > 512 || values.length % 2 || !values.every(function(n) { return isFinite(n) && Math.abs(n) < 100000; })) throw new Error('points');
				var shape = document.createElementNS('http://www.w3.org/2000/svg',shapes[i].localName);
				shape.setAttribute('points',values.join(' ')); shape.setAttribute('fill','none'); shape.setAttribute('stroke','#45dacf'); shape.setAttribute('stroke-width','1'); group.appendChild(shape);
			}
			drawReviewOverlay(); var previous = geometryOverlay.querySelector('[data-bsp-outlines]'); if (previous) geometryOverlay.removeChild(previous); geometryOverlay.insertBefore(group,geometryOverlay.firstChild);
	}
	if (geometryFile) geometryFile.onchange = function() {
		var file = geometryFile.files && geometryFile.files[0], selectedMap = activeMap();
		if (!file || file.size > 4000000 || !lastPayload) return;
		file.text().then(function(text) {
			if (selectedMap !== activeMap()) return;
			geometryGeneration++; installGeometry(text); geometryVisible = true; syncGeometryToggle(true);
			if (geometryStatus) geometryStatus.textContent = adminLanguage === 'ru' ? 'Загружены контуры из файла' : 'Geometry loaded from file';
		}).catch(function() { setLog(adminLanguage === 'ru' ? 'Не удалось открыть контуры: нужен SVG из инструмента для этой картинки.' : 'Use the tool-generated SVG matching this image.'); });
	};
	bindClick('[data-heatmap-clear-geometry]',function() { geometryVisible = !geometryVisible; syncGeometryToggle(true); });
	if (landmarkRows) Array.prototype.forEach.call(landmarkRows.querySelectorAll('[data-heatmap-landmark-row]'), function(row) {
		var cell=document.createElement('td'), button=document.createElement('button'); button.type='button'; button.textContent=adminLanguage==='ru'?'На карте':'Pick on map';
		button.onclick=function() { if (drawingFloor) return; pickingLandmark=row; setLog(adminLanguage==='ru'?'Нажмите соответствующее место на карте. X/Y мира берутся из игры, не из этой картинки.':'Click the matching place on the map. World X/Y must come from the game.'); }; cell.appendChild(button); row.appendChild(cell);
	});

	bindClick('[data-heatmap-admin-load]', requestStoredConfig);
	bindClick('[data-heatmap-admin-preview]', function() { request('preview'); });
	bindClick('[data-heatmap-admin-save]', function() { request('save'); });
	bindClick('[data-heatmap-landmark-apply]', function() {
		landmarkResult = evaluateLandmarks();
		if (!landmarkResult.ok) {
			syncSaveGate();
			return;
		}
		setNumberField('xoffset', landmarkResult.xoffset);
		setNumberField('yoffset', landmarkResult.yoffset);
		setNumberField('scale', landmarkResult.scale);
		var flipX = wizard.querySelector('[data-heatmap-check="flipx"]');
		var flipY = wizard.querySelector('[data-heatmap-check="flipy"]');
		if (flipX) { flipX.checked = landmarkResult.flipX; }
		if (flipY) { flipY.checked = landmarkResult.flipY; }
		setNumberField('rotate', landmarkResult.rotate);
		appliedCandidateKey = candidateKey(landmarkResult);
		syncTransformButtons();
		schedulePreview();
	});
	bindClick('[data-heatmap-admin-upload]', upload);
	bindClick('[data-heatmap-floor-add]', function() {
		var used = readFloors(), next = 1; while (used.some(function(f) { return f.id === 'floor' + next; })) next++;
		addFloorRow({
			id: 'floor' + next,
			label_en: 'Floor',
			label_ru: 'Уровень',
			z_min: used.length ? Math.max.apply(null, used.map(function(f) { return f.z_max; })) : -4096,
			z_max: used.length ? Math.min(8388607, Math.max.apply(null, used.map(function(f) { return f.z_max; })) + 128) : 4096
		});
		renderFloorSelect(readFloors()); floorSelect.value = 'floor' + next;
		schedulePreview();
	});
	bindClick('[data-heatmap-floor-suggest]', function() {
		if (!suggestedFloors.length) {
			return;
		}
		renderFloors(suggestedFloors);
		renderFloorSelect(suggestedFloors);
		schedulePreview();
	});
	if (toggle) {
		toggle.onclick = function() {
			overlayVisible = !overlayVisible;
			canvas.style.display = overlayVisible ? 'block' : 'none';
			toggle.className = overlayVisible ? 'heatmap-toggle is-active' : 'heatmap-toggle';
		};
		toggle.className = 'heatmap-toggle is-active';
	}

	var ranges = wizard.querySelectorAll('[data-heatmap-field]');
	for (var i = 0; i < ranges.length; i++) {
		ranges[i].oninput = function() {
			var number = wizard.querySelector('[data-heatmap-number="' + this.getAttribute('data-heatmap-field') + '"]');
			if (number) {
				number.value = this.getAttribute('data-heatmap-scale-slider') ? sliderToScale(this.value) : this.value;
			}
			schedulePreview();
		};
	}
	var numberInputs = wizard.querySelectorAll('[data-heatmap-number]');
	for (var n = 0; n < numberInputs.length; n++) {
		numberInputs[n].oninput = function() {
			var range = wizard.querySelector('[data-heatmap-field="' + this.getAttribute('data-heatmap-number') + '"]');
			if (range) {
				range.value = range.getAttribute('data-heatmap-scale-slider') ? scaleToSlider(this.value) : this.value;
			}
			schedulePreview(this.getAttribute('data-heatmap-number') !== 'renderer' && this.getAttribute('data-heatmap-number') !== 'normalization');
		};
		numberInputs[n].onchange = numberInputs[n].oninput;
	}
	var checks = wizard.querySelectorAll('[data-heatmap-check]');
	for (var c = 0; c < checks.length; c++) {
		checks[c].onchange = function() {
			syncTransformButtons();
			schedulePreview();
		};
	}
	var transformButtons = wizard.querySelectorAll('[data-heatmap-toggle-check]');
	for (var b = 0; b < transformButtons.length; b++) {
		transformButtons[b].onclick = function() {
			toggleTransform(this.getAttribute('data-heatmap-toggle-check'));
		};
	}
	var rotateButtons = wizard.querySelectorAll('[data-heatmap-rotate-step]');
	for (var r = 0; r < rotateButtons.length; r++) {
		rotateButtons[r].onclick = function() {
			rotateLayer(this.getAttribute('data-heatmap-rotate-step'));
		};
	}
	if (mapSelect) {
		mapSelect.onchange = function() { invalidatePreviewToken(); requestStoredConfig(); };
	}
	if (floorSelect) {
		floorSelect.onchange = function() { cancelDrawing(); schedulePreview(); };
	}
	if (eventSelect) {
		eventSelect.onchange = schedulePreview;
	}
	if (diagnosticFrom) {
		diagnosticFrom.onchange = schedulePreview;
	}
	if (diagnosticTo) {
		diagnosticTo.onchange = schedulePreview;
	}
	if (landmarkRows) {
		var landmarkInputs = landmarkRows.querySelectorAll('input');
		for (var landmarkInputIndex = 0; landmarkInputIndex < landmarkInputs.length; landmarkInputIndex += 1) {
			landmarkInputs[landmarkInputIndex].oninput = schedulePreview;
			landmarkInputs[landmarkInputIndex].onchange = schedulePreview;
		}
	}
	if (landmarkTolerance) {
		landmarkTolerance.oninput = schedulePreview;
		landmarkTolerance.onchange = schedulePreview;
	}
	if (canvas) {
		canvas.onmousedown = function(event) {
			if (chooseMapPoint(event)) return;
			if (!wizard.querySelector('.heatmap-admin-advanced').open) return;
			var rect = canvas.getBoundingClientRect();
			dragState = {
				x: event.clientX,
				y: event.clientY,
				xoffset: intConfig('xoffset'),
				yoffset: intConfig('yoffset'),
				scale: scaleConfig(),
				rotate: rotationSteps(),
				rect: {width: rect.width, height: rect.height},
				canvasWidth: canvas.width,
				canvasHeight: canvas.height
			};
			canvas.className = 'heatmap-overlay is-dragging';
			if (event.preventDefault) {
				event.preventDefault();
			}
		};
		canvas.onmousemove = function(event) {
			var dx;
			var dy;
			var moved;
			if (!dragState) {
				return;
			}
			dx = event.clientX - dragState.x;
			dy = event.clientY - dragState.y;
			moved = HeatmapAdminGeometry.offsetDelta(dx, dy, dragState.rect, dragState.canvasWidth, dragState.canvasHeight, dragState.scale, dragState.rotate);
			setNumberField('xoffset', dragState.xoffset + moved[0]);
			setNumberField('yoffset', dragState.yoffset + moved[1]);
			schedulePreview();
		};
		canvas.onmouseup = function() {
			dragState = null;
			canvas.className = 'heatmap-overlay';
		};
		canvas.onmouseleave = canvas.onmouseup;
		canvas.onwheel = function(event) {
			if (drawingFloor || !wizard.querySelector('.heatmap-admin-advanced').open) return;
			var rect = canvas.getBoundingClientRect();
			var oldScale = scaleConfig();
			var nextScale = clamp(oldScale * (event.deltaY < 0 ? 0.94 : 1.06), 0.1, 64);
			var x = (event.clientX - rect.left) * canvas.width / Math.max(1, rect.width);
			var y = (event.clientY - rect.top) * canvas.height / Math.max(1, rect.height);
			setScaleAroundPoint({x: x, y: y}, nextScale, {
				xoffset: intConfig('xoffset'),
				yoffset: intConfig('yoffset'),
				scale: oldScale,
				rotate: rotationSteps(),
				cropX: intConfig('cropx2') > 0 ? intConfig('cropx1') : 0,
				cropY: intConfig('cropy2') > 0 ? intConfig('cropy1') : 0
			});
			schedulePreview();
			if (event.preventDefault) {
				event.preventDefault();
			}
		};
	}
	mountFloorEditor();
	syncFieldsFromConfig(currentConfig);
	seedDiagnosticWindow();
	updateGuides();
	invalidatePreviewToken();
	if (activeMap()) {
		requestStoredConfig();
	}
}
