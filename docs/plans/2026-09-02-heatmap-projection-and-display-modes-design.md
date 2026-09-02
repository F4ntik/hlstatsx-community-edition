# Heatmap Projection and Display Modes Design

**Date:** 2026-09-02  
**Status:** Approved for implementation  
**Scope:** Modern Heatmap Explorer projection trust and presentation modes

## Result

The Modern Heatmap Explorer will first prove that game-world coordinates are
registered to the correct places on the served map image, then offer three
complementary ways to view the same accepted data:

- `Smooth` renders a continuous density field with merging, rounded hotspots;
- `Cells` renders the authoritative aggregated grid without smoothing;
- `Points` renders distinct events at their projected map-pixel positions.

Projection correctness is a prerequisite for all three modes. A high in-bounds
percentage is not alignment evidence and must no longer be presented as such.

## Current Defects

The current renderer uploads a compact grid with nearest texture filtering and
applies a piecewise-constant 3x3 box average. The average spreads density to
neighboring cells but preserves cell-shaped plateaus and hard boundaries.

The current `cstrike/de_dust2` projection is also not landmark-accepted. The
restored runtime values are `xoffset=384`, `yoffset=1120`, `scale=1.26`,
`flipx=0`, `flipy=1`, `rotate=0`. Historical evidence measured only 30 of 350
candidate coordinates inside the image for that configuration. A later 100%
in-bounds range fit guaranteed containment only; it did not prove that points
landed on the corresponding map geometry.

The served repository image is a 1280x1024 JPG while the installed GoldSrc
overview pair uses a native 1024x768 BMP plus `ZOOM`, `ORIGIN`, and `ROTATED`
metadata. The existing importer treats those values as a simplified legacy
seed and omits the explicit native-frame-to-served-image registration.

## Projection Decision

Projection calibration uses two independent pieces of evidence:

1. an automatic image-frame registration seed when a matching operator-owned
   GoldSrc overview BMP/TXT pair is available;
2. named in-game landmark pairs as the acceptance gate.

For the locally installed `de_dust2` pair, independent SIFT and ORB matching
showed that the native BMP and repository JPG differ by an almost exact uniform
scale and translation:

```text
x_jpg = 1.050233018 * x_bmp + 106.907324
y_jpg = 1.050233018 * y_bmp + 76.955454
```

The SIFT/MAGSAC fit retained 715 of 813 matches, with 0.499 px RMSE and 1.075
px p95 error across all four image quadrants. Perspective and rotation were
negligible. Composed with the installed `de_dust2.txt`, this produces the
non-persisted candidate:

```text
xoffset = 376
yoffset = 1207
scale   = 1.428254465
flipx   = 0
flipy   = 1
rotate  = 0
crop    = 0/0/0/0
```

This candidate is preview evidence, not permission to mutate a live map
configuration. It must pass landmark residual and visual readback before save.
No Valve or Steam bitmap is copied into the repository or release; only
derived numeric coefficients and sanitized verification results may persist.

## Landmark Calibration

The admin heatmap tool gains an exact-point calibration workflow for a bounded
historical interval. It reuses the existing authenticated heatmap data path
and participant-coordinate semantics.

An operator records at least four widely separated calibration events at
visually unambiguous locations and identifies the same locations on the exact
served map image. Six to eight pairs are preferred so some can remain holdout
points. Suitable `de_dust2` landmarks include A site, B site, T spawn, CT
spawn, mid, Long A, short/catwalk, and the B tunnel entrance.

The solver evaluates the eight supported orthogonal orientations: four
quarter-turns with and without reflection. For each orientation it fits one
uniform scale and two translations by least squares, rejects outliers, and
reports the pixel residual for every anchor and holdout. It never selects or
accepts a transform from image containment alone.

The candidate may be saved only when:

- at least four non-collinear anchors are present;
- at least two additional holdouts are present for runtime acceptance;
- semantic labels make A/B and T/CT mirror mistakes observable;
- the residual threshold is compatible with the display mode: no more than
  one 10 px heatmap cell for density modes and no more than the visible point
  marker radius for exact-point acceptance;
- preview/readback uses the exact served map asset hash and game/map identity.

If residuals vary systematically by axis or location, the current uniform
projection model cannot represent the asset pair. The UI must stop and explain
the mismatch rather than save a plausible-looking approximation. A future
explicit asset-frame transform is an evidence-gated escalation, not part of
this slice.

The existing responsive drag calculation is corrected so CSS display pixels
are converted to authoritative canvas pixels before changing offsets.

## Exact Point Geometry

