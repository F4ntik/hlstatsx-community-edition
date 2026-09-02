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
$csrfToken = heatmap_admin_session_csrf_token();
$adminLanguage = current_lang();
?>

<div class="heatmap-admin-wizard" data-heatmap-admin="1" data-heatmap-game="<?php echo eHtml($selectedGame); ?>" data-heatmap-map="<?php echo eHtml($defaultMap); ?>" data-heatmap-csrf="<?php echo eHtml($csrfToken); ?>" data-heatmap-lang="<?php echo eHtml($adminLanguage); ?>" data-heatmap-admin-text-all-floors="<?php echo eHtml(t('admin.task.heatmaps.all_floors')); ?>" data-heatmap-admin-text-remove-floor="<?php echo eHtml(t('admin.task.heatmaps.remove_floor')); ?>" data-heatmap-admin-text-diagnostic-window-invalid="<?php echo eHtml(t('admin.task.heatmaps.diagnostic_window_invalid')); ?>" data-heatmap-admin-text-preview-ready="<?php echo eHtml(t('admin.task.heatmaps.preview_ready')); ?>" data-heatmap-admin-text-saved="<?php echo eHtml(t('admin.task.heatmaps.saved')); ?>" data-heatmap-admin-text-uploaded="<?php echo eHtml(t('admin.task.heatmaps.uploaded')); ?>" data-heatmap-admin-text-load-before-save="<?php echo eHtml(t('admin.task.heatmaps.load_before_save')); ?>" data-heatmap-admin-text-landmarks-required="<?php echo eHtml(t('admin.task.heatmaps.landmarks_required')); ?>" data-heatmap-admin-text-registration-accepted="<?php echo eHtml(t('admin.task.heatmaps.registration_accepted')); ?>" data-heatmap-admin-text-candidate-refused="<?php echo eHtml(t('admin.task.heatmaps.candidate_refused')); ?>" data-heatmap-admin-text-registration-coverage="<?php echo eHtml(t('admin.task.heatmaps.registration_coverage')); ?>">
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
				<div class="heatmap-map-stage">
					<img class="heatmap-map-base" src="<?php echo IMAGE_PATH; ?>/nomap.png" alt="" />
					<canvas class="heatmap-overlay" aria-hidden="true"></canvas>
					<div class="heatmap-status" aria-live="polite"></div>
					<div class="heatmap-tooltip"></div>
				</div>
			</div>
			<div class="heatmap-actions">
				<button type="button" class="heatmap-toggle is-active" data-heatmap-toggle="1"><?php echo eHtml(t('literal.heatmap')); ?></button>
			</div>
		</div>

		<div class="heatmap-admin-panel">
			<label><?php echo eHtml(t('heatmap.x_offset')); ?> <input type="range" min="-16000" max="16000" step="1" data-heatmap-field="xoffset" /><input type="number" data-heatmap-number="xoffset" /></label>
			<label><?php echo eHtml(t('heatmap.y_offset')); ?> <input type="range" min="-16000" max="16000" step="1" data-heatmap-field="yoffset" /><input type="number" data-heatmap-number="yoffset" /></label>
			<label><?php echo eHtml(t('heatmap.scale')); ?> <input type="range" min="-332" max="600" step="1" data-heatmap-field="scale" data-heatmap-scale-slider="1" /><input type="number" min="0.1" max="64" step="0.01" data-heatmap-number="scale" /></label>
			<label><?php echo eHtml(t('heatmap.crop_x')); ?> <input type="number" data-heatmap-number="cropx1" /></label>
			<label><?php echo eHtml(t('heatmap.crop_y')); ?> <input type="number" data-heatmap-number="cropy1" /></label>
			<label><?php echo eHtml(t('heatmap.crop_width')); ?> <input type="number" data-heatmap-number="cropx2" /></label>
			<label><?php echo eHtml(t('heatmap.crop_height')); ?> <input type="number" data-heatmap-number="cropy2" /></label>
			<div class="heatmap-transform-controls">
				<input type="checkbox" class="heatmap-transform-state" data-heatmap-check="flipx" />
				<input type="checkbox" class="heatmap-transform-state" data-heatmap-check="flipy" />
				<input type="hidden" data-heatmap-number="rotate" />
				<button type="button" class="heatmap-transform-button" data-heatmap-toggle-check="flipx"><?php echo eHtml(t('heatmap.flip_x')); ?></button>
				<button type="button" class="heatmap-transform-button" data-heatmap-toggle-check="flipy"><?php echo eHtml(t('heatmap.flip_y')); ?></button>
				<button type="button" class="heatmap-transform-button" data-heatmap-rotate-step="1"><?php echo eHtml(t('heatmap.rotate')); ?> 90&deg;</button>
			</div>
			<label><?php echo eHtml(t('admin.task.heatmaps.renderer')); ?>
				<select data-heatmap-number="renderer">
					<option value="thermal">thermal</option>
					<option value="semantic">semantic</option>
					<option value="points">points</option>
				</select>
			</label>
			<label><?php echo eHtml(t('admin.task.heatmaps.normalization')); ?>
				<select data-heatmap-number="normalization">
					<option value="sqrt">sqrt</option>
					<option value="linear">linear</option>
					<option value="log">log</option>
				</select>
			</label>
			<label><?php echo eHtml(t('admin.task.heatmaps.floor')); ?>
				<select data-heatmap-admin-floor="1"><option value="all"><?php echo eHtml(t('admin.task.heatmaps.all_floors')); ?></option></select>
			</label>
			<label><?php echo eHtml(t('admin.task.heatmaps.event')); ?>
				<select data-heatmap-admin-event="1">
					<option value="both"><?php echo eHtml(t('admin.task.heatmaps.events_both')); ?></option>
					<option value="kills"><?php echo eHtml(t('literal.kills')); ?></option>
					<option value="deaths"><?php echo eHtml(t('literal.deaths')); ?></option>
				</select>
			</label>
			<fieldset class="heatmap-admin-diagnostic">
				<legend><?php echo eHtml(t('admin.task.heatmaps.diagnostic')); ?></legend>
				<label><?php echo eHtml(t('admin.task.heatmaps.diagnostic_from')); ?> <input type="datetime-local" data-heatmap-diagnostic-from="1" /></label>
				<label><?php echo eHtml(t('admin.task.heatmaps.diagnostic_to')); ?> <input type="datetime-local" data-heatmap-diagnostic-to="1" /></label>
				<p data-heatmap-diagnostic-counts="1" aria-live="polite"></p>
				<ol class="heatmap-admin-histogram" data-heatmap-z-histogram="1"></ol>
			</fieldset>
			<fieldset class="heatmap-admin-floors">
				<legend><?php echo eHtml(t('admin.task.heatmaps.floors')); ?></legend>
				<div class="heatmap-admin-floor-table-wrap">
					<table class="heatmap-admin-floor-table">
						<thead><tr><th><?php echo eHtml(t('admin.task.heatmaps.floor_id')); ?></th><th><?php echo eHtml(t('admin.task.heatmaps.floor_label_en')); ?></th><th><?php echo eHtml(t('admin.task.heatmaps.floor_label_ru')); ?></th><th><?php echo eHtml(t('admin.task.heatmaps.floor_z_min')); ?></th><th><?php echo eHtml(t('admin.task.heatmaps.floor_z_max')); ?></th><th></th></tr></thead>
						<tbody data-heatmap-floor-rows="1"></tbody>
					</table>
				</div>
				<button type="button" data-heatmap-floor-add="1"><?php echo eHtml(t('admin.task.heatmaps.add_floor')); ?></button>
				<button type="button" data-heatmap-floor-suggest="1"><?php echo eHtml(t('admin.task.heatmaps.use_suggestion')); ?></button>
			</fieldset>
			<textarea data-heatmap-overview="1" placeholder="<?php echo eHtml(t('heatmap.overview_placeholder')); ?>"></textarea>
			<div class="heatmap-admin-buttons">
				<input type="file" accept="image/jpeg" data-heatmap-map-image="1" />
				<input type="file" accept=".txt,text/plain" data-heatmap-overview-file="1" />
				<button type="button" data-heatmap-admin-upload="1"><?php echo eHtml(t('admin.task.heatmaps.upload')); ?></button>
				<button type="button" data-heatmap-admin-preview="1"><?php echo eHtml(t('admin.task.heatmaps.preview')); ?></button>
				<button type="button" data-heatmap-admin-save="1"><?php echo eHtml(t('admin.task.heatmaps.save')); ?></button>
			</div>
			<fieldset class="heatmap-admin-landmarks">
				<legend><?php echo eHtml(t('admin.task.heatmaps.landmarks')); ?></legend>
				<label><?php echo eHtml(t('admin.task.heatmaps.tolerance')); ?> <input type="number" min="1" max="200" step="1" value="10" data-heatmap-landmark-tolerance="1" /></label>
				<div class="heatmap-admin-floor-table-wrap"><table class="heatmap-admin-floor-table"><thead><tr><th scope="col"><?php echo eHtml(t('admin.task.heatmaps.world_x')); ?></th><th scope="col"><?php echo eHtml(t('admin.task.heatmaps.world_y')); ?></th><th scope="col"><?php echo eHtml(t('admin.task.heatmaps.pixel_x')); ?></th><th scope="col"><?php echo eHtml(t('admin.task.heatmaps.pixel_y')); ?></th><th scope="col"><?php echo eHtml(t('admin.task.heatmaps.holdout')); ?></th><th scope="col"><?php echo eHtml(t('admin.task.heatmaps.residual')); ?></th></tr></thead><tbody data-heatmap-landmark-rows="1">
				<?php for ($landmarkIndex = 0; $landmarkIndex < 6; $landmarkIndex++): ?><tr data-heatmap-landmark-row="1"><td><input type="number" aria-label="<?php echo eHtml(t('admin.task.heatmaps.world_x')); ?>" data-heatmap-landmark="worldX" /></td><td><input type="number" aria-label="<?php echo eHtml(t('admin.task.heatmaps.world_y')); ?>" data-heatmap-landmark="worldY" /></td><td><input type="number" aria-label="<?php echo eHtml(t('admin.task.heatmaps.pixel_x')); ?>" data-heatmap-landmark="pixelX" /></td><td><input type="number" aria-label="<?php echo eHtml(t('admin.task.heatmaps.pixel_y')); ?>" data-heatmap-landmark="pixelY" /></td><td><input type="checkbox" aria-label="<?php echo eHtml(t('admin.task.heatmaps.holdout')); ?>" data-heatmap-landmark="holdout"<?php echo $landmarkIndex >= 4 ? ' checked="checked"' : ''; ?> /></td><td data-heatmap-landmark-residual="1">—</td></tr><?php endfor; ?>
				</tbody></table></div>
				<button type="button" data-heatmap-landmark-apply="1"><?php echo eHtml(t('admin.task.heatmaps.apply_candidate')); ?></button>
				<p data-heatmap-landmark-status="1" aria-live="polite"></p>
			</fieldset>
			<p class="heatmap-admin-deployment" data-heatmap-deployment-note="1"><?php echo eHtml(t('admin.task.heatmaps.deployment')); ?></p>
			<code class="heatmap-admin-deployment-command" data-heatmap-deployment-command="1">$env:PYTHONPATH='scripts'
rtk python -m hlstats_py.heatmaps --game &lt;validated-game&gt; --map &lt;validated-map&gt; --disablecache</code>
			<div class="heatmap-admin-log" data-heatmap-admin-log="1" role="status" aria-live="polite"></div>
		</div>
	</div>
</div>
