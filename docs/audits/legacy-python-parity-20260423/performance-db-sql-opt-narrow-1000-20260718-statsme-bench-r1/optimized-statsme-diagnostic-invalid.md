# Invalid diagnostic attempt

`optimized-statsme/measure1` was stopped during import after discovering that
the copied historical helper referenced the nonexistent
`hlstats_Frag_Frags` anchor table. `optimized-statsme/measure2` was likewise
stopped when the copied double-quoted metric labels were interpreted as column
identifiers. Their logs are retained for provenance only; both disposable
containers and volumes were removed. The benchmark-only helper now uses a
PowerShell SQL variable with SQL single-quoted labels and fails fast if either
anchor query exits nonzero.
