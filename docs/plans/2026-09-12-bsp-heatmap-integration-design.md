# BSP heatmap integration

User-approved follow-up to the offline experiment: carry its warm red heat style,
count-weighted field and wall-aware spreading into the existing Explorer. Prepare
all 25 maps from the bundled cstrike geometry manifest by default. Keep runtime
cost bounded by aggregated samples and geometry size, not individual brush draws.

## Decisions

- Keep the current PHP/DB/WebGL Explorer and ordinary-map fallback. Precompute
  geometry offline; no game BSP parsing during an HTTP request or in the browser.
- Accumulate counted surface-node contributions while original attacker/victim
  XYZ is available. Never infer overlapping floors from already merged XY bins.
  Missing, ambiguous or unsupported surface assignments are counted explicitly.
- Separate stacked surfaces. Apply configured floor and polygon restrictions.
  Render the maximum at coincident XY for an all-floor view, never sum levels.
- Use conservative four-neighbor diffusion on typed arrays, bounded iterations,
  cached geometry and fields. Preserve separate signed Difference contributions.
  Warm positive heat follows the accepted experiment transfer: power 0.45,
  RGB (255, 210*(1-amount), 35), peak alpha 210/255. Preserve comparison meanings
  and reference-scale behavior; explain auto-relative versus fixed scales.
- No interpolation across blocked edges. Final sampled surface clipping remains
  separate from propagation. A post-blur mask alone cannot remove color that has
  already crossed a wall into another valid room.
- Match prepared assets to current image and projection. Mismatch/malformed or
  absent assets fall back visibly without stale geometry or wrong-room snapping.
- Benchmark counted inputs, smoothing and cached redraw separately; use workers
  or bounded asynchronous chunks if measured main-thread work is excessive.

## Frozen asset interface (version 1)

Location: web/hlstatsimg/heatmap-surfaces/cstrike/<map>.json and manifest.json.
Each asset has schemaVersion=1, map, bspSha256, image={width,height,sha256},
projection (existing candidate_config fields), grid={width,height}, nodeCount,
edgeCount, pixelData, heightData, edgeData. Data fields are base64 little-endian:
pixelData uint32 per node (row-major grid cell), heightData float32 floor Z per
node, edgeData uint32 endpoint pairs. Nodes sorted by pixel then height. Edges
undirected, unique, symmetric by interpretation, cardinal, maximum degree four.
Manifest maps names to {file,sha256,imageHash,nodeCount,edgeCount}; only safe local
relative paths. Default grid 320x240, hard 512x384 and 196608 nodes/393216 edges.
PHP only needs pixels/heights for assignment; links are downloaded once by JS.

## Evidence boundary

Focused PHP/JS checks, all-map asset validation, count/coverage invariants,
performance measurements and a real local HTTP Explorer check. Keep generated
artifacts and the pre-existing ZIP. Do not change the release checkout, live DB,
game files or public deployment. Root owns final integration acceptance.

## Implemented scene extension and bounds

Optional `surfaces` has exact keys `version,state,asset,fields,rows,allowedData,diagnostics`.
`version=1`; states are `ready`, `missing_asset`, `invalid_asset`, `identity_mismatch`,
`low_coverage`. Asset descriptor keys: `url,sha256,grid,nodeCount,edgeCount`.
Rows contain `[node,kills,deaths,meKills,meDeaths]`, sorted by node, with integer
counts before ordinary XY bin merging. Diagnostics count contributions:
`candidate,assigned,missingZ,ambiguous,offSurface,excluded`. Missing Z never assigns;
valid Z matches an exact sampled pixel only when precisely one ground node has
`-8 <= originZ-groundZ <= 80`. No nearby-pixel search. Below 70% assigned coverage,
the whole Smooth view visibly falls back; raw inspection counts remain unchanged.
The same 70% threshold also applies to the selected player's contributions in Me,
and independently to both populations in Difference, so high overall coverage
cannot hide missing positions for the population being displayed.

`allowedData` is one base64 byte per node. Configured floor bands intersect the
same admissible origin interval, avoiding an arbitrary standing-height guess and
accepting crouched/boundary events. Selected floors exclude other bands. In all-floor
view every overlapping configured band must allow the node footprint; bands without
configuration retain their surface. One allowed polygon must contain the entire
cell, with no boundary crossing its interior; corners split across separate regions
cannot bridge a narrow excluded gap, and concave notches are excluded. Blocked
polygon intersection is conservative, including walls thinner than a grid cell.

Positive density uses 24 local steps with alpha 0.24. Signed Difference independently
diffuses positive/negative evidence and confidence support; coincident XY chooses
one strongest surface instead of summing levels. The shader uses nearest sampling
for constrained fields, with a separate uniform from Difference smooth alpha.
Configured polygons also clip final display. Smooth texture uses geometry resolution,
Cells and Points retain original sample semantics. Density grid/fields and uploaded
textures are reused on redraw. Browser graph cache has at most three assets; downloads
are bounded to 6.5 MB, SHA-256 verified and generation-gated before applying scenes.
Static JSON enables gzip when Apache supports it. Inspection/source row cap remains
250,000 with the existing explicit overflow response, not truncated-looking success.

Image bytes and integer projection fields match exactly. Scale alone tolerates the
MySQL FLOAT roundtrip at relative 1e-6 (5.33333 versus 5.333333...), approximately
0.001 pixels over a native overview, while meaningful recalibration falls back.
Reference-scale identity includes the effective geometry SHA or ordinary fallback;
the displayed density unit includes actual cell dimensions.
