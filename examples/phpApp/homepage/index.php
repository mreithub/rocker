<html>
<head>
<title>Awesome PHP Site</title>
</head>
<body>
<h1>Welcome to my awesome homepage</h1>

<?php
	# good ol' spaghetti code - or: how not to write PHP ;)
	$db = new SQLite3('data/counter.sqlite3');

	$db->query("CREATE TABLE IF NOT EXISTS visitors ("
		. "id INTEGER PRIMARY KEY AUTOINCREMENT,"
		. "ip VARCHAR(15) NOT NULL,"
		. "ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");

	$query = $db->prepare("INSERT INTO visitors (ip) VALUES (:ip)");
	$query->bindValue(':ip', $_SERVER["REMOTE_ADDR"]);
	$query->execute();

	$res = $db->query("SELECT COUNT(*) FROM visitors")->fetchArray();
	echo "<p>You are visitor nr ${res[0]}</p>";

	$res = $db->query("SELECT COUNT(*) FROM visitors WHERE ts >= DATETIME('now', '-1 minute')")->fetchArray();
	echo "<p>${res[0]} people visited this page in the last minute</p>";
?>

</body>
</html>
