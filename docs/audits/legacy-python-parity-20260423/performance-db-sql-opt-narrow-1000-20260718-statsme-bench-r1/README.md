# Offline Statsme SQL-write benchmark — 20260718-statsme-bench-r1

This audit is an isolated throughput measurement of the current working tree.
It must not be used as parity acceptance evidence and must not touch the live
legacy/Python parity containers.

## Provenance

- Method copied byte-for-byte from
  `../performance-db-sql-opt-narrow-1000-20260718-sqlwrite-1000-bench-r1/run-sample.ps1`
  (SHA-256 `DD7806AE131610B591E3900972FB0FC2A5F35D74F9721E4AB06D3D254F55C272`).
- The copied `hlstats-bench-3338.conf` keeps the accepted disposable host DB
  configuration on port 3338.
- Input corpus is the existing staged `narrow-1000` set:
  `C:\Users\semer\AppData\Local\Temp\hlstatsx-sqlwrite-1000-bench-r1`, with
  1,000 log files.

The runner restores the disposable baseline dump, uses native parser and stdin
batch size 2500 with profiling, captures initial/final anchors and manifests,
then removes its container and volume.
