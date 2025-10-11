# Awards report integration scenarios

The integration test in `scripts/hlstats_awards_py/tests/test_integration.py`
coordinates a full maintenance run against a stubbed MySQL connection.  The
test feeds deterministic data into the calculator, exercises the default
actions (`--inactive`, `--awards`, `--ribbons`, `--prune`, `--optimize`) and
captures the resulting :class:`~hlstats_awards_py.calculator.AwardsReport`.

The fixture emits the following report snapshot:

```json
{
  "inactive_updates": 5,
  "players_hidden": 2,
  "awards": [
    {"award_id": 1, "daily_winner": {"player_id": 111, "count": 15}, "global_winner": {"player_id": 122, "count": 45}},
    {"award_id": 2, "daily_winner": {"player_id": 211, "count": 15}, "global_winner": {"player_id": 222, "count": 45}}
  ],
  "player_awards_synced": 2,
  "ribbons_cleared": {"tf2": 4},
  "ribbons_awarded": {"tf2": 3},
  "pruned_tables": {
    "hlstats_Events_TeamBonuses": 5,
    "hlstats_Events_Frags": 1,
    "hlstats_Players_History": 7,
    "hlstats_Trend": 3,
    "hlstats_server_load": 1
  },
  "optimized_tables": ["hlstats_Players", "hlstats_Awards"]
}
```

The JSON shape mirrors the dataclasses defined in `calculator.py` and can be
used to build operational dashboards or regression datasets.  Teams can extend
the integration scenario with real MySQL fixtures to cross-check output against
the legacy Perl script while reusing the same reporting hooks.
