<?php

/* 
 * Basic WEB frontend for 2nVoiceBlueSMSServer.py SMS server
 * 
 *  __author__ = "Tamas TOBI <tamas.tobi@gmail.com>, Hungary"
 * __copyright__ = "Copyright (C) Tamas Tobi 2012, License: GPL v2, http://www.gnu.org/licenses/gpl-2.0.html"
 * 
 * Dependencies: PHP5.x, Webserver: preferrable Apache2.x
*/

////////////////////////////////////////////////////
// CONFIG
define('WEBLOGPATH',"/var/www/2nsms/smssend.log"); 	//Logging path, www-data user can be write here
define('SMSSERVERIP','127.0.0.1');					//The remote IP where the 2nVoiceBlueSMSServer runs
define('SMSSERVERPORT','8080');						//2nVoiceBlueSMSServer remote PORT
// CONFIG END
////////////////////////////////////////////////////


header('Content-Type: text/html; charset=utf-8');
@ini_set('zlib.output_compression',0);
@ini_set('implicit_flush',1);
@ob_end_clean();
set_time_limit(0);

function elog($msg){
	error_log(date('Y-m-d H:i:s')."\t".$msg."\n",3,WEBLOGPATH);
}

function vphone($inp){
	$v='0123456789';
	$var = str_split($v); 

	$o='';
	$inp=trim((string)$inp); 

	$inp=str_replace("'","",$inp);
	$inp=str_replace('"',"",$inp);
	$inp=str_replace(' ',"",$inp);
	$inp=str_replace(',',"",$inp);
	$inp=str_replace(';',"",$inp);
	$inpar = str_split($inp);
	foreach($inpar as $i){
		if (in_array($i, $var)){
		  $o.=$i;
		}
	}
	return $o;
}

function Selector($order_name,$field_name,$title,$selected=false) {
	$rtrn = "<option";
	if ((isset($_GET[$order_name]) && $_GET[$order_name] == $field_name) || (isset($_POST[$order_name]) && $_POST[$order_name] == $field_name) ||  $selected) {
		$rtrn .=' selected="selected" ';
	} else {
		$rtrn .= ' ';
	}
	$rtrn .= 'value="'.$field_name.'">';
	$rtrn .= $title;
	$rtrn .= '</option>';
	return $rtrn;
}

//sms database actions
$action = (isset($_GET['action']) && !empty($_GET['action'])) ? trim($_GET['action']) : "listrec";
$mod = (isset($_GET['mod']) && !empty($_GET['mod'])) ? trim($_GET['mod']) : "";
$_GET['action'] = $action;

$smslist = false;

if ($mod == "delete"){
	$msgid = $_GET['id'];
	$smslist = file_get_contents("http://".SMSSERVERIP.":".SMSSERVERPORT."/?action=".$mod."&id=".$msgid);
	header("Location: ./?action=".$action);
}
if ($mod == "truncate"){
	$smslist = file_get_contents("http://".SMSSERVERIP.":".SMSSERVERPORT."/?action=".$mod);
	header("Location: ./?action=".$action);
}

$smslist = file_get_contents("http://".SMSSERVERIP.":".SMSSERVERPORT."/?action=".$action);
if ($smslist && !empty($smslist)){
	$xml = simplexml_load_string($smslist);

	$smstable='<table border="0" cellpadding="2" width="825px">';
	$smstable.='<tr bgcolor="#afafaf" ><th>Date</th><th>From</th><th>To</th><th>Status</th><th>SIM</th><th>Message</th><th>Del</th></tr>';
	$i=0;
	foreach($xml->children() as $sms){
		if ($i%2){
			$smstable.= '<tr bgcolor="fafafa">';
		} else {
			$smstable.= '<tr bgcolor="e1e1e1">';
		}
		$smstable.= '<td width="120px">'.$sms->smsdate.'</td>';
		$smstable.= '<td>'.$sms->fromnum.'</td>';
		$smstable.= '<td>'.$sms->tonum.'</td>';
		$smstable.= '<td>'.$sms->status.'</td>';
		$smstable.= '<td>'.$sms->cardnum.'</td>';
		$smstable.= '<td>'.$sms->msg.'</td>';
		$smstable.= '<td><a href="./?action='.$action.'&id='.$sms->id.'&mod=delete">['.$sms->deleted.']</a></td>';
		$smstable.= '</tr>';
		$i++;
	}
	$smstable.='</table>';
}

