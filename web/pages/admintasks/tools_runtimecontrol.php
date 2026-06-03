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
        die(localized_direct_access_message());
    }

	if ($auth->userdata["acclevel"] < 80) {
        die(localized_access_denied_message());
	}
?>

&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" ><strong>&nbsp;<?php echo $task->title; ?></strong>

<?php

    $commands = array(
        array(
            'name' => t('admin.task.tools_runtimecontrol.command.reload_configuration'),
            'cmd' => 'RELOAD',
        ),
        array(
            'name' => t('admin.task.tools_runtimecontrol.command.stop_runtime'),
            'cmd' => 'KILL',
        ),
    );

    if (isset($_POST['confirm'])) {
        $host = isset($_POST['masterserver']) ? trim((string) $_POST['masterserver']) : 'localhost';
        $port = isset($_POST['port']) ? trim((string) $_POST['port']) : '';
        $commandIndex = isset($_POST['command']) ? (int) $_POST['command'] : -1;
        if (!isset($commands[$commandIndex])) {
            die(eHtml(t('admin.task.tools_runtimecontrol.error.invalid_command')));
        }
        $command = $commands[$commandIndex]['cmd'];
        if ($port === '' || !ctype_digit($port) || (int) $port === 0) {
            $port = '27500';
        } else {
            $port = (string) ((int) $port);
        }

		// Check if we're contacting a remote host -- if so, need proxy_key configured for this to work (die and throw an error if we're missing it)
		if (($host != "127.0.0.1") && ($host != "localhost")) 
		{
			if ($g_options['Proxy_Key'] == "") 
			{
                $settingsLink = '<a href="' . $g_options['scripturl'] . '?mode=admin&amp;task=options#options">' . eHtml(t('admin.task.tools_runtimecontrol.proxy_key_settings_link')) . '</a>';
                echo '<p><strong>' . eHtml(t('ui.warning')) . ':</strong> ' . eHtml(t('admin.task.tools_runtimecontrol.proxy_key_warning')) . '</p>';
                echo '<p>' . t('admin.task.tools_runtimecontrol.proxy_key_notice', array('link' => $settingsLink)) . '</p>';
				die();
			}
		}
		
		echo "<div style=\"margin-left: 50px;\"><ul>\n";      
        echo '<li>' . t(
            'admin.task.tools_runtimecontrol.progress.send_command',
            array(
                'host' => eHtml($host),
                'port' => eHtml($port),
            )
        ) . ' &mdash; ';
		$resolvedHost = gethostbyname($host);
		$socket = socket_create(AF_INET, SOCK_DGRAM, SOL_UDP);
		$packet = "";
		if ($g_options['Proxy_Key'])
		{
			$packet = "PROXY Key={$g_options['Proxy_Key']} PROXY C;".$command.";";
		}
		else
		{
			$packet = "C;".$command.";";
		}
		$bytes_sent = socket_sendto($socket, $packet, strlen($packet), 0, $resolvedHost, (int) $port);
        echo '<strong>' . eHtml((string) $bytes_sent) . '</strong> ' . eHtml(t('admin.task.tools_synchronize.progress.bytes_suffix')) . ' <strong>' . eHtml(t('admin.tools_reset.status.ok')) . '</strong></li>';

        echo '<li>' . eHtml(t('admin.task.tools_runtimecontrol.progress.waiting_for_backend_answer'));
		$recv_bytes = 0;
		$buffer     = "";
		$timeout    = 5;
		$answer     = "";
		$packets    = 0;
		$read       = array($socket);
		while (socket_select($read, $write = NULL, $except = NULL, $timeout) > 0) {
			$recv_bytes += socket_recvfrom($socket, $buffer, 2000, 0, $resolvedHost, $port);
			$answer     .= $buffer;
			$buffer     = "";
			$timeout    = "1";
			$packets++;
		}   


        echo ' ' . t(
            'admin.task.tools_runtimecontrol.progress.receiving_response',
            array(
                'bytes' => eHtml((string) $recv_bytes),
                'packets' => eHtml((string) $packets),
            )
        ) . ' <strong>' . eHtml(t('admin.tools_reset.status.ok')) . '</strong></li>';
      
		if ($packets>0) {
            echo '<li>' . t('admin.task.tools_runtimecontrol.progress.backend_answer', array('answer' => eHtml($answer))) . '</li>';
		} 
		else 
		{
            echo '<li><em>' . t(
                'admin.task.tools_runtimecontrol.progress.no_packets_received',
                array(
                    'host' => eHtml($host),
                    'port' => eHtml($port),
                )
            ) . '</em></li>';
		}
      
        echo '<li>' . eHtml(t('admin.task.tools_runtimecontrol.progress.close_connection'));
		socket_close($socket);
        echo '<strong>' . eHtml(t('admin.tools_reset.status.ok')) . '</strong></li>';
		echo "</ul></div>\n";
		
        echo '<img src="' . IMAGE_PATH . '/rightarrow.gif" /> <a href="' . $g_options['scripturl'] . '?mode=admin">' . eHtml(t('admin.task.tools_runtimecontrol.return_to_admin_center')) . '</a>';
		}
		else
		{
        
?>        

<p><?php echo eHtml(t('admin.task.tools_runtimecontrol.intro')); ?></p>

<form method="POST">

	<table class="data-table">
		<tr class="bg1">
            <td width="40%"><label for="masterserver"><?php echo eHtml(t('admin.task.tools_runtimecontrol.field.runtime_host')); ?></label><p><?php echo eHtml(t('admin.task.tools_runtimecontrol.help.runtime_host')); ?></p></td>
			<td><input type="text" name="masterserver" value="localhost"></td>
		</tr>
		<tr class="bg2">
            <td><label for="port"><?php echo eHtml(t('admin.task.tools_runtimecontrol.field.runtime_port')); ?></label><p><?php echo eHtml(t('admin.task.tools_runtimecontrol.help.runtime_port')); ?></p></td>
			<td><input type="text" name="port" value="27500" size="6"></td>
		</tr>
		<tr class="bg1">
            <td><label for="command"><?php echo eHtml(t('admin.task.tools_runtimecontrol.field.command')); ?></label><p><?php echo eHtml(t('admin.task.tools_runtimecontrol.help.command')); ?></p></td>
			<td><SELECT NAME="command"><?php
  $i = 0;
  foreach ($commands as $cmd) {
   echo '<OPTION VALUE="' . $i . '">' . eHtml($cmd["name"]);
   $i++;
  } 
?>
					</SELECT></td>
	</table>
	
	<input type="hidden" name="confirm" value="1">
	<div style="text-align: center; margin-top: 20px;">
        <input type="submit" value="  <?php echo eHtml(t('admin.task.tools_runtimecontrol.submit_button')); ?>  ">
	</div>
</form>

<?php
    }
?>    
