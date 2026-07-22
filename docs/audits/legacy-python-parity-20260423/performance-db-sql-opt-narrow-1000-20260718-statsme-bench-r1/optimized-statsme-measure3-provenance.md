# Measure3 profile provenance

`optimized-statsme/measure3` was launched before the benchmark-only runner
gained an explicit `-Profile` switch. Its recorded command included `--profile`
and wrote `optimized-statsme-measure3-profile/perf-profile.txt`; it is the
profiled measure in this audit. Later runner edits affect only future samples.
