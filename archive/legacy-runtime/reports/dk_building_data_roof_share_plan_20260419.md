# Roof-share identification — improvement plan for `dk-building-data`

**Author:** research note (Martin + Claude), 2026-04-19
**Status:** proposal
**Target repo:** `dk-building-data` (branch audited: `mc/3d-building-alignment`, head `c8a5f09a`)
**Scope:** `internal/alignment`, `internal/dhm`, `internal/fetcher/sources/{lidar, bygninger, colorizer, sunshadow}`
**Goal:** turn the existing DHM + Skraafoto + LiDAR + SAM3 stack into a per-roof-face *roof-share* output (one polygon per roof facet with azimuth, inclination, area, capture vintage, confidence) and use the result to fix the four pain points of scan-vs-DHM mapping (basements, extensions/verandas, azimuth, temporal mismatch).

This plan does **not** propose ripping out the current pipeline. Most of what we need is already implemented. The plan is four targeted additions, plus three cross-cutting cleanups.

> **Note on file location:** this document lives in the tirana repo because of workspace permission boundaries. When acted on, copy it to `dk-building-data/docs/roof-share-identification-plan.md`.

---

## 1. Why this document exists

We have repeatedly hit the same mapping problem: the iOS RoomPlan scan and the Danish national height model (DHM) do not register cleanly. The reasons we have catalogued are: basements are invisible in DHM by construction, verandas/extensions disagree in 3D volume, RoomPlan's compass is unreliable indoors, and the two datasets can be separated by 5+ years of construction history.

The deep-research report at `tirana/reports/dhm_for_roof_share_identification_20260419.md` argued that the right fix is architectural: stop trying to align scan and DHM symmetrically, anchor on GeoDanmark + DHM, and treat the scan as a downstream attribute provider for the interior. **An audit of `dk-building-data` shows that most of that architecture already exists.** What is genuinely missing is a small set of well-defined components that turn the existing per-point classification into a per-roof-face geometric output.

The rest of this document is the engineering work plan to close those gaps.

---

## 2. Current state (audit, 2026-04-19, branch `mc/3d-building-alignment`)

### What is already in place

