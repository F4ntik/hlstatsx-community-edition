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
			'<div><b>' + escapeHtml(nearest.value || 0) + '</b> events</div>' +
			'<div>Kills: ' + escapeHtml(nearest.killValue || 0) + ' / Deaths: ' + escapeHtml(nearest.deathValue || 0) + '</div>' +
			formatActors('Killers', nearest.topKillers) +
			formatActors('Victims', nearest.topVictims) +
			formatActors('Players', nearest.topPlayers);
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
					payload.diagnostics.inBounds + '/' + payload.diagnostics.queried + ' in bounds',
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
				throw new Error('heatmap request failed');
			}
			return response.json();
		})
		.then(function(payload) {
			if (!payload.points || !payload.points.length || !payload.image || !payload.image.url) {
				var warningText = '';
				var warning = false;
				if (payload.diagnostics && payload.diagnostics.queried > 0) {
					warningText = payload.diagnostics.inBounds + '/' + payload.diagnostics.queried + ' in bounds';
					warning = true;
				}
				lastPayload = payload;
				if (payload.image && payload.image.url) {
					image.onload = function() {
						syncCanvasSize(payload);
						setStatus(warningText || '0', warning);
					};
					image.src = payload.image.url;
					if (image.complete) {
						syncCanvasSize(payload);
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
	var lastPayload = null;
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
		for (i = 0; i < ranges.length; i++) {
			if (currentConfig[ranges[i].getAttribute('data-heatmap-field')] !== undefined) {
				ranges[i].value = currentConfig[ranges[i].getAttribute('data-heatmap-field')];
			}
		}
	}

	function collectConfig(action) {
		var payload = {
			action: action || 'preview',
			game: wizard.getAttribute('data-heatmap-game'),
			map: activeMap(),
			overviewText: overviewText ? overviewText.value : ''
		};
		var fields = wizard.querySelectorAll('[data-heatmap-number]');
		var checks = wizard.querySelectorAll('[data-heatmap-check]');
		var i;
		for (i = 0; i < fields.length; i++) {
			payload[fields[i].getAttribute('data-heatmap-number')] = fields[i].value;
		}
		for (i = 0; i < checks.length; i++) {
			payload[checks[i].getAttribute('data-heatmap-check')] = checks[i].checked ? 1 : 0;
		}
		return payload;
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
				renderer.radius(radius, Math.round(radius * 0.55)).data(payload.points || [], payload.max || 1, payload.renderer).draw();
			};
			image.src = payload.image.url;
			if (image.complete) {
				image.onload();
			}
		}
		if (status && payload.diagnostics) {
			status.textContent = payload.diagnostics.inBounds + '/' + payload.diagnostics.queried + ' in bounds';
			status.className = payload.diagnostics.manualRequired ? 'heatmap-status is-warning' : 'heatmap-status';
		}
		setLog(JSON.stringify({
			saved: Boolean(payload.saved),
			configHash: payload.configHash,
			diagnostics: payload.diagnostics
		}, null, 2));
	}

	function request(action) {
		var payload = collectConfig(action);
		setLog('Loading...');
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
			render(data);
			return data;
		})
		.catch(function(error) {
			setLog(JSON.stringify(error, null, 2));
		});
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
		setLog('Uploading...');
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

	bindClick('[data-heatmap-admin-load]', function() { request('preview'); });
	bindClick('[data-heatmap-admin-preview]', function() { request('preview'); });
	bindClick('[data-heatmap-admin-save]', function() { request('save'); });
	bindClick('[data-heatmap-admin-upload]', upload);
	bindClick('[data-heatmap-admin-regenerate]', function() {
		request('regenerate');
	});

	var ranges = wizard.querySelectorAll('[data-heatmap-field]');
	for (var i = 0; i < ranges.length; i++) {
		ranges[i].oninput = function() {
			var number = wizard.querySelector('[data-heatmap-number="' + this.getAttribute('data-heatmap-field') + '"]');
			if (number) {
				number.value = this.value;
			}
			request('preview');
		};
	}
	if (mapSelect) {
		mapSelect.onchange = function() { request('preview'); };
	}
	syncFieldsFromConfig(currentConfig);
	if (activeMap()) {
		request('preview');
	}
}
