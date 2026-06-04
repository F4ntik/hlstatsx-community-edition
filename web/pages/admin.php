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
    die(t('admin.direct_access'));
}

global $db;

if (empty($game)) {
	$resultGames = $db->query("
        SELECT
            code,
            name
        FROM
            hlstats_Games
        WHERE
            hidden='0'
        ORDER BY
            name ASC 
        LIMIT 0,1

	");

	list($game) = $db->fetch_row($resultGames);
}

class Auth
{
	var $ok = false;
	var $error = false;

	var $username, $password, $savepass;
	var $sessionStart, $session;

	var $userdata = array();

	function __construct()
	{
		//@session_start();

        $authUsername = isset($_POST['authusername']) ? $_POST['authusername'] : '';
        $authPassword = isset($_POST['authpassword']) ? $_POST['authpassword'] : '';
        $authSavePass = isset($_POST['authsavepass']) ? $_POST['authsavepass'] : '';

		if (!empty($authUsername) && valid_request($authUsername, false)) {
			$this->username = valid_request($authUsername, false);
			$this->password = valid_request($authPassword, false);
			$this->savepass = valid_request($authSavePass, false);
			$this->sessionStart = 0;

			# clear POST vars so as not to confuse the receiving page
			unset($_POST);
			$_POST = array();

			$this->session = false;

			if ($this->checkPass() == true) {
				// if we have success, save it in this users SESSION
				$_SESSION['username'] = $this->username;
				$_SESSION['password'] = $this->password;
				$_SESSION['authsessionStart'] = time();
				$_SESSION['acclevel'] = $this->userdata['acclevel'];
			}
		} elseif (isset($_SESSION['loggedin'])) {
			$this->username = $_SESSION['username'];
			$this->password = $_SESSION['password'];
			$this->savepass = 0;
			$this->sessionStart = $_SESSION['authsessionStart'];
			$this->ok = true;
			$this->error = false;
			$this->session = true;
			
			if (!$this->checkPass()) {
				unset($_SESSION['loggedin']);
			}
		} else {
			$this->ok = false;
			$this->error = false;

			$this->session = false;

			$this->printAuth();
		}
	}

	function checkPass()
	{
		global $db;

		$db->query("
            SELECT
                *
            FROM
                hlstats_Users
            WHERE
                username = '$this->username'
            LIMIT 1
        ");

		if ($db->num_rows() == 1)
		{
			// The username is OK

			$this->userdata = $db->fetch_array();
			$db->free_result();

			if (md5($this->password) == $this->userdata["password"])
			{
				// The username and the password are OK

				$this->ok = true;
				$this->error = false;
				$_SESSION['loggedin']=1;
				if ($this->sessionStart > (time() - 3600))
				{
					// Valid session, update session time & display the page
					$this->doCookies();
					return true;
				}
				elseif ($this->sessionStart)
				{
					// A session exists but has expired
					if ($this->savepass)
					{
						// They selected 'Save my password' so we just
						// generate a new session and show the page.
						$this->doCookies();
						return true;
					}
					else
					{
						$this->ok = false;
						$this->error = t('admin.session_expired');
						$this->password = '';

						$this->printAuth();
						return false;
					}
				}
				elseif (!$this->session)
				{
					// No session and no cookies, but the user/pass was
					// POSTed, so we generate cookies.
					$this->doCookies();
					return true;
				}
				else
				{
					// No session, user/pass from a cookie, so we force auth
					$this->printAuth();
					return false;
				}
			}
			else
			{
				// The username is OK but the password is wrong

				$this->ok = false;
				if ($this->session)
				{
					// Cookie without 'Save my password' - not an error
					$this->error = false;
				}
				else
				{
					$this->error = t('admin.password_incorrect');
				}
				$this->password = '';
				$this->printAuth();
			}
		}
		else
		{
			// The username is wrong
			$this->ok = false;
			$this->error = t('admin.username_invalid');
			$this->printAuth();
		}
	}

	function doCookies()
	{
		return;
		setcookie('authusername', $this->username, time() + 31536000, '', '', 0);

		if ($this->savepass)
		{
			setcookie('authpassword', $this->password, time() + 31536000, '', '', 0);
		}
		else
		{
			setcookie('authpassword', $this->password, 0, '', '', 0);
		}
		setcookie('authsavepass', $this->savepass, time() + 31536000, '', '', 0);
		setcookie('authsessionStart', time(), 0, '', '', 0);
	}

	function printAuth()
	{
		global $g_options;

		include (PAGE_PATH . '/adminauth.php');
	}
}

class AdminTask
{
	var $title = '';
	var $acclevel = 0;
	var $type = '';
	var $description = '';
	public $group;

	function __construct($title, $acclevel, $type = 'general', $description = '', $group = '')
	{
		$this->title = $title;
		$this->acclevel = $acclevel;
		$this->type = $type;
		$this->description = $description;
		$this->group = $group;
	}
}

class EditList
{
	var $columns;
	var $keycol;
	var $table;
	var $deleteCallback;
	var $icon;
	var $showid;
	var $drawDetailsLink;
	var $DetailsLink;

	var $errors;
	var $newerror;

	var $helpTexts;
	var $helpKey;
	var $helpDIV;

	function __construct($keycol, $table, $icon, $showid = true, $drawDetailsLink = false, $DetailsLink = '', $deleteCallback = null)
	{
		$this->keycol = $keycol;
		$this->table = $table;
		$this->icon = $icon;
		$this->showid = $showid;
		$this->drawDetailsLink = $drawDetailsLink;
		$this->DetailsLink = $DetailsLink;
		$this->helpKey = '';
		$this->deleteCallback = $deleteCallback;
	}

	function setHelp($div, $key, $texts)
	{
		$this->helpDIV = $div;
		$this->helpKey = $key;
		$this->helpTexts = $texts;

		$returnstr = '';

		if ($this->helpKey != '')
		{
			$returnstr .= "<script type='text/javascript'>\n";
			$returnstr .= "var texts = new Array();\n";
			foreach (array_keys($this->helpTexts) as $key)
			{
				$value = $this->helpTexts[$key];
				// $value = nl2br(htmlspecialchars($this->helpTexts[$key]));
				$value = str_replace('"', "'", $value);
				//$value = preg_replace("/\"/", "'", $value);
				$value = preg_replace("/[\r\n]/", " ", $value);
				$returnstr .= "texts[\"" . $key . "\"] = \"" . $value . "\";\n";
			}

			$returnstr .= "\n\nfunction showHelp (keyname) {\n";
			$returnstr .= "document.getElementById('" . $this->helpDIV . "').innerHTML=texts[keyname];\n";
			$returnstr .= "document.getElementById('" . $this->helpDIV . "').style.visibility='visible';\n";
			$returnstr .= "}\n";
			$returnstr .= "\n\nfunction hideHelp () {\n";
			$returnstr .= "document.getElementById('" . $this->helpDIV . "').style.visibility='hidden';\n";
			$returnstr .= "}\n";
			$returnstr .= "</script>\n";

			$returnstr .= '<div class="helpwindow" ID="' . $this->helpDIV . '">' . eHtml(t('admin.no_help_text')) . '</div>';

		}
		return $returnstr;
	}

	function update()
	{
		global $db;

		$okcols = 0;
		foreach ($this->columns as $col) {
			$value = (!empty($_POST["new_$col->name"])) ? $_POST["new_$col->name"] : '';
			//  legacy code that should have never been here. these should never be html-escaped in the db.
			//  if there's a problem with removing this, it needs to be fixed on the web/display end
			//  -psychonic
			//
			/*
			if ( $col->name != 'rcon_password' && $col->type != 'password' && $col->name != 'pattern')
			{
				$value = htmlspecialchars($value);
			}
			*/

			if ($value != '')
			{
				if ($col->type == 'ipaddress' && !preg_match('/^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$/', $value))
				{
					$this->errors[] = t('admin.editlist.error.invalid_ip_new_row', array('column' => translate_ui_literal($col->title)));
					$this->newerror = true;
					$okcols++;
				}
				else
				{
					if ($qcols)
					{
						$qcols .= ', ';
					}
					$qcols .= $col->name;

					if ($qvals)
					{
						$qvals .= ', ';
					}

					if ($col->type == 'password' && $col->name != 'rcon_password')
					{
						$value = md5($value);
					}
					$qvals .= "'" . $db->escape($value) . "'";

					if ($col->type != 'select' && $col->type != 'hidden' && $value != $col->datasource)
					{
						$okcols++;
					}
				}
			}
			elseif ($col->required)
			{
				$this->errors[] = t('admin.editlist.error.required_new_row', array('column' => translate_ui_literal($col->title)));
				$this->newerror = true;
			}
		}

		if ($okcols > 0 && !$this->errors)
		{
			$db->query("
					INSERT INTO
						$this->table
						(
							$qcols
						)
					VALUES
					(
						$qvals
					)");
		}
		elseif ($okcols == 0)
		{
			$this->errors = array();
			$this->newerror = false;
		}

		if (!is_array($_POST['rows']))
		{
			return true;
		}
		
		foreach ($_POST['rows'] as $row)
		{
			if (!empty($_POST[$row . '_delete'])) {
				if (!empty($this->deleteCallback) && is_callable($this->deleteCallback)) {
					call_user_func($this->deleteCallback, $row);
				}

				$db->query("
					DELETE FROM
						$this->table
					WHERE
						$this->keycol='" . $db->escape($row) . "'
				");
			}
			else
			{
				$rowerror = false;

				$query = "UPDATE $this->table SET ";
				$i = 0;
				foreach ($this->columns as $col)
				{
					if ($col->type == 'readonly')
					{
						continue;
					}

					$value = (!empty($_POST[$row . "_" . $col->name])) ? $_POST[$row . "_" . $col->name] : null;
					
					//  legacy code that should have never been here. these should never be html-escaped in the db.
					//  if there's a problem with removing this, it needs to be fixed on the web/display end
					//  -psychonic
					//
					/*
					if ( $col->name != 'rcon_password' && $col->type != 'password' && $col->name != 'pattern')
					{
						$value = htmlspecialchars($value);
					}
					*/

					if ($col->type == 'checkbox' && $value == ('' || null))
					{
						$value = '0';
					}

					if ($col->type == 'password' && ($value == '(encrypted)' || $value == t('admin.editlist.password_encrypted')))
					{
						continue;
					}

					if ($value == '' && $col->required)
					{
						$this->errors[] = t('admin.editlist.error.required_row', array('column' => translate_ui_literal($col->title), 'row' => $row));
						$rowerror = true;
					}
					elseif ($col->type == "ipaddress" && !preg_match("/^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$/", $value))
					{
						$this->errors[] = t('admin.editlist.error.invalid_ip_row', array('column' => translate_ui_literal($col->title), 'row' => $row));
						$rowerror = true;
					}

					if ($i > 0)
					{
						$query .= ', ';
					}

					if ($col->type == 'password' && $col->name != 'rcon_password')
					{
						$query .= $col->name . "='" . md5($value) . "'";
					}
					else
					{
						$query .= $col->name . "='" . $db->escape($value) . "'";
					}
					$i++;
				}
				$query .= " WHERE $this->keycol='" . $db->escape($row) . "'";

				if (!$rowerror)
				{
					$db->query($query);
				}
			}
		}

		if ($this->error()) {
			return false;
		}

        return true;
	}

	function draw($result, $draw_new = true)
	{
		global $g_options, $db;


?>
<table width="100%" border="0" cellspacing="0" cellpadding="0">

<tr valign="top" class="table_border">
	<td><table width="100%" border="0" cellspacing="1" cellpadding="4">

		<tr valign="bottom" class="head">
<?php
		echo '<td></td>';

		if ($this->showid)
		{
?>
			<td align="right" class="fSmall"><?php
			echo eHtml(t('search.id'));
?></td>
<?php
		}

		foreach ($this->columns as $col)
		{
			if ($col->type == 'hidden')
			{
				continue;
			}
			echo '<td class="fSmall">' . eHtml(translate_ui_literal($col->title)) . "</td>\n";
		}

		if ($this->drawDetailsLink)
		{
?>
			<td align="right" class="fSmall"><?php
			echo '';
?></td>
<?php
		}


?>
			<td align="center" class="fSmall"><?php
		echo eHtml(t('admin.editlist.delete'));
?></td>
		</tr>

<?php
		while ($rowdata = $db->fetch_array($result))
		{
			echo "\n<tr>\n";
			echo '<td align="center" class="bg1">';
			if  (file_exists(IMAGE_PATH . "/$this->icon.gif"))
			{
				echo '<img src="' . IMAGE_PATH . "/$this->icon.gif\" width=\"16\" height=\"16\" border=\"0\" alt=\"\" />";
			} 
			else 
			{
				echo '<img src="' . IMAGE_PATH . "/server.gif\" width=\"16\" height=\"16\" border=\"0\" alt=\"\" />";
			}
			echo "</td>\n";
			
			if ($this->showid)
			{
				echo '<td align="right" class="bg2 fSmall">' . $rowdata[$this->keycol] . "</td>\n";
			}

			$this->drawfields($rowdata, false, false);

			if ($this->drawDetailsLink)
			{
				global $gamecode;
?>
			<td align="center" class="bg2 fSmall"><?php
				echo "<a href='" . $g_options["scripturl"] . "?mode=admin&amp;game=$gamecode&amp;task=" . $this->DetailsLink . "&amp;key=" . $rowdata[$this->keycol] . "'><b>" . eHtml(t('admin.editlist.configure')) . "</b></a>";
?></td>
<?php
			}

?>
<td align="center" class="bg2"><input type="checkbox" name="<?php echo $rowdata[$this->keycol]; ?>_delete" value="1" /></td>
<?php echo "</tr>\n\n";
		}
?>

<tr>
<?php
		if ( $draw_new )
		{
			echo "<td class=\"bg1 fSmall\" align=\"center\">" . eHtml(t('admin.editlist.new')) . "</td>\n";

			if ($this->showid)
				echo "<td class=\"bg2 fSmall\" align=\"right\">" . "&nbsp;</td>\n";
	
			if ($this->newerror)
			{
				$this->drawfields($_POST, true, true);
			}
			else
			{
				$this->drawfields(array(), true);
			}

			echo "<td class=\"bg1\"></td>\n";
		}
?>
</tr>

		</table></td>
</tr>

</table><br /><br />
<?php
	}

	function drawfields($rowdata = array(), $new = false, $stripslashes = false)
	{
		global $g_options, $db;

		$i = 0;
		foreach ($this->columns as $col)
		{
			if ($new)
			{
				$keyval = 'new';
				$rowdata[$col->name] = $rowdata["new_$col->name"];
				if ($stripslashes)
					$rowdata[$col->name] = $rowdata[$col->name];
			}
			else
			{
				$keyval = $rowdata[$this->keycol];
				if ($stripslashes)
					$keyval = $keyval;

			}

			if ($col->type != 'hidden')
			{
				echo '<td class="bg1">';
			}

			if ($i == 0 && !$new)
			{
				echo '<input type="hidden" name="rows[]" value="' . htmlspecialchars($keyval) . '" />';
			}

			if ($col->maxlength < 1)
			{
				$col->maxlength = '';
			}

			switch ($col->type)
			{
				case 'select':
					unset($coldata);

					// for manual datasource in format "key/value;key/value" or "key;key"
					foreach (explode(';', $col->datasource) as $v)
					{
						$sections = preg_match_all('/\//', $v, $dsaljfdsaf);
						if ($sections == 2)
						{
							// for SQL datasource in format "table.column/keycolumn/where"
							list($col_table, $col_col) = explode('.', $v);
							list($col_col, $col_key, $col_where) = explode('/', $col_col);
							if ($col_where)
							{
								$col_where = "WHERE $col_where";
							}
							$col_result = $db->query("SELECT $col_key, $col_col FROM $col_table $col_where ORDER BY $col_col");
							$coldata = array();
							while (list($a, $b) = $db->fetch_row($col_result))
							{
								$coldata[$a] = $b;
							}
						}
						else if ($sections > 0)
						{
							list($a, $b) = explode('/', $v);
							$coldata[$a] = $b;
						}
						else
						{
							$coldata[$v] = $v;
						}
					}

					if ($col->width)
					{
						$width = ' style="width:' . $col->width * 5 . 'px"';
					}
					else
					{
						$width = '';
					}

					echo "<select name=\"" . $keyval . "_$col->name\"$width>\n";

					if (!$col->required)
					{
						echo "<option value=\"\"></option>\n";
					}

					$gotcval = false;

					foreach ($coldata as $k => $v)
					{
						if ($rowdata[$col->name] == $k)
						{
							$selected = ' selected="selected"';
							$gotcval = true;
						}
						else
						{
							$selected = '';
						}

						echo "<option value=\"$k\"$selected>$v</option>\n";
					}

					if (!$gotcval)
					{
						echo '<option value="' . $rowdata[$col->name] . '" selected="selected">' . $rowdata[$col->name] . "</option>\n";
					}

					echo '</select>';
					break;

				case 'checkbox':
					$selectedval = '1';
					$value = $rowdata[$col->name];

					if ($value == $selectedval)
					{
						$selected = ' checked="checked"';
					}
					else
					{
						$selected = '';
					}

					echo '<center><input type="checkbox" name="' . $keyval . "_$col->name\" value=\"$selectedval\"$selected /></center>";
					break;
					
				case 'hidden':
					echo '<input type="hidden" name="' . $keyval . "_$col->name\" value=\"" . htmlspecialchars($col->datasource) . '" />';
					break;
					
				case 'readonly':
					if (!$new)
					{
						echo html_entity_decode($rowdata[$col->name]);
						break;
					}
					/* else fall through to default */

				default:
					$onclick = '';
					if ($col->type == 'password') {
						$onclick = " onclick=\"if (this.value == '" . addslashes(t('admin.editlist.password_encrypted')) . "') this.value='';\"";
					}

					if ($col->datasource != '' && !isset($rowdata[$col->name]))
					{
						$value = $col->datasource;
					}
					else
					{
						$value = $rowdata[$col->name];
					}

					$onClick = '';
					if (!empty($this->helpKey) && !empty($rowdata[$this->helpKey])) {
						$onClick = "onmouseover=\"javascript:showHelp('" . strtolower($rowdata[$this->helpKey]) . "')\" onmouseout=\"javascript:hideHelp()\"";
					}

					if ($col->type == 'password' && $value == '(encrypted)') {
						$value = t('admin.editlist.password_encrypted');
					}

					$input_value = (!empty($value)) ? htmlentities(html_entity_decode($value), ENT_COMPAT, 'UTF-8') : "";

					echo "<input $onClick type=\"text\" name=\"" . $keyval . "_$col->name\" size=$col->width " . "value=\"" . $input_value . "\" class=\"textbox\"" . " maxlength=\"$col->maxlength\"$onclick />";
// doing htmlentities on something that we just decoded is because we need to encode them when we fill out a form, but we don't want to double encode them (some items like rcon are not encoded at all - but server names are)
			}

			if ($col->type != 'hidden')
			{
				echo "</td>\n";
			}

			$i++;
		}
	}

	function error()
	{
		if (is_array($this->errors))
		{
			return implode("<br /><br />\n\n", $this->errors);
		}
		else
		{
			return false;
		}
	}
}

class EditListColumn
{
	var $name;
	var $title;
	var $width;
	var $required;
	var $type;
	var $datasource;
	var $maxlength;

	function __construct($name, $title, $width = 20, $required = false, $type = 'text', $datasource = '', $maxlength = 0)
	{
		$this->name = $name;
		$this->title = $title;
		$this->width = $width;
		$this->required = $required;
		$this->type = $type;
		$this->datasource = $datasource;
		$this->maxlength = intval($maxlength);
	}
}

class PropertyPage
{
	var $table;
	var $keycol;
	var $keyval;
	var $propertygroups = array();

	function __construct($table, $keycol, $keyval, $groups)
	{
		$this->table = $table;
		$this->keycol = $keycol;
		$this->keyval = $keyval;
		$this->propertygroups = $groups;
	}

	function draw($data)
	{
		foreach ($this->propertygroups as $group)
		{
			$group->draw($data);
		}
	}

	function update()
	{
		global $db;

		$setstrings = array();
		foreach ($this->propertygroups as $group)
		{
			foreach ($group->properties as $prop)
			{
				if ($prop->name == 'name')
				{
					$value = $_POST[$prop->name];
					$search_pattern = array('/script/i', '/;/', '/%/');
					$replace_pattern = array('', '', '');
					$value = preg_replace($search_pattern, $replace_pattern, $value);
					$setstrings[] = $prop->name . "='" . $value . "'";
				}
				else
				{
                    $postValue = isset($_POST[$prop->name]) ? $_POST[$prop->name] : '';
					$setstrings[] = $prop->name . "='" . valid_request($postValue, 0) . "'";
				}
			}
		}

		$db->query("
            UPDATE
                " . $this->table . "
            SET
                " . implode(",\n", $setstrings) . "
            WHERE
                " . $this->keycol . "='" . $db->escape($this->keyval) . "'
        ");
	}
}

class PropertyPage_Group
{
	var $title = '';
	var $properties = array();

	function __construct($title, $properties)
	{
		$this->title = $title;
		$this->properties = $properties;
	}

	function draw($data)
	{
		global $g_options;
?>
<b><?php echo eHtml(translate_ui_literal($this->title)); ?></b><br />
<table width="100%" border="0" cellspacing="0" cellpadding="0">

<tr valign="top">
	<td><table width="100%" border="0" cellspacing="1" cellpadding="4">
<?php
		foreach ($this->properties as $prop)
		{
			$prop->draw($data[$prop->name]);
		}
?>
		</table></td>
</tr>

</table><br /><br />
<?php
	}
}

class PropertyPage_Property
{
	var $name;
	var $title;
	var $type;

	function __construct($name, $title, $type, $datasource = '')
	{
		$this->name = $name;
		$this->title = $title;
		$this->type = $type;
		$this->datasource = $datasource;
	}

	function draw($value)
	{
		global $g_options;
?>
<tr style="vertical-align:middle;">
	<td class="bg1" style="width:45%;"><?php
		echo eHtml(translate_ui_literal($this->title)) . ':';
?></td>
	<td class="bg1" style="width:55%;"><?php
		switch ($this->type)
		{
			case 'textarea':
				echo "<textarea name=\"$this->name\" cols=35 rows=4 wrap=\"virtual\">" . htmlspecialchars($value) . '</textarea>';
				break;

			case 'select':
				// for manual datasource in format "key/value;key/value" or "key;key"
				foreach (explode(';', $this->datasource) as $v)
				{
					if (preg_match('/\//', $v))
					{
						list($a, $b) = explode('/', $v);
						$coldata[$a] = $b;
					}
					else
					{
						$coldata[$v] = $v;
					}
				}

				echo getSelect($this->name, $coldata, $value);
				break;

			default:
				echo "<input type=\"text\" name=\"$this->name\" size=35 value=\"" . htmlspecialchars($value) . "\" class=\"textbox\" />";
				break;
		}
?>
</td>
</tr>
<?php
	}
}

function message($icon, $msg)
{
	global $g_options;
	$msg = translate_ui_literal($msg);
?>
		<table width="60%" border="0" cellspacing="0" cellpadding="0">

		<tr valign="top">
			<td width="40"><img src="<?php echo IMAGE_PATH . "/$icon"; ?>.gif" width="16" height="16" border="0" hspace="5" alt="" /></td>
			<td width="100%"><?php
	echo "<b>$msg</b>";
?></td>
		</tr>

		</table><br /><br />
<?php
}

$auth = new Auth;
if ($auth->ok === false) {
	return;
}

pageHeader(array(t('ui.admin')), array(t('ui.admin') => ''));

$selTask = isset($_GET['task']) ? valid_request($_GET['task'], false) : '';
$selGame = isset($_GET['game']) ? valid_request($_GET['game'], false) : '';
?>

<table width="100%" align="center" border="0" cellspacing="0" cellpadding="0">

<tr valign="top">
	<td><?php

// General Settings
$admintasks['options'] = new AdminTask(t('admin.task.options.title'), 80);
$admintasks['adminusers'] = new AdminTask(t('admin.task.adminusers.title'), 100);
$admintasks['games'] = new AdminTask(t('admin.task.games.title'), 80);
$admintasks['hostgroups'] = new AdminTask(t('admin.task.hostgroups.title'), 100);
$admintasks['clantags'] = new AdminTask(t('admin.task.clantags.title'), 80);
$admintasks['voicecomm'] = new AdminTask(t('admin.task.voicecomm.title'), 80);

// Game Settings
$admintasks['newserver'] = new AdminTask(t('admin.task.newserver.title'), 80, 'game');
$admintasks['servers'] = new AdminTask(t('admin.task.servers.title'), 80, 'game');
$admintasks['serversettings'] = new AdminTask('&nbsp;&nbsp;&nbsp;&gt;&gt;&nbsp;' . t('admin.task.serversettings.title'), 80, 'game');
$admintasks['actions'] = new AdminTask(t('literal.actions'), 80, 'game');
$admintasks['teams'] = new AdminTask(t('admin.task.teams.title'), 80, 'game');
$admintasks['roles'] = new AdminTask(t('literal.roles'), 80, 'game');
$admintasks['weapons'] = new AdminTask(t('literal.weapons'), 80, 'game');
$admintasks['heatmaps'] = new AdminTask(t('admin.task.heatmaps.title'), 80, 'game');
$admintasks['awards_weapons'] = new AdminTask(t('admin.task.awards_weapons.title'), 80, 'game');
$admintasks['awards_plyractions'] = new AdminTask(t('admin.task.awards_plyractions.title'), 80, 'game');
$admintasks['awards_plyrplyractions'] = new AdminTask(t('admin.task.awards_plyrplyractions.title'), 80, 'game');
$admintasks['awards_plyrplyractions_victim'] = new AdminTask(t('admin.task.awards_plyrplyractions_victim.title'), 80, 'game');
$admintasks['ranks'] = new AdminTask(t('admin.task.ranks.title'), 80, 'game');
$admintasks['ribbons'] = new AdminTask(t('admin.task.ribbons.title'), 80, 'game');

// Tools
$admintasks['tools_runtimecontrol'] = new AdminTask(t('admin.task.tools_runtimecontrol.title'), 80, 'tool', t('admin.task.tools_runtimecontrol.description'));
$admintasks['tools_editdetails'] = new AdminTask(t('admin.task.tools_editdetails.title'), 80, 'tool', t('admin.task.tools_editdetails.description'));
$admintasks['tools_adminevents'] = new AdminTask(t('admin.task.tools_adminevents.title'), 80, 'tool', t('admin.task.tools_adminevents.description'));
$admintasks['tools_ipstats'] = new AdminTask(t('admin.task.tools_ipstats.title'), 80, 'tool', t('admin.task.tools_ipstats.description'));
$admintasks['tools_optimize'] = new AdminTask(t('admin.task.tools_optimize.title'), 100, 'tool', t('admin.task.tools_optimize.description'));
//$admintasks['tools_synchronize'] = new AdminTask('Synchronize Statistics', 80, 'tool', 'Sychronize all players with the offical global ELstatsNEO banlist with catched VAC cheaters.');
$admintasks['tools_resetdbcollations'] = new AdminTask(t('admin.task.tools_resetdbcollations.title'), 100, 'tool', t('admin.task.tools_resetdbcollations.description'));

// Sub-Tools
$admintasks['tools_editdetails_player'] = new AdminTask(t('admin.task.tools_editdetails_player.title'), 80, 'subtool', t('admin.task.tools_editdetails_player.description'));
$admintasks['tools_editdetails_clan'] = new AdminTask(t('admin.task.tools_editdetails_clan.title'), 80, 'subtool', t('admin.task.tools_editdetails_clan.description'));

// Reset Tools
$admintasks['tools_reset'] = new AdminTask(t('admin.task.tools_reset.title'), 100, 'tool', t('admin.task.tools_reset.description'), 'reset');
$admintasks['tools_reset_2'] = new AdminTask(t('admin.task.tools_reset_2.title'), 100, 'tool', t('admin.task.tools_reset_2.description'), 'reset');

// Game Settings Tools
$admintasks['tools_settings_copy'] = new AdminTask(t('admin.task.tools_settings_copy.title'), 80, 'tool', t('admin.task.tools_settings_copy.description'), 'settingstool');


// Show Tool
if (!empty($admintasks[$selTask]) && ($admintasks[$selTask]->type == 'tool' || $admintasks[$selTask]->type == 'subtool'))
{
	$task = $admintasks[$selTask];

	$code = $selTask;
?>
&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width="9" height="6" alt="" /><b>&nbsp;<a href="<?php echo $g_options['scripturl']; ?>?mode=admin"><?php echo eHtml(t('admin.heading.tools')); ?></a></b><br />
<img src="<?php echo IMAGE_PATH; ?>/spacer.gif" width="1" height="8" border="0" alt="" /><br />

<?php
	include (PAGE_PATH . "/admintasks/$code.php");
}
else
{
	// General Settings

?>
&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width="9" height="6" alt="" /><b>&nbsp;<?php echo eHtml(t('admin.heading.general_settings')); ?></b><br /><br />
<?php
	foreach ($admintasks as $code => $task)
	{
		if ($auth->userdata['acclevel'] >= $task->acclevel && $task->type == 'general')
		{
			if ($selTask == $code)
			{
?>
&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width="9" height="6" alt="" /><b>&nbsp;<a href="<?php echo $g_options['scripturl']; ?>?mode=admin" name="<?php echo $code; ?>"><?php echo $task->title; ?></a></b><br /><br />

<form method="post" action="<?php echo $g_options['scripturl']; ?>?mode=admin&amp;task=<?php echo $code; ?>#<?php echo $code; ?>">

<table width="100%" border="0" cellspacing="0" cellpadding="0">

<tr>
	<td width="2%">&nbsp;</td>
	<td width="98%"><?php
				include (PAGE_PATH . "/admintasks/$code.php");
?></td>
</tr>

</table><br /><br />
</form>
<?php
			}
			else
			{
?>
&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/rightarrow.gif" width="6" height="9" alt="" /><b>&nbsp;<a href="<?php echo $g_options['scripturl']; ?>?mode=admin&amp;task=<?php echo $code; ?>#<?php echo $code;
?>"><?php echo $task->title; ?></a></b><br /><br /> <?php
			}
		}
	}
?>
	
&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width="9" height="6" alt="" /><b>&nbsp;<?php echo eHtml(t('admin.heading.game_settings')); ?></b><br /><br />
<?php
	$gamesresult = $db->query("
			SELECT
				name,
				code
			FROM
				hlstats_Games
			WHERE
				hidden = '0'
			ORDER BY
				name ASC
			;
		");

	while ($gamedata = $db->fetch_array($gamesresult))
	{
		$gamename = $gamedata['name'];
		$gamecode = $gamedata['code'];

		if ($gamecode == $selGame)
		{
?>
&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width="9" height="6" alt="" /><b>&nbsp;<a href="<?php echo $g_options['scripturl']; ?>?mode=admin" name="game_<?php echo $gamecode; ?>"><?php echo $gamename; ?></a></b> (<?php echo $gamecode; ?>)<br /><br /> <?php
			foreach ($admintasks as $code => $task)
			{
				if ($auth->userdata['acclevel'] >= $task->acclevel && $task->type == 'game')
				{
					if ($selTask == $code)
					{
?>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width="9" height="6" alt="" /><b>&nbsp;<a href="<?php echo $g_options['scripturl']; ?>?mode=admin&amp;game=<?php echo $gamecode; ?>" name="<?php echo $code; ?>"><?php echo $task->title; ?></a></b><br /><br />

<form method="post" name="<?php echo $code; ?>form" action="<?php echo $g_options['scripturl']; ?>?mode=admin&amp;game=<?php echo $gamecode; ?>&task=<?php echo $code; ?>#<?php echo $code; ?>">

<table width="100%" border="0" cellspacing="0" cellpadding="0">

<tr>
	<td width="10%">&nbsp;</td>
	<td width="90%"><?php
						include (PAGE_PATH . "/admintasks/$code.php");
?></td>
</tr>

</table><br /><br />
</form>
<?php
					}
					elseif ($code != 'serversettings')
					{
	?>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/rightarrow.gif" width="6" height="9" alt="" /><b>&nbsp;<a href="<?php echo $g_options['scripturl']; ?>?mode=admin&amp;game=<?php echo $gamecode; ?>&task=<?php echo $code; ?>#<?php echo $code; ?>"><?php echo $task->title; ?></a></b><br /><br /> <?php
					}
				}
			}
		}
		else
		{
?>
&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/rightarrow.gif" width="6" height="9" alt="" /><b>&nbsp;<a href="<?php echo $g_options['scripturl']; ?>?mode=admin&amp;game=<?php echo $gamecode; ?>#game_<?php echo $gamecode; ?>"><?php echo $gamename; ?></a></b> (<?php echo $gamecode; ?>)<br /><br /> <?php
		}
	}
}
echo "</td>\n";

if (!$selTask || !$admintasks[$selTask])
{
	echo '<td width="50%">';
?>
&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width="9" height="6" alt="" /><b>&nbsp;<?php echo eHtml(t('admin.heading.tools')); ?></b>

<ul>
<?php
	foreach ($admintasks as $code => $task)
	{
		if ($auth->userdata['acclevel'] >= $task->acclevel && $task->type == 'tool')
		{
?>	<li><b><a href="<?php echo $g_options['scripturl']; ?>?mode=admin&amp;task=<?php echo $code; ?>"><?php echo $task->title; ?></a></b><br />
		<?php echo $task->description; ?><br /><br />
	</li>
<?php
		}
	}
?>
</ul>
<?php
	echo '</td>';
}
?>
</tr>

</table>

<?php
if (isset($footerscript))
{
    echo $footerscript;
}
?>
