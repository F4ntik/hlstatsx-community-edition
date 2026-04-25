# Drift Ledger (post-mapfix, window-50)

## Baseline integrity
- `strict-input-parity-50.txt`: inputs match (`50/50`), dropped-line manifests match (`109/109`).
- `runtime-db-diff-post-mapfix.txt` and `runtime-db-diff-post-mapfix-rerun.txt` are byte-identical.
- This file is the reference ledger for subsequent drift-reduction passes.

## Baseline correction note
- Authoritative replay comparisons in this stage use `-ForceDumpRestore`.
- Snapshot-only restore was found to inject pre-diverged state between stacks and
  distort drift shape.

## hlstats_Maps_Counts (top-10)

| Symptom | Likely cause | Next probe |
|---|---|---|
| `de_dust2`: legacy `233/98` vs python `577/216` | Duplicate frag/headshot attribution in Python stream | Compare frag event multiplicity per `(event_time,killer,victim,weapon,map)` |
| `$2000$`: legacy `464/188` vs python `873/364` | Same duplicate pattern in dense combat rounds | Trace `record_frag_event` calls for a single kill chain |
| `aim_map`: legacy `32/20` vs python `540/212` | Multi-write around lifecycle/state carry-over | Check map assignment around `Loading map`/`Started map` boundaries |
| `aim_ulbc_picolo`: legacy `128/78` vs python `391/200` | Over-counting plus possible map carry-over | Inspect context map source (`extras.map` vs server current map) |
| `cs_mansion`: legacy `142/62` vs python `393/178` | Event replay duplication | Compare row multiplicity in `hlstats_Events_Frags` for same signatures |
| `de_mirage`: legacy `77/35` vs python `151/69` | Over-counting in normal map flow | Validate one-to-one frag -> maps_counts increment |
| `de_inferno`: legacy `0/0` vs python `39/15` | Wrong map ownership near lifecycle boundary | Extract nearest lifecycle lines before first `de_inferno` increments |
| `de_nuke`: legacy `0/0` vs python `15/5` | Same boundary attribution issue | Correlate first frag timestamps with map transition timestamps |
| Python-only map rows (`de_jeepathon2k`, `de_spay`, etc.) | Python sees extra gameplay events not present in legacy baseline | Validate if duplication originates before mapping layer (`Events_Frags`) |
| Legacy row count `16` vs python `26` | Additional maps introduced by duplicated/extra events | Quantify unique maps in `Events_Frags` for both stacks |

## hlstats_Events_PlayerActions / hlstats_Actions (top-10)

| Symptom | Likely cause | Next probe |
|---|---|---|
| `Events_PlayerActions` rows: legacy `919` vs python `3486` | Systemic duplication (often x2/x4) | Group by normalized action signature and count multiplicity |
| `Actions` `headshot`: legacy `481` vs python `1378` | Headshot action emitted multiple times per frag | Verify headshot trigger path in runtime + handler |
| `Actions` `kill_streak_2`: legacy `220` vs python `420` | Streak recalculation emitted repeatedly | Trace streak update conditions across round boundaries |
| `Actions` `Spawned_With_The_Bomb`: legacy `83` vs python `603` | Spawn/team events replayed repeatedly | Check lifecycle reset and spawn-event dedupe behavior |
| `Actions` `CTs_Win`: legacy `174` vs python `806` | Round-end triggers duplicated | Review trigger handler dispatch for round-end actions |
| `Actions` `Terrorists_Win`: legacy `154` vs python `1027` | Same round-end duplication pattern | Confirm event parser/dispatcher does not double-handle trigger lines |
| Python-only `amx_chat` action code | Action classification too permissive vs legacy | Validate whether `amx_chat` should be ignored or mapped differently |
| Python-only `latency` action code | Legacy likely ignores these pseudo-actions | Align action whitelist/normalization with legacy behavior |
| Python-only `time` action code | Same as above, appears operational not gameplay action | Add explicit skip/compatibility rule if legacy omits |
| Many action rows with `<missing-player-name>` | Missing actor identity still generating actions | Guard action writes when actor identity is unresolved |

## hlstats_Events_ChangeTeam (top-10)

| Symptom | Likely cause | Next probe |
|---|---|---|
| Rows: legacy `265` vs python `1261` | High duplication of team-change writes | Count duplicate signatures `(player,event_time,map,team)` |
| Python-only examples with `_count=4` | Same event accepted multiple times during replay | Trace dispatcher path for TEAM events and replay loop idempotency |
| Early-batch bot transitions dominate python-only set | Synthetic/bot transitions not filtered like legacy | Compare legacy filtering of empty/service team transitions |
| Repeated `UNASSIGNED` transitions | Transitional/noise transitions should be collapsed | Add de-noise rule for immediate repeated same-team transitions |
| Same timestamp+map+player with alternating CT/TERRORIST bursts | Round reset/map transition side effects | Probe transitions around lifecycle messages and server map reset |
| Legacy has `SPECTATOR` examples missing in python parity set | Team normalization mismatch | Verify parser normalization for spectator/team labels |
| Player name encoding variants (`Ocelisea!` vs decoded variant) | Identity mismatch inflates diffs | Compare by uniqueId-first identity in diff triage |
| Some legacy examples appear once, python many times | Reprocessing of same logical lines | Inspect replay handling for duplicate datagram effects |
| Transition spikes around map switches | Map lifecycle patch changed event ordering | Correlate first 10 transition events after each map start |
| Python-only volume >1000 normalized rows | Root issue is systemic, not edge-case | Fix dedupe/filter first before per-case parity tuning |

## Immediate focus order
1. `hlstats_Maps_Counts` (map ownership + frag multiplicity)
2. `hlstats_Events_PlayerActions` / `hlstats_Actions` (classification + dedupe)
3. `hlstats_Events_ChangeTeam` (noise filtering + duplication control)