| Capability | Location | Notes |
|---|---|---|
| GeoDanmark `Bygning` WFS fetcher | `internal/fetcher/sources/bygninger/bygninger.go` | Authoritative footprint geometry. |
| `målestedbygning` attribute extraction | `internal/fetcher/sources/bygninger/bygninger.go:448` | `Tag` / `Væg` / `Tag og Væg` already surfaced in summary. |
| BBR fetcher | `internal/fetcher/sources/bbr` | Attributes (anvendelseskode, kælder, year). |
| DHM REST point client | `internal/dhm/client.go` | `HentKoter` API, 50 pts/request batching. |
| DHM WCS raster client | `internal/dhm/wcs.go` | DSM (`dhm_overflade`) and DTM (`dhm_terraen`) at 1 m default. |
| DHM contours | `internal/dhm/contour.go` | |
| LiDAR Punktsky LAZ download | `internal/fetcher/sources/lidar/lidar.go` | `punktsky` (current), `punktsky2015`, `punktsky2007` selectable. |
| Skraafoto oblique fetcher | `internal/fetcher/sources/skraafoto` | |
| Orthophoto / DDO Hexagon | `internal/fetcher/sources/orthophoto` | |
| Matrikelkort fetcher | `internal/fetcher/sources/matrikelkort` | Used to crop SAM3 inputs to parcel. |
| Sunshadow analysis | `internal/fetcher/sources/sunshadow/{shadow,slope,sunshadow}.go` | Horn's-method slope, daylight-hour shadow accumulation. |
| Solar facilities WFS | `internal/fetcher/sources/solar/solar.go` | Existing PV installations from BPST. |
| **Procrustes + ICP 2D registration** | `internal/alignment/procrustes.go` (752 LoC) | `AlignOutlineToTarget`: coarse → fine angular search → ICP. |
| **Window-edge azimuth recovery** | `internal/alignment/procrustes.go::dominantEdgeAngleFromSegments`, `InitialAlignFromWindowEdges` (commit `c8a5f09a`, 2026-03-01) | Replaces compass with RoomPlan window normals; magnetometer only resolves 4-quadrant ambiguity. |
| Alpha-shape outline extraction | `internal/alignment/alphashape.go` | |
| Multi-storey vertical stacking | `internal/alignment/stack.go` | Slab thickness + DTM ground anchor. |
| Gap closure between storeys | `internal/alignment/gap.go` | |
| Full alignment orchestrator | `internal/alignment/align.go::Aligner.Align` | 8-step pipeline incl. footprint fetch + DHM elevation + Procrustes + stack + gap close. |
| `align-rbr` web tool | `cmd/tools/align-rbr/` | Leaflet map, 2-point manual override, 3D side view. |
| Colorizer pipeline | `internal/fetcher/sources/colorizer/` (38 files) | LiDAR + Skraafoto + DHM + matrikelkort + SAM3 fusion. |
| SAM3 building-part classes | `internal/fetcher/sources/colorizer/sam3_classifier.go:66-105` | `building`, `pool`, `terrace`, `stairs`, `roof_window`, `chimney`, `pv_panel`, `balcony`, `rooftop_terrace` — already classified per LiDAR point. |
| Per-building roof-height grid | `internal/fetcher/sources/colorizer/building.go:436-452::createRoofHeightGrid` | Max-Z per cell. |
| Per-cell local plane fit (roof) | `internal/fetcher/sources/colorizer/surface_interpolator.go:183-207::interpolateRoofSurfaces` | Local plane fits at 0.15 m grid spacing. |

### What this means

Re-stating the prior research recommendations against this audit:

| Prior recommendation | Actual status |
|---|---|
| Stop symmetric scan↔DHM registration | **Already done** — `Aligner.Align` is one-way (scan → footprint). |
| Switch footprint anchor from BBR to GeoDanmark | **Already done** — `bygninger` is the anchor; BBR is attribute-only. |
| Read `målestedBygning` and prefer `Tag` polygons | **Half done** — attribute is read but not yet used to filter polygons before clipping. |
| Per-tile density routing (RANSAC ≥8 pts/m² vs region growing) | **Not done** — but the colorizer uses SAM3, not RANSAC, so this branch may not apply. |
| Capture DHM/Oprindelse vintage metadata | **Not done.** |
| Procrustes 2D footprint registration | **Already done.** |
| Pilot Roofer | **N/A** — colorizer + SAM3 already produces roof-classified points; we need a downstream facet extractor, not a competing toolkit. |
| Multi-vintage diff for change detection | **Not done** — but `lidar.go` already exposes the vintages. |
| Cathedral-ceiling subtraction for insulation | **Not done.** |

The pipeline is in much better shape than the prior research assumed. The real gaps are smaller and more specific.

---

## 3. Real remaining gaps

### Gap A — No per-roof-face polygon output

The colorizer emits a point cloud where each point has `Classification ∈ {Building, RoofWindow, Chimney, PVPanel, Balcony, …}` and `surface_interpolator.go` does *local* plane fits to densify roof points. There is no step that:

1. Clusters roof points into discrete coplanar facets.
2. Emits a 2D polygon per facet (in UTM32N) with azimuth, inclination, area, point count.
3. Aggregates facets into per-building "roof shares" (e.g. "this house has 42 m² of south-facing 35° roof, 38 m² of north-facing 35° roof, 6 m² of flat dormer").

Without this, downstream consumers (PV potential, thermal modelling, energy assessment) have to re-derive facets themselves or rely on the national `sologvindinfo.dk` which is computed once per DHM vintage and may not match what we see for a specific building.

