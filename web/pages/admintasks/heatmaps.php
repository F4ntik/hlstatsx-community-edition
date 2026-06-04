<?php

if (!defined('IN_HLSTATS')) {
	die(localized_direct_access_message());
}

if ($auth->userdata['acclevel'] < 80) {
	die(localized_access_denied_message());
}

$includeRoot = preg_match('/^([A-Za-z]:)?[\/\\\\]/', INCLUDE_PATH)
	? INCLUDE_PATH
	: dirname(__DIR__, 2) . '/' . ltrim(INCLUDE_PATH, './');
require_once $includeRoot . '/heatmap_points.php';

$selectedGame = heatmap_clean_token($game ?? '');
$container = require dirname(__DIR__, 2) . '/bootstrap.php';
$pdo = $container->get('pdo');
$maps = $selectedGame === '' ? array() : heatmap_fetch_known_maps($pdo, $selectedGame);
$defaultMap = count($maps) ? $maps[0] : '';
?>

<div class="heatmap-admin-wizard" data-heatmap-admin="1" data-heatmap-game="<?php echo eHtml($selectedGame); ?>" data-heatmap-map="<?php echo eHtml($defaultMap); ?>">
	<p><?php echo eHtml(t('admin.task.heatmaps.intro')); ?></p>
	<div class="heatmap-admin-controls">
		<label>
			<?php echo eHtml(t('literal.map')); ?>
			<select data-heatmap-admin-map="1">
<?php foreach ($maps as $mapName): ?>
				<option value="<?php echo eHtml($mapName); ?>"><?php echo eHtml($mapName); ?></option>
<?php endforeach; ?>
			</select>
		</label>
		<label>
			<?php echo eHtml(t('admin.task.heatmaps.new_map')); ?>
			<input type="text" maxlength="64" data-heatmap-admin-new-map="1" />
		</label>
		<button type="button" data-heatmap-admin-load="1"><?php echo eHtml(t('admin.task.heatmaps.load')); ?></button>
	</div>

	<div class="heatmap-admin-grid">
		<div class="heatmap-viewer heatmap-viewer-admin">
			<div class="heatmap-canvas-wrap">
				<img class="heatmap-map-base" src="<?php echo IMAGE_PATH; ?>/nomap.png" alt="" />
				<canvas class="heatmap-overlay" aria-hidden="true"></canvas>
				<div class="heatmap-status" aria-live="polite"></div>
				<div class="heatmap-tooltip"></div>
			</div>
			<div class="heatmap-actions">
				<button type="button" class="heatmap-toggle is-active" data-heatmap-toggle="1"><?php echo eHtml(t('literal.heatmap')); ?></button>
			</div>
		</div>

		<div class="heatmap-admin-panel">
			<label>xoffset <input type="range" min="-16000" max="16000" step="1" data-heatmap-field="xoffset" /><input type="number" data-heatmap-number="xoffset" /></label>
			<label>yoffset <input type="range" min="-16000" max="16000" step="1" data-heatmap-field="yoffset" /><input type="number" data-heatmap-number="yoffset" /></label>
			<label>scale <input type="range" min="0.1" max="64" step="0.01" data-heatmap-field="scale" /><input type="number" step="0.01" data-heatmap-number="scale" /></label>
			<label>crop x <input type="number" data-heatmap-number="cropx1" /></label>
			<label>crop y <input type="number" data-heatmap-number="cropy1" /></label>
			<label>crop w <input type="number" data-heatmap-number="cropx2" /></label>
			<label>crop h <input type="number" data-heatmap-number="cropy2" /></label>
			<label><input type="checkbox" data-heatmap-check="flipx" /> flipx</label>
			<label><input type="checkbox" data-heatmap-check="flipy" /> flipy</label>
			<label><input type="checkbox" data-heatmap-check="rotate" /> rotate</label>
			<label><?php echo eHtml(t('admin.task.heatmaps.renderer')); ?>
				<select data-heatmap-number="renderer">
					<option value="thermal">thermal</option>
					<option value="semantic">semantic</option>
				</select>
			</label>
			<label><?php echo eHtml(t('admin.task.heatmaps.normalization')); ?>
				<select data-heatmap-number="normalization">
					<option value="sqrt">sqrt</option>
					<option value="linear">linear</option>
					<option value="log">log</option>
				</select>
			</label>
			<textarea data-heatmap-overview="1" placeholder="overview .txt"></textarea>
			<div class="heatmap-admin-buttons">
				<input type="file" accept="image/jpeg" data-heatmap-map-image="1" />
				<input type="file" accept=".txt,text/plain" data-heatmap-overview-file="1" />
				<button type="button" data-heatmap-admin-upload="1"><?php echo eHtml(t('admin.task.heatmaps.upload')); ?></button>
				<button type="button" data-heatmap-admin-preview="1"><?php echo eHtml(t('admin.task.heatmaps.preview')); ?></button>
				<button type="button" data-heatmap-admin-save="1"><?php echo eHtml(t('admin.task.heatmaps.save')); ?></button>
				<button type="button" data-heatmap-admin-regenerate="1"><?php echo eHtml(t('admin.task.heatmaps.regenerate')); ?></button>
			</div>
			<pre class="heatmap-admin-log" data-heatmap-admin-log="1"></pre>
		</div>
	</div>
</div>
