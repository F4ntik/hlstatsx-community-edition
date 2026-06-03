# Default FTP data dir (small smoke fixtures)

If you do **not** set `HLSTATS_FTP_LOGS_HOST_PATH`, compose mounts this folder into `log-ftp`.

To serve **thousands of logs from the host** (e.g. `replay_baseline/artifacts`) without copying them here, set the env var — see [`FTP_CONTOUR.md`](../FTP_CONTOUR.md) and [`env.ftp-logs.example`](../env.ftp-logs.example).