**Impact:** this is the single highest-value addition. It is the actual answer to the question "use the DHM for roof share identification."

### Gap B — DHM/Oprindelse vintage not captured

`lidar.go` exposes `DefaultDataSet = "punktsky"` plus `punktsky2015` and `punktsky2007` historical sets. But:

- The per-tile *capture date* (DHM/Oprindelse layer) is never recorded alongside the points.
- A building-level field `dhm_capture_date` does not exist anywhere in the result schema.
- We cannot tell a downstream consumer "this roof analysis is from 2019 LiDAR, but BBR says the property had a major renovation in 2022, so trust the 2022 BBR field 213 (basement) over the 2019 roof outline."

**Impact:** medium. Affects every output that mixes scan, BBR, and LiDAR data — i.e. all of them.

### Gap C — Multi-vintage diff for extension/veranda detection

We already download two or three Punktsky vintages on demand. We do not compare them. Yet a veranda built between 2015 and 2023 will appear as a building-classified delta in DSM differencing, with no scan/BBR involvement at all. This is the cleanest possible signal for "where has the building changed since the last full LiDAR sweep" and it is free.

**Impact:** medium-high. Directly addresses the third pain point ("verandas not in DHM"). Specifically, it tells us *whether* the veranda is in DHM, and if so, in which vintage.

### Gap D — Cathedral-ceiling subtraction for roof underside

RoomPlan reports `cathedralCeiling` planes. The DHM Punktsky gives us roof topsides. The vertical difference between them, sampled across the roof, is a proxy for roof thickness, which is in turn a proxy for insulation depth. This is a research direction, not a production feature.

**Impact:** low for the immediate roof-share goal, high for the medium-term energy-assessment goal.

---

## 4. Work packages

Each work package is sized for one engineer-week or less.

### WP-1 — Roof facet extractor (highest priority)

**New package:** `internal/roofshare/`

**Files:**

```
internal/roofshare/
  facet.go            // RoofFacet type, per-facet azimuth/inclination/area derivation
  cluster.go          // region-growing on roof-classified LiDAR points
  fit.go              // robust plane fit (RANSAC inside cluster) + normal → (az, incl)
  polygon.go          // alpha-shape projection to UTM polygon, hole carving for chimneys/PV
  share.go            // aggregation into per-building RoofShare
  share_test.go       // golden tests on 5–10 representative buildings
```

**Inputs:**
- `[]LiDARPoint` from the colorizer with `Classification ∈ {ClassBuilding, ClassRoofWindow, ClassChimney, ClassPVPanel}`.
- Optional GeoDanmark footprint polygon (for clipping; already fetched by the orchestrator).
- Optional `målestedbygning` value (`Tag` / `Væg` / `Tag og Væg`) from the same building record — when `Tag`, the polygon already represents roof projection and clipping should be tight; when `Væg`, expand by an eave allowance before clipping.

**Output schema (Go):**

