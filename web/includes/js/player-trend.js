(function (window) {
    'use strict';
    var document = window.document, ns = 'http://www.w3.org/2000/svg', sequence = 0;
    function svgNode(name, attrs, text) {
        var node = document.createElementNS(ns, name);
        Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
        if (text !== undefined) node.textContent = text;
        return node;
    }
    function mount(root) {
        if (root.getAttribute('data-trend-mounted')) return;
        var data;
        try { data = JSON.parse(root.getAttribute('data-player-trend')); } catch (error) { return; }
        if (!data || data.version !== 1 || !Array.isArray(data.rows) || !data.rows.length || data.rows.length > 30) return;
        var rows = data.rows, labels = data.labels, pane = root.querySelector('.player-trend__interactive');
        if (!pane || rows.some(function (row) {
            return !/^\d{4}-\d{2}-\d{2}$/.test(row.date) || !Number.isFinite(row.rating) || !Number.isFinite(row.change)
                || !Number.isFinite(Date.parse(row.date + 'T00:00:00Z'));
        })) return;
        var locale = data.locale === 'ru' ? 'ru-RU' : 'en-US';
        var numbers = new Intl.NumberFormat(locale, {maximumFractionDigits: 0});
        var dates = new Intl.DateTimeFormat(locale, {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
        var times = rows.map(function (row) { return Date.parse(row.date + 'T00:00:00Z'); });
        var selected = rows.length - 1, points = [], coordinates = [], crosshair, width;
        var gradientId = 'player-trend-background-' + (++sequence);
        var chart = svgNode('svg', {role: 'group', 'aria-label': root.getAttribute('aria-label')});
        var tooltip = document.createElement('p'); tooltip.className = 'player-trend__tooltip';
        tooltip.setAttribute('role', 'status'); tooltip.setAttribute('aria-live', 'polite');
        pane.appendChild(chart); pane.appendChild(tooltip);
        function description(index) {
            var row = rows[index];
            return dates.format(times[index]) + ' · ' + labels.rating + ': ' + numbers.format(row.rating)
                + ' · ' + labels.change + ': ' + (row.change > 0 ? '+' : '') + numbers.format(row.change);
        }
        function select(index) {
            selected = index; tooltip.textContent = description(index);
            points.forEach(function (pair, position) {
                pair.forEach(function (point) { point.setAttribute('r', position === selected ? 4 : 2); });
                pair[0].setAttribute('tabindex', position === selected ? '0' : '-1');
            });
            crosshair.setAttribute('x1', coordinates[index].x); crosshair.setAttribute('x2', coordinates[index].x);
        }
        function draw() {
            while (chart.firstChild) chart.removeChild(chart.firstChild);
            points = []; coordinates = [];
            width = Math.max(260, root.clientWidth - 16);
            chart.setAttribute('viewBox', '0 0 ' + width + ' 215');
            var left = 43, right = width - 46, top = 30, bottom = 188;
            var span = times[times.length - 1] - times[0], scales = {};
            function x(index) { return span ? left + (times[index] - times[0]) / span * (right - left) : (left + right) / 2; }
            ['rating', 'change'].forEach(function (key) {
                var values = rows.map(function (row) { return row[key]; });
                var low = Math.min.apply(null, values), high = Math.max.apply(null, values);
                if (key === 'change') { low = Math.min(0, low); high = Math.max(0, high); }
                var padding = Math.max(2, (high - low) * 0.1);
                low = Math.floor(low - padding); high = Math.ceil(high + padding);
                if (key === 'rating' && values.every(function (value) { return value >= 0; })) low = Math.max(0, low);
                var rawStep = (high - low) / 4, power = Math.pow(10, Math.floor(Math.log10(Math.max(1, rawStep))));
                var step = [1, 2, 5, 10].map(function (factor) { return factor * power; }).filter(function (value) { return value >= rawStep; })[0];
                var floor = Math.floor(low / step) * step;
                if (floor + 4 * step < high) step *= 2;
                low = Math.floor(low / step) * step; high = low + 4 * step;
                scales[key] = {low: low, high: high};
            });
            function y(key, value) { var scale = scales[key]; return bottom - (value - scale.low) / (scale.high - scale.low) * (bottom - top); }
            var defs = svgNode('defs'), gradient = svgNode('linearGradient', {id: gradientId, x2: '0%', y2: '100%'});
            gradient.appendChild(svgNode('stop', {offset: '0%', 'stop-color': '#303030'}));
            gradient.appendChild(svgNode('stop', {offset: '100%', 'stop-color': '#505050'}));
            defs.appendChild(gradient); chart.appendChild(defs);
            chart.appendChild(svgNode('rect', {x: left, y: top, width: right - left, height: bottom - top, fill: 'url(#' + gradientId + ')'}));
            chart.appendChild(svgNode('text', {x: 4, y: 15, 'class': 'player-trend__axis player-trend__change'}, labels.change));
            chart.appendChild(svgNode('text', {x: width - 4, y: 15, 'text-anchor': 'end', 'class': 'player-trend__axis player-trend__rating'}, labels.rating));
            for (var tick = 0; tick <= 4; tick++) {
                var ordinate = bottom - (bottom - top) * tick / 4;
                chart.appendChild(svgNode('line', {x1: left, y1: ordinate, x2: right, y2: ordinate, 'class': 'player-trend__grid'}));
                ['change', 'rating'].forEach(function (key) {
                    var scale = scales[key], value = scale.low + (scale.high - scale.low) * tick / 4;
                    chart.appendChild(svgNode('text', {x: key === 'change' ? left - 5 : right + 5, y: ordinate + 3, 'text-anchor': key === 'change' ? 'end' : 'start', 'class': 'player-trend__axis player-trend__' + key}, numbers.format(value)));
                });
            }
            chart.appendChild(svgNode('line', {x1: left, y1: y('change', 0), x2: right, y2: y('change', 0), 'class': 'player-trend__zero'}));
            ['rating', 'change'].forEach(function (key) {
                var line = rows.map(function (row, index) { return (index ? 'L' : 'M') + x(index) + ',' + y(key, row[key]); }).join(' ');
                if (key === 'rating') chart.appendChild(svgNode('path', {d: line + ' L' + x(rows.length - 1) + ',' + bottom + ' L' + x(0) + ',' + bottom + ' Z', 'class': 'player-trend__area'}));
                chart.appendChild(svgNode('path', {d: line, 'class': 'player-trend__line player-trend__' + key}));
            });
            crosshair = svgNode('line', {y1: top, y2: bottom, 'class': 'player-trend__cursor'}); chart.appendChild(crosshair);
            rows.forEach(function (row, index) {
                coordinates.push({x: x(index), rating: y('rating', row.rating), change: y('change', row.change)});
                var pair = [];
                ['rating', 'change'].forEach(function (key) {
                    var point = svgNode('circle', {cx: x(index), cy: y(key, row[key]), r: 2, 'class': 'player-trend__point player-trend__' + key});
                    if (key === 'rating') {
                        point.setAttribute('tabindex', '-1'); point.setAttribute('role', 'button'); point.setAttribute('aria-label', description(index));
                        point.addEventListener('focus', function () { select(index); });
                        point.addEventListener('keydown', function (event) {
                            var next = index;
                            if (event.key === 'ArrowRight') next = Math.min(rows.length - 1, index + 1);
                            else if (event.key === 'ArrowLeft') next = Math.max(0, index - 1);
                            else if (event.key === 'Home') next = 0;
                            else if (event.key === 'End') next = rows.length - 1;
                            else if (event.key !== 'Enter' && event.key !== ' ') return;
                            event.preventDefault(); select(next); points[next][0].focus();
                        });
                    }
                    point.addEventListener('click', function () { select(index); points[index][0].focus(); });
                    pair.push(point); chart.appendChild(point);
                });
                points.push(pair);
            });
            chart.appendChild(svgNode('text', {x: 4, y: 207, 'class': 'player-trend__axis'}, dates.format(times[0])));
            if (rows.length > 1) chart.appendChild(svgNode('text', {x: width - 4, y: 207, 'text-anchor': 'end', 'class': 'player-trend__axis'}, dates.format(times[times.length - 1])));
            select(selected);
        }
        chart.addEventListener('pointermove', function (event) {
            var matrix = chart.getScreenCTM();
            if (!matrix) return;
            var pointer = chart.createSVGPoint(); pointer.x = event.clientX; pointer.y = event.clientY;
            pointer = pointer.matrixTransform(matrix.inverse());
            var px = pointer.x, py = pointer.y;
            var nearest = 0, distance = Infinity, vertical = Infinity;
            coordinates.forEach(function (point, index) {
                var dx = Math.abs(point.x - px), dy = Math.min(Math.abs(point.rating - py), Math.abs(point.change - py));
                if (dx < distance - 2 || (Math.abs(dx - distance) <= 2 && dy < vertical)) { nearest = index; distance = dx; vertical = dy; }
            });
            if (nearest !== selected) select(nearest);
        });
        pane.hidden = false; draw(); root.setAttribute('data-trend-mounted', '1');
        root.querySelector('.player-trend__data').open = false;
        if (typeof window.ResizeObserver === 'function') {
            var previousWidth = root.clientWidth;
            var observer = new window.ResizeObserver(function () {
                if (!root.isConnected) { observer.disconnect(); return; }
                if (root.clientWidth > 0 && root.clientWidth !== previousWidth) { previousWidth = root.clientWidth; draw(); }
            });
            observer.observe(root);
        }
    }
    function mountAll(scope) { (scope || document).querySelectorAll('[data-player-trend]').forEach(mount); }
    window.PlayerTrendGraph = {mountAll: mountAll};
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { mountAll(document); });
    else mountAll(document);
})(window);
