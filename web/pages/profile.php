<?php

function renderProfileTable($titleKey, $query)
{
	global $db;

	echo '<p>' . eHtml(t($titleKey)) . '<table><tr><td>' .
		eHtml(t('profile.table.origin')) . '</td><td>' .
		eHtml(t('profile.table.count')) . '</td><td>' .
		eHtml(t('profile.table.total_time')) . '</td><td>' .
		eHtml(t('profile.table.avg_time')) . '</td></tr>';

	$result = $db->query($query);
	while ($rowdata = $db->fetch_array($result)) {
		echo '<tr><td>' . eHtml($rowdata['source']) . '</td><td>' . eHtml($rowdata['run_count']) .
			'</td><td>' . eHtml($rowdata['run_time']) . '</td><td>' . eHtml($rowdata['avg_rt']) . '</td></tr>';
	}

	echo '</table>';
}

if (!empty($_REQUEST['reset'])) {
	$db->query("delete from hlstats_sql_web_profile");
	$db->query("delete from hlstats_sql_daemon_profile");
	die(t('profile.reset_done'));
}

	echo '<h3>' . eHtml(t('profile.web_performance')) . '</h3>';
	renderProfileTable(
		'profile.top_queries_by_count',
		"select *, (run_time/run_count) as avg_rt from hlstats_sql_web_profile order by run_count desc limit 20"
	);
	renderProfileTable(
		'profile.top_queries_by_total_time',
		"select *, (run_time/run_count) as avg_rt from hlstats_sql_web_profile order by run_time desc limit 20"
	);
	renderProfileTable(
		'profile.top_queries_by_avg_time',
		"select *, (run_time/run_count) as avg_rt from hlstats_sql_web_profile order by avg_rt desc limit 20"
	);

	echo '<hr>';

	echo '<h3>' . eHtml(t('profile.daemon_performance')) . '</h3>';
	renderProfileTable(
		'profile.top_queries_by_count',
		"select *, (run_time/run_count) as avg_rt from hlstats_sql_daemon_profile order by run_count desc limit 20"
	);
	renderProfileTable(
		'profile.top_queries_by_total_time',
		"select *, (run_time/run_count) as avg_rt from hlstats_sql_daemon_profile order by run_time desc limit 20"
	);
	renderProfileTable(
		'profile.top_queries_by_avg_time',
		"select *, (run_time/run_count) as avg_rt from hlstats_sql_daemon_profile order by avg_rt desc limit 20"
	);

?>