?>
<!DOCTYPE html>
<html lang="en-US">
	<head>
		<meta charset="utf-8">
		<title>2n VoiceBlue SMS Server - Basic Web Interface</title>
		<style>
			body {
				font-size: 12px;
				font-family: Arial, Helvetica, sans-serif;
				line-height: 20px;
				color: #333333;
			}
			
			a {
				color: #blue;
				text-decoration: underline;
			}
			
			.overview {
				background: #FFEC9D;
				padding: 10px;
				width: 800px;
				border: 1px solid #CCCCCC;
			}
			
			.originalTextareaInfo {
				font-size: 12px;
				color: #000000;
				font-family: Tahoma, sans-serif;
				text-align: right
			}
			
			.warningTextareaInfo {
				font-size: 12px;
				color: #FF0000;
				font-family: Tahoma, sans-serif;
				text-align: right
			}
			
		</style>
		<script src="./jquery.min.js" type="text/javascript"></script>
		<script src="./jquery.textareaCounter.plugin.js" type="text/javascript"></script>
		<script type="text/javascript">
			var info;
			$(document).ready(function(){
				var options2 = {
						'maxCharacterSize': 155,
						'originalStyle': 'originalTextareaInfo',
						'warningStyle' : 'warningTextareaInfo',
						'warningNumber': 150,
						'displayFormat' : '#input/#max'
				};
				$('#msgTextarea').textareaCount(options2);
			});
		</script>
	</head>
	<body>
	<div align="center">
<?php

//sms sending 
if (isset($_POST['numTextarea']) 
	&& !empty($_POST['numTextarea']) 
	&& strlen(trim($_POST['numTextarea'])) > 3
	&& isset($_POST['msgTextarea'])){

	echo '<div class="overview">
		SMS sending result
		</div>';
	flush();
	$numary=explode("\n",$_POST['numTextarea']);
	$msg=trim($_POST['msgTextarea']);
	$msg=str_replace(array("\r", "\n", "\r\n"), ' ', $msg);
	$msg=trim($msg);
	elog("---------------");
	elog($_SERVER['REMOTE_ADDR'].' / SMS sending: '.str_replace(array("\r", "\n", "\r\n"), ',',$_POST['numTextarea']).": ".$msg);
	echo "Message: ", $msg,"<hr>";
	$i=1;
	foreach($numary as $phone){
		$phone=trim($phone);
		if (!$phone){
			continue;
		}
		$vphone=vphone($phone);
		if (!is_numeric($vphone)){
			echo '<font color="red"><b>Invalid number: ',$phone,' => ',$vphone,' !!! </b></font><br>';
			flush();
			sleep(1);
			continue;
		}
		$handle = file_get_contents("http://".SMSSERVERIP.":".SMSSERVERPORT."/?rcpt=".$vphone."&msg=".urlencode($msg)."");
		elog($handle);
		echo $handle,"<br>";
		flush();
		sleep(1);
		$i++;
	}
	elog("---------------");
	echo 'Sent: ',($i-1)," pcs";
	sleep(2);
}
?>
<div class="overview">
2N VoiceBlue - basic SMS frontend
</div>
<form action="./" method="post">
	<table border="0" cellpadding="10">
		<tr><td valign="bottom"><b>Recipient numbers (per row):</b></td><td valign="bottom"><b>Message (max 155 char):</b></td></tr>
		<tr><td valign="top"><textarea id="numTextarea" name="numTextarea"  cols="25" rows="10"></textarea></td><td valign="top"><textarea id="msgTextarea" name="msgTextarea" cols="25" rows="10"></textarea></td></tr>
		<tr><td colspan="2" valign="top"><input type="submit" value="Send SMS" /></td></tr>
	</table>
</form>
<div class="overview">SMS database</div>
<br />
<form action="./" method="get">
<b>Filter:</b> <select id="action" name="action" onChange="form.submit();">';
<?php 
echo Selector("action","listrec","Received SMS");
echo Selector("action","listrecdel","Received SMS - show deleted");
echo Selector("action","listall","All SMS (sent+received)");
echo Selector("action","list","All SMS (sent+received) - show not deleted");
echo Selector("action","listdel","All SMS (sent+received) - show deleted");
echo Selector("action","listsent","Sent SMS");
echo Selector("action","listsentdel","Sent SMS - show deleted");
echo Selector("action","listqueue","SMS queued for sending");
echo Selector("action","listerr","SMS errors");
?>
</select> <button type="button" onclick="window.location.href='./?action=<?=$action?>'">Page Refresh</button> <button type="button" onclick="window.location.href='./?mod=truncate&action=<?=$action?>'">Truncate Deleted</button>
</form>
<br />
<?=$smstable?>
</div>
</body>
</html>
