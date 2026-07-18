# Evidence inventory — 2026-07-17 baseline

This is a read-only inventory captured before the manifest/runner changes in
the current checkout. Existing artifacts are retained; no evidence file was
deleted, moved, or overwritten by this inventory.

## Narrow baseline candidates

The only matching 1,000-log input pair currently present is:

| Stack | File | Lines | Bytes | SHA-256 | Actual classification |
| --- | --- | ---: | ---: | --- | --- |
| legacy | `legacy-input-manifest-1000-current.txt` | 1,000 | 14,000 | `5274e3e01a790dbcb09fc8454d11197e97506135ba4f3199e188bd1e76fe3d` | `narrow-1000` candidate |
| python | `python-input-manifest-1000.txt` | 1,000 | 14,000 | `5274e3e01a790dbcb09fc8454d11197e97506135ba4f3199e188bd1e76fe3d` | `narrow-1000` candidate |

Both manifests cover `L0101000.log..L0106125.log`. The stored contour
metadata in `.parity-state/contour-info/legacy-narrow-1000.json` and
`python-narrow-1000.json` reports `logs_count=1000` and the same selected-log
fingerprint `ccc06efc73505e1f1cf0703500f4dacdb05ee1ced634e93ee3cb410cad435566`.
Those metadata files were created on 2026-06-03 and must not be paired with
the later snapshots below without a fresh run.

## Files whose `-1000` name is not their actual contour

These files are retained for history but are classified as `full-41513`, not
as narrow evidence:

| File | Lines | Bytes | SHA-256 | Reason |
| --- | ---: | ---: | --- | --- |
| `legacy-input-manifest-1000.txt` | 41,513 | 581,182 | `24f62af562ed6acb724595a8899bf339ec936378eac6f534fcd2157f516ae676` | full-corpus input set with 63 excluded logs |
| `legacy-dropped-lines-1000.txt` | 169,140 | 7,074,180 | `b87a22ee0c1df9a1daf19e56b128f9a29389670b279cce4ebb83d8c3dfdfe5bb` | dropped-line capture belonging to the full-corpus run |
| `legacy-sql-snapshot-1000.txt` | 54 | 992 | `d3b155abdbfa1cd5a40840b7cb44957a90ee149126ace55778c4f1d9dfc2a888` | anchors are full-corpus: 6,039 players and 536,996 frags |

The corresponding `python-sql-snapshot-1000.txt` is also not a valid narrow
counterpart: it has 496 players and 12,314 frags and belongs to the stale,
partial 41,513-log Python capture. Its SHA-256 is
`f79665e3d954e88f9ff429c2c9e9fd6254be29fd6f2b782dc29f7b65f9bf37d1`.
`python-dropped-lines-1000.txt` has 722 lines and SHA-256
`7f59ac059d34975776ef0fa1d95e7cbf6f183ba271eab5e6e90c715a185a917f`; it is
not paired evidence until the new Python import produces an identical input
manifest and an explicit ignored-lines manifest.

## Full-corpus label mapping

The complete 41,576-log manifest pair has 41,576 lines and SHA-256
`9b65f3c47ecb963ce772fb1ae020973268cdd6a50a7d1863a56d219ebfe86898` for
both stacks. The reduced 41,513-log manifest set has 41,513 lines and SHA-256
`24f62af562ed6acb724595a8899bf339ec936378eac6f534fcd2157f516ae676`; the
excluded-list file has 27 lines and SHA-256
`47774ef8bc2d01242103a680e8ac6f110228be6e14edcafdce97b33a3001e6db`.
These sets are `full-41513`/full-corpus diagnostics, never `narrow-1000`.

The existing metadata files named `legacy-narrow-41513.json` and
`python-narrow-41513.json` are likewise classified as `full-41513` for
inventory purposes. Their anchors are not a pair: legacy reports 6,039
players/536,996 frags, while Python reports 496 players/12,314 frags and one
entry. They remain untouched pending a fresh, explicitly labelled run.

## Promotion rule

Do not delete or rename the old `*-1000` files until a new dual narrow run has
completed successfully under a unique run identifier. Promotion requires:

- identical final legacy/Python input manifests (same order, count, and SHA);
- both explicit ignored/dropped-line manifests;
- contour metadata and SQL snapshots carrying the same canonical label;
- no new DB drift against the accepted narrow baseline.

## Fresh narrow acceptance candidate

The runner was rerun with `-UseDumpRestore`, the canonical label
`narrow-1000`, and the unique evidence run id
`20260717-narrow-1000-r1`. The first diagnostic attempt with this run id was
not promoted because the legacy writer emitted CRLF while the Python writer
emitted LF. Both manifest writers were then made explicit LF writers and the
same uniquely labelled evidence was regenerated with `-OverwriteEvidence`.
Historical files above were not changed.

| Evidence | Legacy | Python | Result |
| --- | --- | --- | --- |
| final input manifest | 1,000 lines / 13,000 bytes / `95bfdb5951922c0c36aab2c5263e1880b227e845b34c9262939b028d0fbebe8a` | same | byte-identical |
| dropped/ignored manifest | 1,969 dropped lines / `d9b558567bfa40133afcec4e2ef8a11275780a6242837900f48b5b0c544f2cc7` | 0 ignored lines / empty-file SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | both present and attributable |
| selected-log metadata | 1,000 logs, `L0101000.log..L0106125.log`, `ccc06efc73505e1f1cf0703500f4dacdb05ee1ced634e93ee3cb410cad435566` | same | matching |
| SQL snapshot sections | `players=323`, `frags=5464`, `maps_counts_rows=31`, same event range/top maps | same | equal after stack/container/timestamp header normalization |

The run completed with `processed=1000`, `errors=0` on the legacy replay and a
successful Python import. Both contour metadata files carry
`artifact_label=narrow-1000`, `contour=narrow-1000`, the same
`evidence_run_id`, `baseline_mode=dump`, and anchors
`players=323`, `frags=5464`, `team_bonuses=4765`, `entries=0`,
`server_rows=1`.

`compare_stats_dbs.py --max-examples 1000 --json` returned one known
`hlstats_Players` residual: `323/323` rows, `250` legacy-only and `250`
Python-only normalized pairs. Pairing all 250 identities after removing only
`country` and `flag` produced `0` non-GeoIP pairs. The stable aggregate and
snapshot sections therefore show no new replay drift; the raw GeoIP residual
remains the documented post-processing difference and is not silently hidden.

The guarded migration inspection was run read-only in the Python comparison
network. It reported `rotate=0: 442` and no stored `2/3` values. The projection
version marker was absent at inventory time and no mutation was performed by
the inventory step. After both full-41513 databases were preserved and the
user supplied the separate runtime gate on 2026-07-18, the guarded migration
advanced the marker to version `2` without changing the `{0:442}` distribution
or replay anchors. See `runtime-heatmap-migration-gate-20260718.md`; no map
calibration proposal was applied.
