<?php
/*
HLstatsX Community Edition - Real-time player and clan rankings and statistics
Copyleft (L) 2008-20XX Nicholas Hastings (nshastings@gmail.com)
http://www.hlxcommunity.com

HLstatsX Community Edition is a continuation of 
ELstatsNEO - Real-time player and clan rankings and statistics
Copyleft (L) 2008-20XX Malte Bayer (steam@neo-soft.org)
http://ovrsized.neo-soft.org/

ELstatsNEO is an very improved & enhanced - so called Ultra-Humongus Edition of HLstatsX
HLstatsX - Real-time player and clan rankings and statistics for Half-Life 2
http://www.hlstatsx.com/
Copyright (C) 2005-2007 Tobias Oetzel (Tobi@hlstatsx.com)

HLstatsX is an enhanced version of HLstats made by Simon Garner
HLstats - Real-time player and clan rankings and statistics for Half-Life
http://sourceforge.net/projects/hlstats/
Copyright (C) 2001  Simon Garner
            
This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

For support and installation notes visit http://www.hlxcommunity.com
*/

    if (!defined('IN_HLSTATS')) {
        die('Do not access this file directly.');
    }

	flush();
	$tblMaps = new Table(
		array
		(
			new TableColumn
			(
				'map',
				t('literal.map'),
				'width=22&align=left&link=' . urlencode("mode=mapinfo&amp;map=%k&amp;game=$game")
			),
			new TableColumn
			(
				'kills',
				t('literal.kills'),
				'width=7&align=right'
			),
			new TableColumn
			(
				'kpercent',
				'%',
				'width=6&sort=no&align=right&append=' . urlencode('%')
			),
			new TableColumn
			(
				'kpercent',
				t('literal.ratio'),
				'width=8&sort=no&type=bargraph'
			),
			new TableColumn
			(
				'deaths',
				t('literal.deaths'),
				'width=7&align=right'
			),
			new TableColumn
			(
				'dpercent',
				'%',
				'width=6&sort=no&align=right&append=' . urlencode('%')
			),
			new TableColumn
			(
				'dpercent',
				t('literal.ratio'),
				'width=8&sort=no&type=bargraph'
			),
			new TableColumn
			(
				'kpd',
				t('literal.kpd_cap'),
				'width=5&align=right'
			),
			new TableColumn
			(
				'headshots',
				t('literal.headshots'),
				'width=7&align=right'
			),
			new TableColumn
			(
				'hpercent',
				'%',
				'width=6&sort=no&align=right&append=' . urlencode('%')
			),
			new TableColumn
			(
				'hpercent',
				t('literal.ratio'),
				'width=8&sort=no&type=bargraph'
			),
			new TableColumn
			(
				'hpk',
				t('literal.hpk_cap'),
				'width=5&align=right'
			)
		),
		'map',
		'kpd',
		'kills',
		true,
		9999,
		'maps_page',
		'maps_sort',
		'maps_sortorder',
		'tabmaps',
		'desc',
		true
	);
	$result = $db->query
	("
		SELECT
			IF(hlstats_Events_Frags.map='', '(Unaccounted)', hlstats_Events_Frags.map) AS map,
			SUM(hlstats_Events_Frags.killerId = $player) AS kills,
			SUM(hlstats_Events_Frags.victimId = $player) AS deaths,
			IFNULL(ROUND(SUM(hlstats_Events_Frags.killerId = $player) / IF(SUM(hlstats_Events_Frags.victimId = $player) = 0, 1, SUM(hlstats_Events_Frags.victimId = $player)), 2), '-') AS kpd,
			ROUND(CONCAT(SUM(hlstats_Events_Frags.killerId = $player)) / $realkills * 100, 2) AS kpercent,
			ROUND(CONCAT(SUM(hlstats_Events_Frags.victimId = $player)) / $realdeaths * 100, 2) AS dpercent,
			SUM(hlstats_Events_Frags.killerId = $player AND hlstats_Events_Frags.headshot = 1) AS headshots,
			IFNULL(ROUND(SUM(hlstats_Events_Frags.killerId = $player AND hlstats_Events_Frags.headshot = 1) / SUM(hlstats_Events_Frags.killerId = $player), 2),'-') AS hpk,
			ROUND(CONCAT(SUM(hlstats_Events_Frags.killerId = $player AND hlstats_Events_Frags.headshot = 1)) / $realheadshots * 100, 2) AS hpercent
		FROM
			hlstats_Events_Frags
		WHERE
			hlstats_Events_Frags.killerId = '$player'
			OR hlstats_Events_Frags.victimId = '$player'
		GROUP BY
			hlstats_Events_Frags.map
		ORDER BY
			$tblMaps->sort $tblMaps->sortorder,
			$tblMaps->sort2 $tblMaps->sortorder
	");
	$numitems = $db->num_rows($result);
	if ($numitems > 0)
	{
?>
<div style="clear:both;padding-top:20px;"></div>
<?php
		printSectionTitle(t('literal.map_performance'));
		$tblMaps->draw($result, $numitems, 95);
?>
<br /><br />

<?php
	}

	$heatmapMaps = array();
	$heatmapResult = $db->query("
		SELECT
			events.map,
			SUM(events.kills) AS kills,
			SUM(events.deaths) AS deaths
		FROM
		(
			SELECT
				hef.map,
				COUNT(*) AS kills,
				0 AS deaths
			FROM
				hlstats_Events_Frags AS hef
				INNER JOIN hlstats_Servers AS hs ON hs.serverId = hef.serverId
				INNER JOIN hlstats_Games AS hg ON hg.code = hs.game
				INNER JOIN hlstats_Heatmap_Config AS hc ON hc.game = hg.realgame AND hc.map = hef.map
			WHERE
				hef.killerId = '$player'
				AND hs.game = '$game'
				AND hef.map <> ''
				AND hef.pos_x IS NOT NULL
				AND hef.pos_y IS NOT NULL
			GROUP BY
				hef.map
			UNION ALL
			SELECT
				hef.map,
				0 AS kills,
				COUNT(*) AS deaths
			FROM
				hlstats_Events_Frags AS hef
				INNER JOIN hlstats_Servers AS hs ON hs.serverId = hef.serverId
				INNER JOIN hlstats_Games AS hg ON hg.code = hs.game
				INNER JOIN hlstats_Heatmap_Config AS hc ON hc.game = hg.realgame AND hc.map = hef.map
			WHERE
				hef.victimId = '$player'
				AND hs.game = '$game'
				AND hef.map <> ''
				AND (
					(hef.pos_victim_x IS NOT NULL AND hef.pos_victim_y IS NOT NULL)
					OR (hef.pos_x IS NOT NULL AND hef.pos_y IS NOT NULL)
				)
			GROUP BY
				hef.map
		) AS events
		GROUP BY
			events.map
		ORDER BY
			(SUM(events.kills) + SUM(events.deaths)) DESC,
			events.map ASC
		LIMIT 20
	");

	while ($heatmapRow = $db->fetch_array($heatmapResult)) {
		$candidateMap = $heatmapRow['map'];
		$mapImage = getImage("/games/$game/maps/$candidateMap");
		if (!$mapImage) {
			continue;
		}
		$heatmapRow['image'] = $mapImage;
		$heatmapMaps[] = $heatmapRow;
	}

	if (count($heatmapMaps) > 0) {
		$defaultMap = $heatmapMaps[0]['map'];
		$defaultImage = $heatmapMaps[0]['image'];
		$endpoint = "heatmap_points.php?game=" . rawurlencode($game) . "&map=" . rawurlencode($defaultMap) . "&player=" . intval($player) . "&event=kills";
?>
<div style="clear:both;padding-top:20px;"></div>
<?php printSectionTitle(eHtml(t('literal.heatmap')) . ': ' . eHtml(t('literal.maps'))); ?>
<div class="heatmap-player-panel" data-heatmap-game="<?php echo eHtml($game); ?>" data-heatmap-player="<?php echo intval($player); ?>" data-heatmap-map="<?php echo eHtml($defaultMap); ?>" data-heatmap-current-event="kills">
	<div class="heatmap-player-controls">
		<label>
			<?php echo eHtml(t('literal.map')); ?>
			<select data-heatmap-map-select="1">
<?php
		foreach ($heatmapMaps as $heatmapMap) {
			$mapName = $heatmapMap['map'];
			$selected = ($mapName === $defaultMap) ? ' selected="selected"' : '';
			echo '<option value="' . eHtml($mapName) . '"' . $selected . '>' . eHtml($mapName) . ' (' . intval($heatmapMap['kills']) . '/' . intval($heatmapMap['deaths']) . ')</option>';
		}
?>
			</select>
		</label>
		<button type="button" class="heatmap-mode is-active" data-heatmap-event="kills"><?php echo eHtml(t('literal.kills')); ?></button>
		<button type="button" class="heatmap-mode" data-heatmap-event="deaths"><?php echo eHtml(t('literal.deaths')); ?></button>
		<button type="button" class="heatmap-mode" data-heatmap-event="both"><?php echo eHtml(t('literal.kills_deaths')); ?></button>
		<span class="heatmap-legend"><span class="heatmap-legend-kills"></span><?php echo eHtml(t('literal.kills')); ?> <span class="heatmap-legend-deaths"></span><?php echo eHtml(t('literal.deaths')); ?></span>
	</div>
	<div class="heatmap-viewer heatmap-viewer-player" data-heatmap-endpoint="<?php echo eHtml($endpoint); ?>">
		<div class="heatmap-canvas-wrap">
			<img class="heatmap-map-base" src="<?php echo eHtml($defaultImage['url']); ?>" alt="<?php echo eHtml($defaultMap); ?>" />
			<canvas class="heatmap-overlay" aria-hidden="true"></canvas>
			<div class="heatmap-status" aria-live="polite"></div>
			<div class="heatmap-tooltip"></div>
		</div>
		<div class="heatmap-actions">
			<button type="button" class="heatmap-toggle" data-heatmap-toggle="1"><?php echo eHtml(t('literal.heatmap')); ?></button>
		</div>
	</div>
</div>
<script type="text/javascript">
if (typeof setupInlineHeatmaps == 'function') {
	setupInlineHeatmaps();
}
</script>
<?php
	}
?>
