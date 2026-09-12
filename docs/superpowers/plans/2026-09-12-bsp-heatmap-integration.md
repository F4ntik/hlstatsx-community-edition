# BSP Heatmap Integration Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. One product writer per worktree; independent asset preparation uses its own checkout. User authorization already covers implementation and safe local verification.

**Goal:** Integrate the approved heat appearance and wall-aware spreading, ship prepared geometry for every default map, and measure runtime cost.

**Architecture:** Offline counted-node topology with image/projection identity. PHP aggregates original XYZ onto nodes; WebGL displays cached, bounded diffusion fields with no cross-wall interpolation.

**Tech Stack:** Existing Python/Pillow/NumPy preparation, PHP, vanilla JS and WebGL2.

**Spec:** docs/plans/2026-09-12-bsp-heatmap-integration-design.md

## Global constraints

- Preserve unrelated dirty work and the earlier experiment artifacts/ZIP.
- No public deployment, DB schema changes, or game/server changes.
- EN/RU labels; legacy/JPEG and unsupported-map fallback remain functional.
- Use rtk commands; targeted gates instead of the full parity/replay suite.

## Tasks

- [x] Asset preparation: scripts/heatmap_bsp_surfaces.py consumes the existing validated BSP experiment extraction and emits the frozen asset interface for the exact 25-map default manifest. Validate all hashes, bounds, unique cardinal edges, degree <=4, finite heights, and projection/image matches. Worktree: hlstatsx-bsp-default-assets-20260912.
- [x] Product integration: add bounded PHP surface loading/XYZ assignment at heatmap_scene_accumulate_contribution and optional scene metadata/counts, with cache identities and fail-safe diagnostics. Extend JS validation/loading and typed-array diffusion, cached render fields, final clip, warm transfer and all display modes. Add focused tests covering wall leakage, missing Z, overlapping floors, counts, stale assets and existing scene compatibility. Sole product writer in hlstatsx-bsp-wall-experiment-20260912.
- [x] Integrate prepared files, run focused PHP/JS checks and benchmark at varying event counts, geometry sizes and iterations. Verify larger count weights change the field proportionally while compute cost stays tied to nodes/edges. Record first calculation and cached redraw separately.
- [x] Independently review actual diff and perform local HTTP/browser checks where available. Save a concise Russian HTML report with visual evidence, measurements, included maps and remaining limitations. Update status/plans and acceptance ledger.

## Ledger

- Existing experiment verified on real dust2; approved by user.
- User clarified clip-after-blur proposal; root retained barrier-aware propagation plus final clip because display masking alone leaks into adjacent valid surfaces.
- After Codex restart, no worker processes survived and no product implementation edits existed. Work resumed from the two verified prototype scripts.
- Docker Desktop was stopped; started the already-installed application hidden for local validation. No containers restarted or reconfigured at this point.
- Final local acceptance: isolated copied database and web container at 127.0.0.1:8394. All 25 asset HTTP responses gzip/hash verified; all 25 scene responses valid (23 empty in selected historical window). de_dust2 333/350 and de_train 89/92 assigned positions.
- Full web_heatmap_smoke and web_i18n_smoke passed in a writable disposable snapshot. Focused PHP/JS surface checks read all 25 maps. Final reviewer findings resolved: fractional floor bounds, conservative allowed regions, population-specific coverage, cache identity, and accurate fallback labels.
- Browser checked Smooth/Cells/Points, deaths, Color/Mono, lock scale, zoom/reset, EN/RU, and player Difference fallback. Player 174 has 1/5 personally assigned positions, so ordinary comparison is intentionally retained despite 166/175 overall coverage. No browser errors observed.
- Report with real screenshot: C:/Users/semer/.codex/visualizations/2026/09/12/01a094d6-1dfa-7450-8762-af4e388bbee1/heatmap-result.html. Repository acceptance summary: docs/audits/bsp-heatmap-integration-20260912.md. No commit, push, or public deployment.
