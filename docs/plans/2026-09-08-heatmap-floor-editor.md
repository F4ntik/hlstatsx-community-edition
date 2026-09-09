# Web floor and wall editor

User-authorized continuation; implemented by root without delegation.
The user requests settings for floors and walls instead of manual operations.
BSP revision tracking remains excluded.

- [x] Extend bounded floor polygons with excluded wall polygons; use identical
  membership in PHP aggregation and SQL inspection. Clip presentation and stop
  smoothing across cells intersected by walls.
- [x] Provide a map-adjacent floor editor with draw/finish/undo/cancel, individual
  contour removal, floor selection, and JPEG upload with size validation.
- [x] Allow preview-backed saving without landmarks when the persisted projection
  is unchanged. Preserve the existing landmark requirement for calibration edits,
  CSRF, actor, locking, stale checks and one-use preview tokens.
- [x] Verify focused PHP/JS contracts and the real browser create/draw/upload/save/
  reload flow in the disposable lab; restore fixtures and update the user guide.

Architecture: optional `blocked` world-XY polygons accompany each floor's
`regions`. They subtract from the allowed region union (or full image when no
regions exist). Public metadata exposes only projected contours. No BSP import
or automatic floor reconstruction is implied. The current map projection is
reused for drawing and separately guarded on save.
