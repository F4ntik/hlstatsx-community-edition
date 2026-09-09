# Heatmap BSP registration and presentation improvements

Date: 2026-09-07. User authorized graphical and architectural improvements.

## Decisions

Keep the existing MySQL/PHP/WebGL2 pipeline. Complete the previously approved
Smooth / Cells / Points presentation, with immutable raw grids and a cached
Gaussian presentation field. Improve map space, readable dates, and honest
coordinate-availability wording. No framework or new online service is needed.

Correct coordinate registration before claiming positional accuracy. The old
GoldSrc importer incorrectly uses ZOOM as world units per pixel and ORIGIN as
an image corner. Earlier image-matching coefficients do not repair this wrong
world-to-overview transform; the September 2 numeric candidate is superseded.

Separate world-to-native-overview projection from native-to-served-image
registration. Validate the first against Valve SDK and local BSP world geometry,
and the second against the actual image. An offline diagnostic tool can read
operator-owned BSP/overview files and emit hashes, derived outlines and numeric
evidence without shipping game assets. Source overview panel rotation must not
be applied to points independently of its texture.

Do not infer map alignment from event containment or density. Duplicate or
collinear landmarks cannot establish a transform, and held-out points must be
independent. Keep the existing authenticated preview/save path and strengthen
its server-side evidence checks.

## Checklist

- [x] Identify active Explorer worktree and preserve unrelated files.
- [x] Audit current renderer and importer against primary engine sources.
- [x] Correct import semantics and add BSP/overview diagnostic tooling.
- [x] Complete Smooth / Cells / Points and focused UI improvements.
- [x] Validate projection formulas, landmark rejection and geometry limits.
- [x] Inspect current rendered output in an isolated local runtime.
- [x] Record exact verification boundary and remaining map-specific work.

Results and current browser screenshots:
`docs/audits/modern-heatmap-explorer/improvements-20260907/README.md`.

## Verification boundary

Use a disposable local runtime for configuration experiments. Existing runtime
data/configuration, dirty replay receipts and AGENTS.md remain untouched.
Use focused Python/PHP/JS checks and current browser screenshots. BSP geometry
agreement and image registration are distinct from proof that a historical
server used the identical BSP revision. No production or publication claim.
