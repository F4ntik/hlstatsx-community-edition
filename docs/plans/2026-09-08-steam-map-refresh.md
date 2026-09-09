# Local Counter-Strike overview refresh

User explicitly requests all installed maps with overviews, replacing old map
images (including inferno), extracting BSP geometry and providing admin access.
Root executes without delegation. Local game files and the original port 8281
runtime are read-only; the active worktree and port 8382 are the update target.

- [x] Prepare all matched BSP/BMP/TXT maps with native-frame JPEGs, geometry SVGs,
  import reports and actual product coordinate rounding checks.
- [x] Back up existing images and DB configurations, replace matched base-map
  images and thumbnails, and apply matching native-frame settings in the lab.
- [x] Inspect contact sheets and representative actual public/admin pages,
  verify all served map dimensions/identities and persisted configurations.
- [x] Document extraction and the local result. Keep user-requested admin access.

Native BMP to JPEG changes only the green transparency key and JPEG encoding;
there is no image crop, warp, inferred alignment, or automatic walkability mask.
Custom variants without a matching installed BSP/overview are not relabelled as
standard maps. Original files/configurations are retained in a local backup.
