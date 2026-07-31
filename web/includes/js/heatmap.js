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

var HeatmapAdminPayload = (function() {
	function build(action, identity, controls, useCurrentControls) {
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
			status.innerHTML = text || '';
			status.className = warning ? 'heatmap-status is-warning' : 'heatmap-status';
		}
	}

	function syncCanvasSize(payload) {
		var width = payload.image && payload.image.width ? payload.image.width : image.naturalWidth;
		var height = payload.image && payload.image.height ? payload.image.height : image.naturalHeight;
		canvas.width = width;
		canvas.height = height;
		renderer.data([], 1, payload.renderer || renderer.options).draw();
		canvas.style.display = overlayVisible ? 'block' : 'none';
	}

	function escapeHtml(text) {
		var div = document.createElement('div');
		div.appendChild(document.createTextNode(text == null ? '' : String(text)));
		return div.innerHTML;
	}

	function formatActors(label, actors) {
		var i;
		var rows = [];
		if (!actors || !actors.length) {
			return '';
		}
		for (i = 0; i < Math.min(3, actors.length); i++) {
			rows.push(escapeHtml(actors[i].name) + ' (' + escapeHtml(actors[i].count) + ')');
		}
		return '<div><b>' + escapeHtml(label) + ':</b> ' + rows.join(', ') + '</div>';
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

		tooltip.innerHTML =
			'<div><b>' + escapeHtml(nearest.value || 0) + '</b> ' + escapeHtml(heatmapText('heatmapEvents', 'events')) + '</div>' +
			'<div>' + escapeHtml(heatmapText('kills', 'Kills')) + ': ' + escapeHtml(nearest.killValue || 0) + ' / ' + escapeHtml(heatmapText('deaths', 'Deaths')) + ': ' + escapeHtml(nearest.deathValue || 0) + '</div>' +
			formatActors(heatmapText('heatmapKillers', 'Killers'), nearest.topKillers) +
			formatActors(heatmapText('heatmapVictims', 'Victims'), nearest.topVictims) +
			formatActors(heatmapText('players', 'Players'), nearest.topPlayers);
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
				if (payload.image && payload.image.url) {
					image.onload = function() {
						syncCanvasSize(payload);
						renderer.data([], 1, payload.renderer || renderer.options).draw();
						setStatus(warningText || '0', warning);
					};
					image.src = payload.image.url;
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
			image.src = payload.image.url;
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
			number.value = name === 'scale' ? clamp(value, 0.1, 64).toFixed(2) : Math.round(value);
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
			rotateButtons[i].innerHTML = heatmapText('heatmapRotate', 'Rotate') + ' ' + (rotationSteps() ? (rotationSteps() * 90) : 90) + '&deg;';
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
		layerGuide.innerHTML =
			'<span class="heatmap-layer-handle heatmap-layer-handle-nw" data-heatmap-resize="nw"></span>' +
			'<span class="heatmap-layer-handle heatmap-layer-handle-n" data-heatmap-resize="n"></span>' +
			'<span class="heatmap-layer-handle heatmap-layer-handle-ne" data-heatmap-resize="ne"></span>' +
			'<span class="heatmap-layer-handle heatmap-layer-handle-e" data-heatmap-resize="e"></span>' +
			'<span class="heatmap-layer-handle heatmap-layer-handle-se" data-heatmap-resize="se"></span>' +
			'<span class="heatmap-layer-handle heatmap-layer-handle-s" data-heatmap-resize="s"></span>' +
			'<span class="heatmap-layer-handle heatmap-layer-handle-sw" data-heatmap-resize="sw"></span>' +
			'<span class="heatmap-layer-handle heatmap-layer-handle-w" data-heatmap-resize="w"></span>' +
			'<span class="heatmap-layer-rotate-controls">' +
			'<button type="button" class="heatmap-layer-rotate-button" data-heatmap-rotate-step="-1" title="' + heatmapText('heatmapRotateLeft90', 'Rotate left 90 degrees') + '">&#8635;</button>' +
			'<button type="button" class="heatmap-layer-rotate-button" data-heatmap-rotate-step="1" title="' + heatmapText('heatmapRotateRight90', 'Rotate right 90 degrees') + '">&#8634;</button>' +
			'</span>';
		var frameRotateButtons = layerGuide.querySelectorAll('.heatmap-layer-rotate-button');
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
		transformToolbar.innerHTML =
			'<button type="button" class="heatmap-transform-button" data-heatmap-toggle-check="flipx">' + heatmapText('heatmapFlipX', 'Flip X') + '</button>' +
			'<button type="button" class="heatmap-transform-button" data-heatmap-toggle-check="flipy">' + heatmapText('heatmapFlipY', 'Flip Y') + '</button>' +
			'<button type="button" class="heatmap-transform-button" data-heatmap-rotate-step="1">' + heatmapText('heatmapRotate', 'Rotate') + ' 90&deg;</button>';
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
			overviewText: overviewText ? overviewText.value : ''
		};
		var fields = wizard.querySelectorAll('[data-heatmap-number]');
		var checks = wizard.querySelectorAll('[data-heatmap-check]');
		var i;
		if (useCurrentControls) {
			for (i = 0; i < fields.length; i++) {
				controls[fields[i].getAttribute('data-heatmap-number')] = fields[i].value;
			}
			for (i = 0; i < checks.length; i++) {
				controls[checks[i].getAttribute('data-heatmap-check')] = checks[i].checked ? 1 : 0;
			}
		}
		return HeatmapAdminPayload.build(action, {
			game: wizard.getAttribute('data-heatmap-game'),
			map: activeMap()
		}, controls, useCurrentControls);
	}

	function render(payload) {
		var side;
		var radius;
		lastPayload = payload;
		if (payload.projection) {
			currentConfig = payload.projection;
			currentConfig.renderer = payload.renderer ? payload.renderer.mode : 'thermal';
			currentConfig.normalization = payload.renderer ? payload.renderer.normalization : 'sqrt';
			syncFieldsFromConfig(currentConfig);
		}
		if (payload.image && payload.image.url) {
			image.onload = function() {
				canvas.width = payload.image.width || image.naturalWidth;
				canvas.height = payload.image.height || image.naturalHeight;
				side = Math.sqrt(canvas.width * canvas.height);
				radius = payload.points.length <= 5 ? 46 : Math.max(24, Math.min(54, Math.round(side / 38)));
				lastGuideRadius = radius + Math.round(radius * 0.55);
				renderer.radius(radius, Math.round(radius * 0.55)).data(payload.points || [], payload.max || 1, payload.renderer).draw();
				canvas.style.display = overlayVisible ? 'block' : 'none';
				updateGuides();
			};
			image.src = payload.image.url;
			if (image.complete) {
				image.onload();
			}
		}
		if (status && payload.diagnostics) {
			status.textContent = payload.diagnostics.inBounds + '/' + payload.diagnostics.queried + ' ' + heatmapText('heatmapInBounds', 'in bounds');
			status.className = payload.diagnostics.manualRequired ? 'heatmap-status is-warning' : 'heatmap-status';
		}
		setLog(JSON.stringify({
			saved: Boolean(payload.saved),
			configHash: payload.configHash,
			diagnostics: payload.diagnostics
		}, null, 2));
	}

	function request(action, token, useCurrentControls) {
		var payload = collectConfig(action, useCurrentControls !== false);
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
			headers: {'Content-Type': 'application/json'},
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
			if (action === 'regenerate') {
				setLog(JSON.stringify(data, null, 2));
				return data;
			}
			if (token !== requestSeq) {
				return data;
			}
			render(data);
			return data;
		})
		.catch(function(error) {
			setLog(JSON.stringify(error, null, 2));
		});
	}

	function requestStoredConfig() {
		return request('preview', null, false);
	}

	function upload() {
		var form = new FormData();
		form.append('action', 'upload');
		form.append('game', wizard.getAttribute('data-heatmap-game'));
		form.append('map', activeMap());
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
			if (data.projection) {
				syncFieldsFromConfig(data.projection);
			}
			setLog(JSON.stringify(data, null, 2));
			request('preview');
		})
		.catch(function(error) {
			setLog(JSON.stringify(error, null, 2));
		});
	}

	function bindClick(selector, fn) {
		var button = wizard.querySelector(selector);
		if (button) {
			button.onclick = fn;
		}
	}

	bindClick('[data-heatmap-admin-load]', requestStoredConfig);
	bindClick('[data-heatmap-admin-preview]', function() { request('preview'); });
	bindClick('[data-heatmap-admin-save]', function() { request('save'); });
	bindClick('[data-heatmap-admin-upload]', upload);
	bindClick('[data-heatmap-admin-regenerate]', function() {
		request('regenerate');
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
			schedulePreview();
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
		mapSelect.onchange = requestStoredConfig;
	}
	if (canvas) {
		canvas.onmousedown = function(event) {
			dragState = {
				x: event.clientX,
				y: event.clientY,
				xoffset: intConfig('xoffset'),
				yoffset: intConfig('yoffset'),
				scale: scaleConfig(),
				rotate: rotationSteps()
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
			dx = (event.clientX - dragState.x) * dragState.scale;
			dy = (event.clientY - dragState.y) * dragState.scale;
			moved = unrotateCoordinate(dx, dy, dragState.rotate);
			setNumberField('xoffset', dragState.xoffset + moved.x);
			setNumberField('yoffset', dragState.yoffset + moved.y);
			schedulePreview();
		};
		canvas.onmouseup = function() {
			dragState = null;
			canvas.className = 'heatmap-overlay';
		};
		canvas.onmouseleave = canvas.onmouseup;
		canvas.onwheel = function(event) {
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
	syncFieldsFromConfig(currentConfig);
	updateGuides();
	if (activeMap()) {
		requestStoredConfig();
	}
}
