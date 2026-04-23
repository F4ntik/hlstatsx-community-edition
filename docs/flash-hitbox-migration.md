# Flash Hitbox Migration Notes

## Scope and inventory

Direct Flash embedding in active pages is limited to:

- `web/pages/playerinfo_weapons.php`
- `web/pages/claninfo_weapons.php`

Legacy clipboard Flash code exists in `web/includes/js/syntax.js`, but it is not part
of the hitbox render path.

## Decompilation setup

- JPEXS source cloned to workspace root: `../jpexs-decompiler`.
- FFDec CLI extracted to `../tools/ffdec/ffdec_26.0.0`.
- SWF export command used:

`ffdec -onerror ignore -export script,image,text scripts/flash_decompile/exports web/hlstatsimg`

## SWF dependency findings

Decompiled `hitbox.swf` confirms runtime chaining into other SWFs:

- In `scripts/flash_decompile/exports/hitbox.swf/scripts/frame_1/DoAction.as`:
  - `_root.model = "hlstatsimg/" + model + ".swf";`
  - `_root.modelcon.loadMovie(model);`

This means model assets are dynamic SWF dependencies (`ct.swf`, `ts.swf`, `allies.swf`, etc.).

## Modern replacement approach

- New renderer added: `web/includes/js/hitbox-modern.js`.
- Model SWFs were decompiled and converted to PNG assets under:
  - `web/hlstatsimg/hitbox_models/*.png`
- Weapon pages now render a modern HTML/CSS/JS hitbox panel instead of Flash.

## Compatibility details mirrored from Flash

- Percent math and scaling replicate decompiled ActionScript behavior.
- Legacy left/right graph swap is preserved intentionally:
  - Old PHP passed right-arm/left-arm (and leg) values in swapped query slots.
  - New renderer input mapping preserves this behavior for visual parity.

## Legacy test contour guidance

Use existing replay baseline contour in this repo to validate no runtime regressions while
iterating on frontend migration:

- `scripts/replay_baseline/README.md`
- Canonical loop:
  - restore clean baseline (`restore-baseline.ps1` for `legacy`/`python`)
  - legacy replay smoke
  - python replay
  - diff via `compare_stats_dbs.py`

This keeps frontend work isolated while preserving migration parity discipline.