The existing v2 scene discards projected pixel coordinates after grid
aggregation. `Points` therefore uses a lazy v2 geometry request built from the
same exact query window, participant coordinate, event channel, player lens,
floor, and projection rules as the grid scene.

The payload contains only projected map-pixel coordinates and the minimum
aggregate counts required for the active layer. Events sharing the same
projected pixel are combined. It does not expose raw world XYZ, event IDs,
timestamps, weapons, or player identities.

The response is sorted, unique, finite, and in bounds. It is hard-capped at
20,000 unique visible positions. When the cap is exceeded, the server does not
sample or silently truncate: `Smooth` and `Cells` remain available and the UI
asks for a shorter period.

Clicking a point selects its containing authoritative cell and opens the
existing bounded cell inspector. Inspector counts, navigation, privacy, and
the 100-row detail limit remain unchanged.

## Display Modes

One localized `Smooth / Cells / Points` control appears in the Explorer. The
default is `Smooth`. The choice is presentation state for the current Explorer
instance and does not alter the query URL, period, projection, map identity, or
database state.

### Smooth

`Smooth` uses a separable Gaussian kernel over the authoritative grid with a
fixed moderate bandwidth of approximately `sigma=1.25` cells and radius four.
The client caches the presentation field per layer/channel. The WebGL shader
manually interpolates neighboring float texels so output intensity is
continuous across cell boundaries without depending on optional float-linear
texture extensions.

The field is normalized after smoothing and retains the accepted square-root
visibility transfer. Edge kernels are truncated to in-bounds samples and
renormalized; edge texels are not repeated.

Difference rendering splits positive and negative deltas into independent
non-negative fields, smooths both, and normalizes them against one shared
maximum. Overlap moves toward the neutral palette center instead of cancelling
silently or flipping sign.

### Cells

`Cells` renders the unsmoothed authoritative v2 bins. It is the audit-oriented
view and keeps exact cell boundaries, values, navigation, and inspector
semantics. It also provides an immediate local rollback if Smooth rendering is
unavailable.

### Points

`Points` lazily requests exact projected geometry and renders circular native
WebGL points. Marker size remains screen-legible but bounded and does not
pretend to encode an area larger than the projected pixel. Color and Difference
semantics match the active layer/channel.

## Compatibility and Failure Behavior

- Existing PHP routes, v1 behavior, public URLs, MySQL event authority,
  EN/RU localization, and static JPEG fallback remain intact.
- Static JPEG and no-WebGL fallbacks do not expose a misleading active display
  selector.
- Smooth/Cells switch locally without a network request.
- Points request identity includes the exact window, filters, projection hash,
  asset hash, geometry kind, and response version.
- Empty fields remain transparent. Invalid geometry, cap overflow, context
  loss, or failed lazy fetch returns to the existing grid view with a localized
  explanation.
- Projection save remains authenticated, CSRF-protected, stale-hash guarded,
  transactional, and followed by independent readback.

## Verification

Implementation follows TDD and must prove:

1. Gaussian impulse symmetry, monotonic falloff, constant-field preservation,
   edge normalization, and merging of nearby impulses without grid plateaus.
2. Signed Difference lobes retain sign, shared normalization, and confidence
   semantics without neighbor-induced sign reversal.
3. Raw scene grids, occupied-cell navigation, pointer mapping, inspector
   counts, and bounded details remain unchanged.
4. Exact-point payloads are sorted, unique, bounded, identity-safe, and refuse
   cap overflow without sampling.
5. Smooth/Cells switch without request or URL changes; Points loads lazily and
   falls back honestly.
6. Landmark solving recovers known synthetic rotations/reflections,
   translation, and scale; rejects outliers and unrepresentable fits.
7. Responsive admin dragging produces the same authoritative offset at
   different CSS display sizes.
8. The image-derived `de_dust2` candidate is previewed against real events and
   accepted only with named landmark plus holdout residual evidence.
9. Existing PHP, JavaScript, Python, WebGL context-loss, EN/RU, mobile, 200%
   reflow, Color/Mono/Difference, static JPEG, cache, restore, and rollback
   gates remain green.

## Rollout and Rollback

Projection calibration is completed and accepted before presentation-mode
promotion. All runtime mutation uses the existing recoverable admin save and
readback path. The original `de_dust2` configuration is backed up and restored
on any failed landmark, browser, cache, JPEG, or readback gate.

Removing the display selector, point geometry request, Gaussian presentation
field, and landmark helper restores the current Explorer without a data
migration. `Cells` remains the in-product presentation rollback. This design
does not deploy, publish, push, or establish production release acceptance.
