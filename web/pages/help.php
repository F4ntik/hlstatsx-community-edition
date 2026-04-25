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

	global $game;
	$resultGames = $db->query
	("
		SELECT
			hlstats_Games.code,
			hlstats_Games.name
		FROM
			hlstats_Games
		WHERE
			hlstats_Games.hidden = '0'
		ORDER BY
			hlstats_Games.name ASC 
		LIMIT
			0,
			1
	");
	list($game) = $db->fetch_row($resultGames);
// Help
	pageHeader
	(
		array(t('literal.help')),
		array(t('literal.help') => '')
	);
?>

<div class="block">
	<?php printSectionTitle(t('literal.questions')); ?>
	<ol>
		<li>
			<a href="#players"><?php echo eHtml(t('literal.help_q1')); ?></a><br />
		</li>
		<li>
			<a href="#points"><?php echo eHtml(t('literal.help_q2')); ?></a><br />
		</li>
		<li>
			<a href="#weaponmods"><?php echo eHtml(t('literal.help_q3')); ?></a><br />
		</li>
		<li>
			<a href="#set"><?php echo eHtml(t('literal.help_q4')); ?></a><br />
		</li>
		<li>
			<a href="#hideranking"><?php echo eHtml(t('literal.help_q5')); ?></a>
		</li>
	</ol>

	<?php printSectionTitle(t('literal.answers')); ?>

	<div style="margin-left:2%;">
		<h1 class="fTitle" style="padding-top:10px;"><a name="players">1. <?php echo eHtml(t('literal.help_q1')); ?></a></h1><br /><br />
			<?php
				if ($g_options['Mode'] == 'NameTrack')
				{
			?>
			<?php echo eHtml(t('literal.help_intro_name')); ?><br /><br />
			<?php
				}
				else
				{
					if ($g_options['Mode'] == 'LAN')
					{
						$uniqueid = t('search.ip_address');
						$uniqueid_plural = t('search.ip_addresses');
			?>
			<?php echo eHtml(t('literal.help_intro_ip')); ?><br /><br />
			<?php
					}
					else
					{
						$uniqueid = t('search.unique_id');
						$uniqueid_plural = t('search.unique_ids');
			?>
			<?php echo eHtml(t('literal.help_intro_uid')); ?><br /><br />
			<?php
					}
			?>
			<?php echo eHtml(t('literal.help_aliases')); ?><br /><br />
			<?php echo eHtml(t('literal.help_same_name')); ?> <?php echo eHtml($uniqueid); ?>) <?php echo eHtml(t('literal.help_same_name_tail')); ?><br /><br />
			<?php
				echo t('literal.help_search_sentence', array(
					'url' => eHtml($g_options['scripturl'] . '?mode=search'),
					'uniqueid' => eHtml($uniqueid),
				));
			?><br /><br />
			<?php
				}
			?>
			<h1 class="fTitle" style="padding-top:10px;"><a name="points">2. <?php echo eHtml(t('literal.help_q2')); ?></a></h1><br /><br />
			<?php echo eHtml(t('literal.help_points_1')); ?><br /><br />
			<?php echo eHtml(t('literal.help_points_2')); ?><br /><br />
			<?php echo eHtml(t('literal.help_points_3')); ?><br /><br />
			<pre> Killer Points = Killer Points + (Victim Points / Killer Points)
				 &times; Weapon Modifier &times; 5

 Victim Points = Victim Points - (Victim Points / Killer Points)
				 &times; Weapon Modifier &times; 5</pre><br /><br />
			<?php echo eHtml(t('literal.help_points_4')); ?><br /><br />
			<a name="actions" />
			<?php
				$yesText = $db->escape(t('literal.yes'));
				$noText = $db->escape(t('literal.no'));
				$tblActions = new Table
				(
					array
					(
						new TableColumn
						(
							'gamename',
							t('ui.game'),
							'width=24&sort=no'
						),
						new TableColumn
						(
							'for_PlayerActions',
							t('literal.player_action'),
							'width=4&sort=no&align=center'
						),
						new TableColumn
						(
							'for_PlayerPlayerActions',
							t('literal.plyrplyr_action'),
							'width=4&sort=no&align=center'
						),
						new TableColumn
						(
							'for_TeamActions',
							t('literal.team_action'),
							'width=4&sort=no&align=center'
						),
						new TableColumn
						(
							'for_WorldActions',
							t('literal.world_action'),
							'width=4&sort=no&align=center'
						),
						new TableColumn
						(
							'description',
							t('literal.action'),
							'width=33'
						),
						new TableColumn
						(
							's_reward_player',
							t('literal.player_reward'),
							'width=12'
						),
						new TableColumn
						(
							's_reward_team',
							t('literal.team_reward'),
							'width=15'
						)
					),
					'id',
					'description',
					's_reward_player',
					false,
					9999,
					'act_page',
					'act_sort',
					'act_sortorder',
					'actions',
					'asc'
				);
				$result = $db->query
				("
					SELECT
						hlstats_Games.name AS gamename,
						hlstats_Actions.description,
						IF(SIGN(hlstats_Actions.reward_player) > 0, CONCAT('+', hlstats_Actions.reward_player), hlstats_Actions.reward_player) AS s_reward_player,
						IF(hlstats_Actions.team != '' AND hlstats_Actions.reward_team != 0,
						IF(SIGN(hlstats_Actions.reward_team) >= 0, CONCAT(hlstats_Teams.name, ' +', hlstats_Actions.reward_team), CONCAT(hlstats_Teams.name, ' ', hlstats_Actions.reward_team)), '') AS s_reward_team,
						IF(for_PlayerActions='1', '$yesText', '$noText') AS for_PlayerActions,
						IF(for_PlayerPlayerActions='1', '$yesText', '$noText') AS for_PlayerPlayerActions,
						IF(for_TeamActions='1', '$yesText', '$noText') AS for_TeamActions,
						IF(for_WorldActions='1', '$yesText', '$noText') AS for_WorldActions
					FROM
						hlstats_Actions
					INNER JOIN
						hlstats_Games
					ON
						hlstats_Games.code = hlstats_Actions.game
						AND hlstats_Games.hidden = '0'
					LEFT JOIN
						hlstats_Teams
					ON
						hlstats_Teams.code = hlstats_Actions.team
						AND hlstats_Teams.game = hlstats_Actions.game
					ORDER BY
						hlstats_Actions.game ASC,
						$tblActions->sort $tblActions->sortorder,
						$tblActions->sort2 $tblActions->sortorder
				");
				$numitems = $db->num_rows($result);
				$tblActions->draw($result, $numitems, 90, 'center');
			?><br /><br />
			<strong><?php echo eHtml(t('literal.help_note')); ?></strong> <?php echo eHtml(t('literal.help_note_rewards')); ?><br /><br />
			<h1 class="fTitle" style="padding-top:10px;"><a name="weaponmods">3. <?php echo eHtml(t('literal.help_q3')); ?></a></h1><br /><br />
			<?php echo eHtml(t('literal.help_weaponmods')); ?><br /><br />
			<a name="weapons"></a>
			<?php
				$tblWeapons = new Table
				(
					array
					(
						new TableColumn
						(
							'gamename',
							t('ui.game'),
							'width=24&sort=no'
						),
						new TableColumn
						(
							'code',
							t('literal.weapon'),
							'width=14'
						),
						new TableColumn
						(
							'name',
							t('literal.name'),
							'width=50'
						),
						new TableColumn
						(
							'modifier',
							t('literal.points_modifier'),
							'width=12'
						)
					),
					'weaponId',
					'modifier',
					'code',
					false,
					9999,
					'weap_page',
					'weap_sort',
					'weap_sortorder',
					'weapons',
					'desc'
				);
				$result = $db->query
				("
					SELECT
						hlstats_Games.name AS gamename,
						hlstats_Weapons.code,
						hlstats_Weapons.name,
						hlstats_Weapons.modifier
					FROM
						hlstats_Weapons
					INNER JOIN
						hlstats_Games
					ON
						hlstats_Games.code = hlstats_Weapons.game
						AND hlstats_Games.hidden = '0'
					ORDER BY
						hlstats_Weapons.game ASC,
						$tblWeapons->sort $tblWeapons->sortorder,
						$tblWeapons->sort2 $tblWeapons->sortorder
				");
				$numitems = $db->num_rows($result);
				$tblWeapons->draw($result, $numitems, 90, "center");
			?><br /><br />
			<h1 class="fTitle" style="padding-top:10px;"><a name="set">4. <?php echo eHtml(t('literal.help_q4')); ?></a></h1><br /><br />
			<?php echo eHtml(t('literal.help_set_1')); ?><br /><br />
			<?php echo eHtml(t('literal.help_set_2')); ?><br /><br />
			<?php echo eHtml(t('literal.help_set_3')); ?>
			<ul>
				<li><strong>realname</strong><br />
					<?php echo eHtml(t('literal.help_realname')); ?><br />
					Example: &nbsp; <strong>/hlx_set realname Joe Bloggs</strong><br /><br />
				</li>
			
				<li><strong>email</strong><br />
					<?php echo eHtml(t('literal.help_email')); ?><br />
					Example: &nbsp; <strong>/hlx_set email joe@joebloggs.com</strong><br /><br />
				</li>
				
				<li><strong>homepage</strong><br />
					<?php echo eHtml(t('literal.help_homepage')); ?><br />
					Example: &nbsp; <strong>/hlx_set homepage http://www.joebloggs.com/</strong><br /><br />
				</li>
			</ul>
			<strong><?php echo eHtml(t('literal.help_note')); ?></strong> <?php echo eHtml(t('literal.help_console')); ?><br /><br /><?php echo eHtml(t('literal.help_console_tail')); ?><br /><br />
			<h1 class="fTitle" style="padding-top:10px;"><a name="hideranking">5. <?php echo eHtml(t('literal.help_q5')); ?></a></h1><br /><br />
			<?php echo eHtml(t('literal.help_hideranking_toggle')); ?><br /><br />
			<?php
				echo t('literal.help_find_yourself', array(
					'url' => eHtml($g_options['scripturl'] . '?mode=search'),
				));
			?>
	</div>
</div>
