# Default BSP outlines

These static templates accompany the native overview JPEGs in
`heatmaps/src/cstrike` and their calibration seeds in `sql/install.sql`.
Deploy this directory with the rest of `web/hlstatsimg`; no local game directory,
preparation script, database import of geometry, or runtime artifact is required.

Each game manifest maps a map name to the SHA-256 of its matching base JPEG.
The admin editor loads the SVG only for that exact image. This prevents a custom
replacement or cropped image from silently receiving an unrelated outline.
SVGs are parsed into numeric polygons rather than inserted as executable markup.

These are top-down BSP surface outlines, including roofs and overlapping levels,
not automatic walkability masks or floor definitions. The 25 cstrike templates
were extracted from the user's installed GoldSrc BSP/BMP/TXT set on 2026-09-08.
See `docs/heatmap-bsp-registration.md` for preparation and manual import.