```go
type RoofFacet struct {
    PolygonUTM32N      []Point2D `json:"polygon_utm32n"`     // closed CCW
    AzimuthDeg         float64   `json:"azimuth_deg"`         // 0=N, 90=E, ...
    InclinationDeg     float64   `json:"inclination_deg"`     // 0=flat, 90=vertical
    AreaM2             float64   `json:"area_m2"`             // planar area, not projected
    AreaProjectedM2    float64   `json:"area_projected_m2"`   // 2D footprint area
    PointCount         int       `json:"point_count"`
    PointDensityPerM2  float64   `json:"point_density_per_m2"`
    RANSACInliers      int       `json:"ransac_inliers"`
    RANSACInlierRatio  float64   `json:"ransac_inlier_ratio"`
    PlaneRMSE          float64   `json:"plane_rmse_m"`        // residual to fitted plane
    FacetType          string    `json:"facet_type"`          // "main" | "dormer" | "flat_cap"
    Holes              [][]Point2D `json:"holes,omitempty"`   // chimneys, PV cut-outs
    DHMCaptureDate     string    `json:"dhm_capture_date"`    // from WP-2
    Confidence         float64   `json:"confidence"`          // 0..1, see scoring rule
}

type RoofShare struct {
    BygningID          string      `json:"bygning_id"`         // GeoDanmark Bygning UUID
    BBRUUID            string      `json:"bbr_uuid,omitempty"`
    Facets             []RoofFacet `json:"facets"`
    TotalAreaM2        float64     `json:"total_area_m2"`
    TotalProjectedM2   float64     `json:"total_projected_m2"`
    AzimuthHistogram   map[string]float64 `json:"azimuth_histogram_m2"` // 8-bin: N,NE,E,SE,S,SW,W,NW + flat
    InclinationHistogram map[string]float64 `json:"inclination_histogram_m2"` // <10°, 10-25°, 25-45°, 45-60°, >60°
    DHMVintage         string      `json:"dhm_vintage"`        // "punktsky" | "punktsky2015" | "punktsky2007"
    DHMCaptureDate     string      `json:"dhm_capture_date"`
    GeneratedAt        time.Time   `json:"generated_at"`
}
```

**Algorithm sketch:**

1. **Filter.** Keep points where `Classification == ClassBuilding` and `HeightAboveGround > 1.5 m`; exclude `ClassPVPanel`/`ClassChimney`/`ClassRoofWindow` initially, save them for hole carving.
2. **Cluster** (`cluster.go`). Region-growing on per-point local normals (compute via PCA on k=12 nearest neighbours). Seed = highest unassigned point. Grow if normal angle deviation < 10° and Z gap < 0.3 m. Reject clusters with fewer than `max(20, density_per_m2 * 1.0)` points. This is the Awrangjeb–Fraser approach and works at the 4–8 pts/m² densities we see in DK.
3. **Fit** (`fit.go`). Inside each cluster, run RANSAC plane fit (max 100 iterations, inlier threshold = `0.5 * point_spacing` clamped to [0.05 m, 0.20 m]). Re-fit by least squares on inliers. Reject clusters with inlier ratio < 0.6.
4. **Project + outline** (`polygon.go`). Project inliers onto the fitted plane; rotate to local 2D; alpha-shape outline (reuse `internal/alignment/alphashape.go`); reproject back to UTM XY; close polygon.
5. **Hole carving.** For PV/chimney/roof-window points falling inside a facet polygon, alpha-shape them and carve as holes. Skip holes < 0.25 m².
6. **Clip to footprint.** If the facet polygon extends beyond the GeoDanmark `Bygning` polygon by more than 0.5 m, clip with Sutherland–Hodgman. (Use a tighter clip when `målestedbygning == "Tag"`.)
7. **Derive azimuth & inclination** from the unit normal: `incl = acos(|n_z|)`, `az = atan2(n_x, n_y)` normalised to `[0, 360)` with the convention that flat (`incl < 5°`) is reported as `azimuth = NaN` and `facet_type = "flat_cap"`.
8. **Confidence score:** `0.4 * inlier_ratio + 0.3 * min(1, density / 8) + 0.2 * (1 - clamp(plane_rmse_m / 0.15, 0, 1)) + 0.1 * (1 - clip_correction_ratio)`. Document the formula in `share.go`.

**Acceptance criteria:**

- On a hand-picked set of 10 single-family Danish houses (pick 5 simple gables, 3 hip roofs, 2 mansards), the output facet count matches manual count (from skråfoto inspection) ±1 in 9/10 cases.
- Total roof area within 10% of `Tag` footprint area for 8/10 cases.
- Per-facet azimuth within 10° of azimuth measured from skråfoto for 9/10 cases.
- Confidence < 0.5 correctly flags the cases where the algorithm fails (we want graceful degradation, not silent wrong answers).
- Unit tests (`share_test.go`) cover: synthetic gable, synthetic hip, synthetic flat-with-dormer, edge case of single-point cluster, edge case of degenerate near-vertical facet.

