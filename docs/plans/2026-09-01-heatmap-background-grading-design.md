# Heatmap Explorer Background Grading Design

**Date:** 2026-09-01  
**Status:** Approved for implementation  
**Scope:** Modern Heatmap Explorer presentation only

## Context

The calibrated heatmap sources in `heatmaps/src/<game>/<map>.jpg` are largely
grayscale. Installed Counter-Strike overview bundles contain attractive color
BMP files and matching GoldSrc metadata, but those assets cannot be bundled in
the release without a separate provenance decision. Their native 4:3 geometry
also differs from the current calibrated 5:4 sources.

The Explorer already renders the calibrated map as a DOM image beneath a
separate transparent WebGL heat/difference canvas. That separation provides a
safe presentation seam: grade only the map image and leave data colors,
coordinates, projection, crop, camera transforms, and source assets unchanged.

## Decision

Add a compact localized `Color / Mono` background-style control to the modern
Explorer.

- `Color` is the default.
- `Mono` applies a strict grayscale presentation to the map background.
- The color grade is a restrained warm-sand/cool-shadow treatment with low
  saturation so heat and difference overlays remain dominant.
- The grade applies only to `[data-heatmap-image]` and an optional decorative
  overlay below the WebGL canvas.
- The WebGL heat/difference canvas and the static JPEG fallback are never
  filtered.
- Changing the style performs no fetch, scene rebuild, URL update, API call,
  cache-key change, or database write.
- The selection lives only for the current Explorer instance. Refresh returns
  to the default `Color` presentation.

## UI and Accessibility

The control uses the existing compact toolbar/button visual language and
`aria-pressed` semantics. Both choices are reachable by keyboard, have visible
focus, and use localized English and Russian labels.

When the interactive renderer is unavailable or has fallen back to a static
JPEG, the background-style control is disabled or hidden. This prevents a
filter from changing the semantic colors of a precomposited heatmap image.

## Rendering Contract

The root workspace exposes the presentation state through a narrow DOM
attribute such as `data-heatmap-map-style="color|mono"`. CSS targets only the
calibrated map image inside the interactive camera. The camera's existing
pan/zoom transform continues to move the map image and heat canvas together.

The grade must preserve map luminance and edge readability. It must not alter:

- WebGL density, opacity, or difference textures;
- heat/difference palette values or alpha;
- pin, grid, tooltip, or inspector rendering;
- image dimensions, crop, map hash, projection, or point-to-pixel mapping;
- v1 routes, generated JPEGs, or static fallback behavior.

## GoldSrc Overview Follow-up

Read-only research confirmed that the installed Counter-Strike bundle contains
25 color `BMP + TXT` overview pairs and that Valve's client uses a centered 4:3
orthographic transform based on `ZOOM`, `ORIGIN`, `ROTATED`, and `HEIGHT`.
That exact transform places the inspected `de_dust2` SQL cluster inside the
native 1024x768 frame, while the project's historical overview importer uses a
simplified transform.

This is deliberately outside the grading slice. A future optional local
GoldSrc mode may accept an administrator-provided pair and use the exact Valve
projection after full-scene and landmark acceptance. No Valve bitmap is copied
into this repository or release by this design.

## Verification

Implementation follows TDD and must prove:

1. `Color` is the initial style and the correct button is pressed.
2. Switching to `Mono` changes only the root presentation state and performs no
   network request or URL mutation.
3. Switching back to `Color` is reversible.
4. Static fallback does not receive the map filter and cannot expose an active
   misleading style control.
5. Existing JavaScript, PHP, route, responsive, keyboard, reduced-motion, and
   WebGL context-loss checks remain green.
6. Browser screenshots of map overview, player difference, mobile inspector,
   and mono mode confirm that overlays remain semantically unchanged and text/
   controls remain legible.

## Rollback

Removing the control, root style attribute, and scoped CSS restores the current
presentation. No data, configuration, asset, projection, URL, or API migration
is involved.