**Out of scope for WP-1:**

- LoD2 polyhedral assembly (PolyFit/City3D-style). We emit *facets*, not a watertight roof solid. If we need watertightness later, add a WP-5 to wrap Roofer/3DBAG.
- Deep-learning segmentation (RoofN3D, RoofSeg). Region-growing + RANSAC + SAM3 priors are sufficient for the densities and roof complexity we see in DK residential.
- Gable/hip line topology extraction. Adjacency between facets is implied by their polygons; if downstream consumers need explicit ridge/eave/hip lines, add a WP-6.

---

### WP-2 — DHM/Oprindelse vintage capture

**Edit:** `internal/fetcher/sources/lidar/lidar.go`, `internal/dhm/wcs.go`.

**New file:** `internal/dhm/oprindelse.go`.

**Tasks:**

1. Add a new method `Client.OprindelseAt(ctx, lat, lng) (CaptureMetadata, error)` to `internal/dhm/`. Backed by the WMS/WFS Oprindelse layer at `https://services.datafordeler.dk/DHMOprindelse/...`. Response includes `dataset_id`, `capture_date` (string `YYYY-MM-DD`), `source` (e.g. `Cowi/Terratec`), `resolution_m`.
2. Extend `lidar.LiDARResult` (or whichever struct holds the LAZ download outcome) with `CaptureDate string` and `OprindelseDatasetID string` fields.
3. In the lidar fetcher's main entry, after locating the tile, call `OprindelseAt` for the tile centroid and populate the new fields. Cache per tile (one Oprindelse lookup per LAZ tile is enough; the layer is per-tile not per-point).
4. Plumb `CaptureDate` through `colorizer.PipelineContext` so downstream stages (and the new `roofshare` package) can stamp it on outputs.

**Acceptance criteria:**

- For 5 randomly chosen DK addresses, the returned `CaptureDate` matches the date shown on https://dataforsyningen.dk's DHM coverage map within ±1 day.
- The field appears in `RoofShare.DHMCaptureDate` output (WP-1 dependency).
- Fallback behaviour: if Oprindelse query fails, log a warning and emit `CaptureDate = ""` rather than failing the whole pipeline.

**Estimated effort:** 1 day including tests.

---

### WP-3 — Multi-vintage Punktsky diff for change detection

**New file:** `internal/roofshare/changedetect.go` (or a new package `internal/dsm_diff/` if scope grows).

**Tasks:**

1. New function `DetectExtensions(ctx, footprint, vintages []string) (ChangeReport, error)`.
2. For each vintage in `{punktsky2015, punktsky}` (and optionally `punktsky2007`), fetch DSM raster for the footprint bbox at 1 m resolution via `dhm.WCSClient.FetchDSM`.
3. Subtract: `delta = DSM_recent - DSM_old`. Mark cells where `delta > 1.5 m` as "added building mass" and `delta < -1.5 m` as "removed."
4. Cluster the added cells (4-connectivity), filter clusters < 4 m², emit each cluster as a polygon with attributes `{capture_date_old, capture_date_new, max_height_added_m, area_m2, classification_guess}` where the guess is one of `"new_building" | "extension" | "raised_roof" | "veranda" | "demolition"`.
5. Cross-reference the clusters with BBR `byg026Opførelsesår` (construction year) and `byg027Tilbygningsår` (extension year). If a cluster is inside a `Bygning` whose `Tilbygningsår` falls between the two vintage dates, classify as "extension." If no BBR match, "unmapped change" — flag for manual review.

```go
type ChangePolygon struct {
    PolygonUTM32N    []Point2D `json:"polygon_utm32n"`
    AreaM2           float64   `json:"area_m2"`
    MaxDeltaZM       float64   `json:"max_delta_z_m"`
    OldVintage       string    `json:"old_vintage"`
    OldCaptureDate   string    `json:"old_capture_date"`
    NewVintage       string    `json:"new_vintage"`
    NewCaptureDate   string    `json:"new_capture_date"`
    Classification   string    `json:"classification"`     // see above
    BBRBygningID     string    `json:"bbr_bygning_id,omitempty"`
    BBRTilbygningsår int       `json:"bbr_tilbygnings_aar,omitempty"`
}

type ChangeReport struct {
    Footprint   []Point2D       `json:"footprint"`
    Added       []ChangePolygon `json:"added"`
    Removed     []ChangePolygon `json:"removed"`
    GeneratedAt time.Time       `json:"generated_at"`
}
```

**Acceptance criteria:**

- For 5 buildings known to have had verandas added between 2015 and 2023 (we can pick from BBR's `byg027Tilbygningsår`), the detector flags an `Added` polygon overlapping the BBR record in 4/5 cases.
- For 5 buildings with no recorded changes, the detector flags ≤ 1 spurious added polygon (typically vegetation or solar panels).
- Output is consumable by the web extension as a GeoJSON layer.

**Estimated effort:** 2–3 days including tuning of the 1.5 m threshold.

---

### WP-4 — Cathedral-ceiling subtraction (research, not production)

**New file:** `internal/alignment/insulation.go` (alongside the existing alignment work).

**Tasks:**

1. After `Aligner.Align` produces an `AlignedModel` with cathedral ceiling planes, sample each ceiling plane on a 0.25 m grid in UTM32N.
2. For each sample point, query DHM Punktsky for the topmost point within a 0.3 m radius — this gives the roof topside Z at that XY.
3. Compute `roof_thickness_m = roof_top_z - ceiling_underside_z`. Aggregate per ceiling plane.
4. Emit a `RoofThicknessReport{ MeanThicknessM, MedianThicknessM, P10ThicknessM, P90ThicknessM, SampleCount, CeilingPlaneID }` per cathedral plane.
5. Cross-reference with BBR insulation fields where present (`enh020Energimærke`, `byg056Varmeinstallation` adjacencies).

**Acceptance criteria:**

- For 3 hand-picked cathedral-ceiling rooms, the median thickness is within 30% of the value reported in the EPC (energy performance certificate) insulation depth field. (We expect noisy results — this is research.)
- Output is emitted but explicitly flagged as `experimental: true` until validated on ≥ 30 buildings.

**Estimated effort:** 2–4 days. Mark the package as `// EXPERIMENTAL` in the doc comment.

---

## 5. Cross-cutting cleanups

These are small, do them alongside any of WP-1..3.

### CC-1 — Use `målestedbygning` to pick the right footprint polygon

`bygninger.go:448` already extracts the attribute. Add a helper:

```go
// PreferredFootprint returns the polygon best suited for roof clipping.
// When målested == "Tag", the polygon is already the roof projection.
// When målested == "Væg", expand outward by eaveAllowanceM (default 0.5m).
// When målested == "Tag og Væg" (or empty/unknown), use the polygon as-is.
func (b *Bygning) PreferredFootprint(eaveAllowanceM float64) Polygon
```

And use it in:
- `internal/alignment/align.go` (anchor for Procrustes).
- `internal/roofshare/polygon.go` (clipping in WP-1).
- `internal/fetcher/sources/colorizer/parcel_crop.go` if appropriate.

**Effort:** half a day.

### CC-2 — Per-tile density check, surfaced not enforced

In `internal/fetcher/sources/lidar/lidar.go`, after parsing the LAZ header (or the bbox + point count), compute `density_per_m2` and attach it to the result. Do not branch on it — log it as a structured field so we can audit which tiles are dense enough for which algorithms. The actual algorithm choice stays inside `roofshare/cluster.go` (region-growing handles 2 → 20 pts/m² without a hard branch).

**Effort:** half a day.

### CC-3 — DAWA → DAR sweep

`docs/` includes references to DAWA. The DAWA → DAR retirement is announced for 2026-07-01. Search the codebase for `dawa.dataforsyningen.dk` and `dawadocs` and replace any production paths with the Datafordeler DAR equivalent. Track in a separate ticket; this is unrelated to roof shares but it shares the same Datafordeler credential infrastructure and is the most likely thing to silently break for unrelated parts of the system.

```bash
grep -r "dawa" --include="*.go" --include="*.ts" --include="*.tsx" .
```

**Effort:** unknown, scope first.

---

## 6. Sequencing

```
Week 1:  WP-1 (roof facet extractor) + CC-1 (målested helper)
Week 2:  WP-2 (Oprindelse vintage) + CC-2 (density logging)
Week 3:  WP-3 (multi-vintage diff) + integration with web extension layer
Week 4:  Validation pass on 50–100 buildings; tune thresholds
Later:   WP-4 (cathedral subtraction, experimental); CC-3 (DAWA sweep)
```

Total: ~3 weeks of focused work to deliver per-building roof-share data with vintage metadata and change detection. WP-4 is research and should not block the rest.

---

## 7. Open questions (decide before starting)

1. **Schema location.** Do `RoofFacet` / `RoofShare` live in `internal/roofshare/` only, or do we also expose them in `internal/models/` as part of the public API surface? Recommendation: define in `roofshare`, re-export from `models` only when an HTTP handler needs them.
2. **API endpoint shape.** `GET /api/v1/property/roofshare?bbruuid=...` returning `RoofShare`, or fold into existing `GET /api/v1/property/...` mega-response? Recommendation: separate endpoint — the computation is heavier than other property attributes and benefits from its own cache.
3. **Caching.** Roof-share output is stable per DHM vintage. Cache key = `(bygning_id, dhm_vintage)`, TTL until next national LiDAR sweep is announced. Storage: GCS like the other heavy outputs?
4. **Manual override path.** When confidence < 0.5 or the user disagrees, do we surface a "manual roof tracing" UI in `align-rbr` (it already has a Leaflet map), or is that a separate tool? Recommendation: extend `align-rbr` rather than spawn another tool.
5. **Cross-check against `sologvindinfo.dk`.** Should the API surface a "national_estimate_disagreement" flag when our roof-share output differs by > 20% from the national portal? Recommendation: yes — cheap to compute, useful for QA. Owner: someone needs to figure out the sologvindinfo data ingestion path; it may be a Septima dataset on Datafordeler.

---

## 8. References

- Audit branch: `mc/3d-building-alignment` in `dk-building-data`, head `c8a5f09a` (2026-03-01).
- Background research: `tirana/reports/dhm_for_roof_share_identification_20260419.md`.
- Awrangjeb–Fraser region-growing: Awrangjeb M., Fraser C. S. (2014). "Automatic Segmentation of Raw LIDAR Data for Extraction of Building Roofs." Remote Sensing 6(5):3716–3751. DOI: 10.3390/rs6053716.
- Schnabel RANSAC: Schnabel R., Wahl R., Klein R. (2007). Computer Graphics Forum 26(2):214–226. DOI: 10.1111/j.1467-8659.2007.01016.x.
- 3DBAG / Roofer (alternative path if WP-1 region-growing proves insufficient): Peters R. et al. (2022). PE&RS 88(3):165–170. DOI: 10.14358/PERS.21-00064R2. https://github.com/3DGI/roofer.
- DHM v1.0.0 specification (Klimadatastyrelsen / SDFI): https://sdfi.dk/produkter-og-ydelser/produktkatalog-data/danmarks-hoejdemodel.
- ISPRS Vaihingen benchmark for evaluation methodology: https://www2.isprs.org/commissions/comm2/wg4/benchmark/.
