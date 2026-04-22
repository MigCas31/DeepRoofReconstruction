# Tracking Progress

Chronological log of all changes to `reconcile/`, `reconcile_v2/`, and `reconcile_v3/`.
Each entry documents **what changed**, **why**, the **result**, and critically: **what went wrong and what we learned**.

This document covers 12 days of intensive work (April 9-20 2026) across 92 Claude sessions and 2,488 conversation turns. The goal is to prevent colleagues from repeating our mistakes.

---

## What We're Building

**Goal**: Reconstruct a 3D polyhedral model of a building from Apple RoomPlan scan data. The output should be a watertight (or near-watertight) shell representing the building envelope: walls, floors, ceilings, and roof surfaces. This model feeds Danish EPC (energy performance certificate) calculations — heated floor area, envelope surface area + orientation, U-values, roof type + inclination.

**The input**: RoomPlan gives us per-room data: wall polygons (4-6 corners), floor polygons, doors, windows, and wall segment metadata (azimuth, inclination). Multiple rooms are scanned per building, sometimes across multiple ARKit sessions. Apple merges these into a single model, but the merge is lossy — wall thickness becomes uniform, floor heights get averaged. We work from the per-room data, not the Apple merge.

**The hard part**: RoomPlan **does not capture ceiling geometry**. Ceilings must be inferred from wall evidence — pentagon-shaped walls encode gable pitch, wall segment inclination/azimuth fields encode slope direction. For flat-roofed rooms this is trivial (ceiling = wall top height). For sloped roofs (gable, hip, mansard, dormer) it's a reconstruction problem.

**What the polyhedron needs**: For each building, produce polygon surfaces for: (1) floor slabs per story, (2) exterior walls forming the vertical envelope, (3) interior walls separating rooms, (4) ceiling/roof surfaces closing the top — flat where flat, sloped where sloped, with correct ridge lines, valleys, and hip lines. Gaps and dormers must be handled. The result should look like the actual building when rendered in Three.js and should produce correct areas/orientations for the energy model.

## Techniques Tried: The Evolution

The project went through **four distinct technical approaches** over 12 days. Understanding why each one was tried and why we moved on is critical for colleagues.

### Approach 0: Roof Boundary Detection via "Scanning Upward" (Apr 10 — FAILED, predates pipeline)
**Idea**: Before the roof pipeline existed, we tried to detect roof boundaries directly from building outlines. Use the maximum XZ boundaries of the building, then "scan upward" to find each maximum Z point within those boundaries. Martin's idea: "use the maximum x,y boundaries for the entire building, and then scan upwards to find each maximum z point."
**Techniques tried**: (1) Find outer building boundary from wall top edges, (2) Delaunay/alpha shape triangulation of boundary points, (3) dominant plane detection from wall heights, (4) ridge detection from "kinks" in the height surface.
**Problems**: Building outlines were wrong ("red building outlines are wrong. I don't know why."). The approach created "weird shapes where the plane is actually flat" — artificial local optima in the height surface. The "double kink" problem: instead of finding one ridge, it created two dips flanking the actual ridge. Martin: "really the vertices should be a good sign of where the ridge is." Ceilings were "not continuous... it makes 0 sense" and "goes WAY beyond the boundaries of the wall edges."
**Martin's frustration level**: "wtf that's terrible?", "still completely useless", "it still sucks. the ceilings are not continuous", "I'm a bit at loss about what our strategy should be i have to be honest."
**Key insight that survived**: Martin's idea to "start with horizontal polygons top-to-bottom using plane Z, then fill X,Y with oblique planes limited by building boundaries" — this became the volume-based ceiling construction approach in Approach 2.
**Status**: Fully abandoned. Code removed.

### Approach 1: Per-Room Heuristics (Apr 9 — FAILED)
**Idea**: For each room independently, infer ceiling geometry from wall polygon corners.
**Techniques tried**: (1) chain upper wall corners into ceiling contour, (2) detect height variance to classify flat vs sloped, (3) find perpendicular walls as ridge indicators, (4) cluster wall top heights, (5) use segment inclination/azimuth fields, (6) extract slope from gable wall top edge.
**Why it failed**: Scan noise (6-10cm), missing data (many segments lack inclination), ambiguity (adjacent room height differences vs actual slope), and fundamentally: rooms don't know about each other. A gable roof spans multiple rooms — you can't detect it from one room's walls alone.
**Status**: Abandoned. Code remains in `extract_3d.py` as `_infer_ceilings()` but is not used.

### Approach 2: Building-Wide Roof Pipeline + Cell Decomposition (Apr 11-16 — PARTIALLY SUCCESSFUL)
**Idea**: Cluster wall segments across the entire building by inclination and azimuth to find roof planes. Build a 3D cell complex (polyhedral decomposition) to classify volumes as room/attic/outside. Derive ceiling surfaces from cell boundaries.
**Techniques used**: (1) oblique segment clustering, (2) flat roof detection from exposed wall tops, (3) multi-stage ceiling clipping (footprint narrowing, L-junction valley synthesis, opposing plane cuts, height caps), (4) exact-on-lattice polyhedral kernel for cell construction, (5) top-boundary graph for semantic role assignment (flat ceiling, attic floor, sloped roof, knee wall).
**What worked**: Clustering is solid — correctly identifies roof planes ~97% of the time. Cell decomposition correctly models room/attic/outside volumes. Parity with legacy heuristic baseline reached 99.88% shell overlap, 99.56% semantic overlap.
**What didn't work**: (1) 950-line `thermal_ceiling.py` with cascading fallbacks became unmaintainable, (2) thresholds scattered across 7+ files, (3) each fix added a parameter + silent-failure path (whack-a-mole), (4) per-atom semantic decisions couldn't capture building-level roof topology (the "attic-over-slope bias" — rooms under sloped roof rendered as flat attic because local atom reasoning couldn't propagate regional evidence).
**Status**: V1/V2 pipeline still runs and produces the current `buildings_3d.json` and `roof_algorithms_py_results.json`. The cell decomposition and topology graph are architecturally sound but the roof surface selection on top is too heuristic-driven.

### Approach 3: Per-Segment ML Classification (Apr 18-19 — ABANDONED)
**Idea**: Train a GBM classifier on human-labeled roof segments. For each candidate segment, predict accept/reject. Use feature expansion (150+ features) and grouped cross-validation.
**Techniques used**: (1) permissive candidate generation (every cluster × slab pair), (2) human labeling via viewer UI (8,865 labels across 111 buildings), (3) LightGBM with GroupKFold(building_uuid), (4) SHAP for feature importance.
**Why it failed**: F1 plateaued at 0.84 with 22% per-segment review rate. The fundamental problem: **independent per-segment classification loses building-level topology**. A segment that's "correct" in isolation may conflict with other segments at the building level (overlapping planes, impossible angles, coverage gaps). Martin's insight: "but it is easy for 97% of properties. i just don't know if looking at each segment is correct."
**Status**: Labels preserved in `v3_roof_proposal_labels.jsonl`. GBM scores repurposed as a prior for the BIP solver (Approach 4). The classifier itself is not used for final decisions.

### Approach 4: Building-Level Reconstruction via Binary Integer Programming (Apr 19-20 — CURRENT)
**Idea**: Reframe from "classify each segment" to "select and clip a subset of plane hypotheses that form a valid roof envelope." This is a constrained optimization problem, not a classification problem.
**Key reframing** (Martin): "for me we have all the planes. we just need to figure out which planes to pick and how to cut them."
**Techniques used**: (1) generate candidate faces by pairwise-intersecting plane hypotheses and clipping to footprint (13,105 candidates across 223 buildings), (2) formulate as BIP: maximize coverage quality − complexity, subject to footprint coverage, non-overlap, azimuth coherence, topology connectivity, (3) Python-mip with CBC solver, (4) realism scorer (IoU vs reference), (5) hyperparameter search (100 trials on 20-building pilot), (6) building-level triage (auto-accept vs review).
**What works so far**: Candidate generation complete. Ridge/eave scoring using `shapely.ops.split` (shape-based, no hardcoded heuristics). Viewer integration for visual validation.
**What's in progress**: BIP solver core, hyperparameter optimization, triage policy.
**Target**: ≤10% of buildings need human review (ideally ≤5%). For ~97% of buildings, the geometry + constraints should determine a unique valid envelope.
**Status**: Active development track.

### Approach 2.5: Wall Thickness & Coplanar Merging via Topology (Apr 10 — PARTIALLY SUCCESSFUL)
**Idea**: Build a topology graph that merges coplanar adjacent wall segments across rooms, infers wall thickness from the gap between deduplicated walls, and produces a clean IFC-aligned model.
**Why**: Martin identified early that "the distance between walls that are deduplicated is a better representation of the thickness of the walls - apple merge seems to set them as uniform." The Go backend (calor) already did some of this.
**Techniques tried**: (1) ST_ApproximateMedialAxis / Voronoi diagrams for centerline extraction (researched online), (2) coplanar plane merging with tolerance-based stitching, (3) wall segment intersection and face splitting.
**Problems**: "it is not working for complex geometries (gable walls etc)" — convex/concave polygon merging failed on non-rectangular walls. "still a lot of not merged co-planes on all floors" — the merging tolerance was too strict. Martin: "come on. it's super fractured? i don't get it." Wall faces from different rooms had slightly different normals, causing coplanarity test failures. Also: "i can see far from all coplanar planes have been merged."
**Partial success**: Wall thickness inference works for simple adjacent rooms. Used in `reconcile_v2/wall_thickness_inference.py`.
**Status**: Wall thickness inference kept. Full coplanar merging deferred — the V3 approach handles this at the plane level instead.

### Approach 2.6: External Data Augmentation Research (Apr 13 — RESEARCHED, NOT IMPLEMENTED)
**Idea**: Use external Danish geodata (nDSM height maps, LiDAR point clouds, SAM3 segmentation, skråfoto oblique photos) to solve the zone decomposition problem for complex buildings.
**Why**: Martin: "but that's not true. our problem is with complex geometries (building extensions, multiple building zones, scanned zones can be outside the BBR official stories, etc). Please really check online and understand."
**Research findings**: nDSM height discontinuities are the strongest external signal for detecting building extensions at different heights. Per-zone LiDAR plane fitting (not global segment clustering) is the right approach. SAM3 on orthophotos can visually confirm zone boundaries. GeoDanmark footprints help identify unscanned zones. BBR should be a soft prior, not a hard constraint.
**Why not implemented**: The critical blocker is registration between scan-local coordinates and UTM32N, especially for multi-session scans with coordinate breaks. Also, Martin rejected BBR as ground truth: "We will not use BBR as it is too crude."
**Status**: Research documented. Integration architecture designed but not built. Flagged for potential future use if scan-to-UTM registration is solved.

### Approach 2.7: Heuristic-to-Graph Migration (Apr 12-14 — IN PROGRESS)
**Idea**: Systematically migrate from geometric heuristics (hardcoded thresholds) to graph-based logic (topological constraints).
**Five rule families identified**: (1) exterior gap indicators → `EXPOSES_TO` edges, (2) floor overlap → `INTERFERES` edges, (3) wall stitching → `CONNECTS_TO` with junction classification, (4) ceiling clipping → `ABOVE/BELOW` constraints, (5) thermal ceiling → face class from room-top boundary.
**Roof heuristic audit**: Separated rules into "geometric" (should stay: inclination filters, azimuth computation, plane normals) vs "topological" (should migrate: room eligibility via `has_floor_above()`, exposed-room selection, dormer gating).
**Status**: Partially migrated. `classify_roof_room()` uses partial graph relations. Building-part decomposition uses graph. Full migration to cell-boundary-driven logic not yet done.

### Viewer Evolution: Pascal Editor as Styling Reference (Apr 10)
**Why**: Martin wanted the viewer to look professional. "I imagine there are window frames and door frames?" and "please look at pascal" (referring to github.com/pascalorg/editor). Multiple iterations on door/window styling: "the doors doesn't look that good. Please really investigate how pascal does it" and "I still think it's looking not as good as pascal, especially the doors."
**Specific issues**: (1) Door/window mullion crosses in wrong alignment, (2) jittery center rectangles, (3) shadow inconsistency across wall facades — "why are those facades not treated uniformly by the shadow?" Martin: "it simply doesn't know what's inside and outside. but this makes very little sense."
**Result**: Door/window cutouts with frames, ambient occlusion shadows, floor rendering. Not Pascal-quality but functional.

### Techniques Considered But Not Tried
- **CGAL Kinetic Surface Reconstruction**: Wrong tier — designed for dense point clouds, not parametric RoomPlan data.
- **PolyRoom / PolyDiffuse**: Research-grade, no RoomPlan compatibility.
- **HouseDiffusion**: Generative (creates new buildings), not reconstruction.
- **Manifold library**: Recommended by deep research as replacement for custom exact kernel. Not yet evaluated — would replace `polyhedral_kernel.py`.
- **ARKit mesh + depth frames**: Available on same device as RoomPlan but not currently captured. Would provide actual ceiling geometry if captured. Separately investigated in the room-by-room iOS repo (Apr 2): Martin discussed stair scanning, cross-session floor registration, ARWorldMap persistence across floors. Key finding: "relocalisation can often take 30s, it's not trivial for the user." Decided to capture staircase scans + mesh without ARWorldMap persistence, do matching server-side from timestamps.
- **BBR roof type as strong prior**: Rejected by Martin — "We will not use BBR as it is too crude. Our problem is determining the extent of the gable roof where BBR is general."
- **Hopper (iOS instrumentation)**: Used in parallel iOS debugging sessions for memory leak investigation in the material builder, not for tirana geometry work.

---

## Phase 1: Foundation — The First Day (2026-04-09)

### 2026-04-09 — Initial reconciliation pipeline
**Changed**: Created `reconcile/` package from scratch: `cli.py`, `loader.py`, `matcher.py`, `trust_merge.py`, `story_fix.py`, `floor_gaps.py`, `cross_floor_gaps.py`, `validation.py`, `output.py`, `extract_3d.py`, `models.py`, `transform.py`, `room_alignment.py`, `viewer.html`
**Why**: Lun Energy surveyors scan Danish homes with Apple RoomPlan (iOS). Each building produces multiple scan sessions that need to be reconciled into a single coherent 3D model. No Python pipeline existed — the Go backend (calor) had partial logic but nothing for offline analysis of the full 225-building corpus.
**Key design decision**: Martin confirmed early: "the target for room and floor alignment and building coherence is the json in pipeline folder, right? not the floor level merged json." Also: "i also believe the floor height (bottom of walls) is better at individual room level" and "the distance between walls that are deduplicated is a better representation of the thickness of the walls - apple merge seems to set them as uniform which also worsens the metric accuracy." These three insights shaped the entire pipeline — work from individual room data, not Apple's merged model.
**Result**: Full pipeline operational. Reconciled output for 223/225 buildings (2 had missing merged.json). Three.js viewer with merged/raw wall toggle, floor polygons, gap visualization. Quality classification per building. Commit `006ff97`.

### 2026-04-09 — Cross-floor gap detection: three iterations in one day
**Changed**: `reconcile/cross_floor_gaps.py`, `reconcile/floor_gaps.py`, `reconcile/viewer.html`
**Why**: Vertical gaps between floor levels are the most visible reconstruction artifact — walls stop short of the floor above, creating holes in the 3D model. Martin spotted this immediately on Skovmærkevej 5: "there is clearly a gap between the basement and first floor."

**Iteration 1 — hull.difference (WRONG)**: Used `hull.difference(footprint)` which detected exterior building shape indentations (large triangles), not the thin inter-room gap strips we needed.

**Iteration 2 — morphological close + pairwise buffer**: Replaced with two-phase: (1) `footprint.buffer(0.20).buffer(-0.20).difference(footprint)` for enclosed voids, (2) pairwise buffer-intersect with STRtree spatial index for adjacent rooms (distance < 0.40m). Scoring: 25% area + 20% compactness + 20% perimeter + 15% consistency + 20% raw wall coverage.

**Iteration 3 — convex hull clipping (bug fix)**: Buffering by 0.20m created rounded extensions at strip ends that protruded beyond room boundaries. Fix: clip gap to convex hull of the two rooms — 3-line change.

**Remaining limitation discovered later**: Building Enebærvej 6 has rooms 1.19m apart — gaps wider than 0.40m threshold are missed. Increasing WALL_HALF from 0.20→0.40 would bridge up to 0.80m but we deferred this.

**Lesson for colleagues**: Gap detection thresholds (WALL_HALF=0.20m, MAX_GAP=0.40m) are conservative. Danish houses can have 0.6-1.2m gaps between rooms. If you see missing gaps, check the threshold first.

### 2026-04-09 — Floor slab & wall overlap clipping: a dangerous heuristic
**Changed**: `reconcile/extract_3d.py`
**Why**: RoomPlan produces overlapping floor polygons (same room scanned twice) and multi-floor wall overlaps (stairwells spanning stories).
**Approach**: Group rooms by story, sort by area (largest wins), subtract prior rooms' polygons via Shapely. Clamp wall top Y to next story's floor Y.

**Bug discovered (IMPORTANT)**: `_clip_floor_overlaps()` removed ALL walls from the smaller room whose XZ midpoint falls in the overlap zone — including external boundary walls that should be kept. Martin noticed: "wait it seems now you clipped all half floors." Buildings affected: Bakkegårdsvej 46 (Rooms 4, 7 lose all walls), Berildsvej 42, Bøgebakken 3 (Rooms 0, 3, 6).

**Root cause**: Midpoint-in-overlap test doesn't distinguish internal shared walls from external boundary walls. For long walls, midpoint can be outside overlap region while the wall segment still crosses it.

**Lesson for colleagues**: The midpoint-based wall selection heuristic in `_clip_floor_overlaps()` is known to be too aggressive. 31/223 buildings have same-story room-floor overlap > 0.5 m². Don't trust it blindly — it was never properly fixed, just worked around.

### 2026-04-09 — Sloped ceiling inference: SIX failed attempts
**Changed**: `reconcile/extract_3d.py` (multiple iterations of `_infer_ceilings()`)
**Why**: RoomPlan doesn't capture ceiling geometry. Top-story rooms under sloped roofs have pentagon/hexagon-shaped wall polygons whose top edges encode the roof slope. We must infer ceilings from walls.

**Attempt 1 — top contour chaining**: Extract upper wall corners → chain into ceiling polygon → triangulate via XZ projection. **Failed**: 6-10cm scan noise makes corner chaining unreliable.

**Attempt 2 — height variance detection**: Classify walls as slanted (top Y range > 0.15m) → project floor up. **Failed**: couldn't determine slope direction from individual walls.

**Attempt 3 — perpendicular flat walls as ridge indicators**: Find flat-topped walls perpendicular to slanted walls → ridge direction is perpendicular. **Failed**: many rooms have no clear perpendicular pair.

**Attempt 4 — height clustering**: Cluster wall tops by height to find ridge/eave. **Failed**: half-levels and split-story buildings create ambiguous clusters.

**Attempt 5 — segment inclination/azimuth fields**: Use wall segment inclination/azimuth directly. **Partial success** but too few segments have this data.

**Attempt 6 — gable wall top edge (breakthrough)**: Martin's insight: "the slant is in the wall segment itself" — gable-end walls directly encode roof pitch. Ridge direction is perpendicular to gable. Algorithm: classify by top Y range → extract slope from highest-to-lowest corner → cluster by direction (±15°) → project onto floor with clamping.

**Result**: Approach 6 validated conceptually but not production-ready. Martin's verdict after seeing the results: "it is far from good enough. It seems the algorithm is not the right one... and it seems it's not following a strong logic enough."

**Decision**: Defer ceiling inference to a proper roof pipeline rather than more `extract_3d.py` hacking. This led directly to Phase 3 (the roof detection pipeline).

**Lesson for colleagues**: Per-room, per-wall ceiling inference fundamentally doesn't work. You need a building-wide pipeline that clusters segments across rooms. Don't go back to per-room approaches.

### 2026-04-09 — Wall extension strips: overlaps and doors
**Changed**: `reconcile/extract_3d.py`, `reconcile/viewer.html`
**Why**: Raw walls on story N stop short of the floor slab of story N+1, creating visible vertical gaps.
**Approach**: Extend wall's top Y to meet nearest slab above. Store original + extension strip for viewer.

**Problems Martin spotted**:
- "some of the extensions overlap on existing walls" — extensions were being generated even when a wall already reached the slab
- "ok, not sure if clamping means it gets cut? right now it seems the doors are too tall (ie extend more than they should)" — doors/windows were being extended past their natural height
- "I don't think mean height is correct here. It should maybe compute the height of the closest?" — using mean slab height instead of closest slab height created incorrect extensions

**Fix**: Nearest-slab lookup instead of mean; skip extensions where wall already reaches slab; clamp door/window heights separately.

### 2026-04-09 — Split-level houses: wall clipping breaks
**Changed**: `reconcile/extract_3d.py`
**Why**: Martin found Bakkevej 2 (split-level, 3 stories at ~1.3m offsets vs normal ~2.5m) where wall clipping went horribly wrong: Story 0 walls (median 2.27m) clipped to 1.37m, Story 1 stairwell walls (3.75m) clipped to 1.23m. 88/143 walls affected.
**Root cause**: Fixed inter-story gap assumption — `_clip_walls_to_story_bounds` uses ceiling = next story's floor Y. For split-levels, the "next story" is only 1.3m above.
**Fix designed**: Detect split-level by checking if inter-story gap < 0.6 × median_wall_height. If so, skip that ceiling bound.

**Lesson for colleagues**: Any algorithm that assumes uniform story heights will break on split-level Danish houses. Always check Bakkevej 2 (split-level) and the multi-story buildings in the corpus.

### 2026-04-09 — Exterior gap indicators
**Changed**: `reconcile/extract_3d.py`, `reconcile/viewer.html`
**Why**: Large doors/openings on building exterior with a parallel wall close behind indicate scan artifacts.
**Result**: 17 door matches across 223 buildings; 1460 openings in scan-cache, 427 wider than 1m. Martin: "OK, sometimes a chimney on the bottom floor means a gap in the floor. Can you close internal holes that are less than 2m²?"
**Follow-up**: Added internal hole closing for floor polygons (Shapely polygon interior ring removal for rings < 2m²).

---

## Phase 2: Investigation — Understanding Problem Buildings (2026-04-09 to 2026-04-10)

### 2026-04-09–10 — AR session break investigation
**Changed**: Created 11 investigation scripts, expanded `reconcile/extract_3d.py` (+2066 lines)
**Why**: 8 of 223 buildings had visibly broken 3D reconstructions. Martin's hypothesis: "my hypothesis right now is that there was a failure of arkit during the scan that triggered this, which created a new ARsession and maybe even a new ARworld map."
**PostHog investigation**: Attempted to check iOS logs via PostHog MCP. Martin had to reconnect MCP multiple times ("mcp is connected?", "test. i just reconnected it", "test again", "are you sure you can't? are there constraints to the mcp?"). Eventually: "so we couldn't see anything in posthog that was different from other projects."
**Key finding**: Primary signal is **multiple ARKit scan sessions**. 7/8 problem buildings had 3+ `referenceOriginTransform` rotation angle clusters, vs 0/8 reference buildings with ≤2. Problem buildings also showed ~9m median wall displacement (vs ~2m), frequent story reassignments, 2x spatial spread.
**Also investigated**: Whether merged walls add info beyond raw scan-cache. Result: 99.8% of slanted walls (820/822) already have matching data in raw. Apple merge deduplicates but doesn't invent geometry. **No code change needed.**

**Lesson for colleagues**: If a building looks broken, count `referenceOriginTransform` rotation angle clusters first. ≥3 = multi-session scan, likely broken. The data is in the per-room JSON under the transform matrices.

### 2026-04-10 — Full-model unified view: z-fighting discovery
**Changed**: `reconcile/viewer.html`
**Why**: Need to see all layers together as a single building for validation.
**First attempt**: Uniform color with opacity 0.5. **Problem**: transparent coplanar surfaces caused z-fighting (shimmer/flicker). This is a fundamental Three.js issue with transparent overlapping polygons.
**Fix**: Switched to opaque material (opacity 0.7, depthWrite true). Martin: "also, if there are overlaps, remove them between the exterior gaps + floor overlaps + gapwalls + wall extensions, remove them" and "no keep the same edge color as fill."
**Result**: Clean single-color full model view.

**Lesson for colleagues**: Never use transparent materials for coplanar geometry in Three.js. Always use opaque + depthWrite. If you need transparency, use a separate render pass.

---

## Phase 3: Roof Detection & Ceiling Pipeline (2026-04-10 to 2026-04-11)

### 2026-04-11 — Azimuth alignment with web-main
**Changed**: Created `reconcile/grid_convergence.py`, modified `reconcile/extract_3d.py`
**Why**: Martin noticed: "and isn't web-main using building outlines from somewhere else than osm." Investigation revealed two misalignments: (1) no grid convergence correction (UTM grid north vs true north, ~0.5-2° in Denmark), (2) different atan2 sign convention.
**Also**: Martin: "DATAFORDELEREN_API_KEY should be set for ortofoto no? otherwise check in gcp secrets" — led to creating `reconcile/datafordeler.py` for official Danish building footprints.
**Result**: Model footprint aligns with orthophoto. Copenhagen (55.68N, 12.57E) → convergence ~2.0°.

### 2026-04-11 — Ceiling polygon construction: the convex hull problem
**Changed**: `reconcile/roof_algorithms_py/ceiling_plane_generation.py` and clipping sub-modules
**Why**: After the 6 failed ceiling attempts, we moved to building-wide roof plane clustering. But naive construction had problems.

**Problem 1 — false oblique segments**: Knee walls, gable walls, and extension strips were clustered as "roof" planes → wrong ceilings. Martin: "centroid is absolute shit. what the hell are you doing?" (after seeing centroid-based plane matching produce nonsensical results).

**Problem 2 — convex hull boundary**: Convex hull footprint filled L-shape concavities → ceilings extended into outdoor areas. Building `bb013161` (L-shaped with extension) was the worst case.

**Evolution through 3 viewer iterations**:
1. Centroid-based plane matching → Martin rejected it
2. Volume-based approach (breakthrough): build 3D volume from union of floor polygons, cut down by oblique planes. Per-vertex `planeCoversXZ` check prevents false segments from affecting wrong rooms.
3. Added L-junction valley synthesis for perpendicular wings

**Lesson for colleagues**: Centroid-based anything is unreliable for non-convex rooms. Use per-vertex or per-edge tests. And ALWAYS use floor polygon union as footprint, NEVER convex hull.

### 2026-04-11 — The 180° azimuth filter: a critical production lesson
**Changed**: `reconcile/roof_algorithms_py/ceiling_plane_clipping.py`
**Why**: L-shaped buildings need perpendicular (~90°) roof plane pairs to be clipped at their valley intersection. Initial implementation used a 90° azimuth filter to accept these pairs.
**CRITICAL BUG**: The 90° filter caused false clips on unrelated perpendicular planes. Martin explicitly corrected: "but we added the 180° exactly because before we were clipping the wrong things with 90°."
**Fix**: Ridge line intersection test — two perpendicular planes form an L-junction only if their ridges, when extended, intersect **inside the building footprint** (±1m). Unrelated planes have intersections far outside.
**After the fix**: Martin reported "nope now the planes of the aisle got removed completely. i think it's your 'the lowest wins' strategy that did that." Further iteration needed to handle the valley clip correctly.

**CRITICAL LESSON FOR COLLEAGUES**: The azimuth filter uses **180° threshold, NOT 90°**. The 90° range caused false clips in production. This is documented in AGENTS.md as a gotcha. Do not change it back to 90°.

### 2026-04-11 — Roof oblique segments: specific building feedback
**Changed**: Various ceiling/roof modules
**Why**: Martin tested on specific buildings and provided detailed feedback:
- **Åløkkehaven 41, 5000 Odense C**: "clearly not working." The first test building for roof detection. Oblique clustering produced 2 clusters but ceiling construction failed.
- **Brydevej 24, 5700 Svendborg**: "not working. check Brydevej 24 on the top floor. the problem is that it goes all the way to the floor, before the dormer." Roof surface extending through dormer area.
- **Building 117d172e**: "what did you do? ceiling-oblique:0 should have expanded, instead it looks like both this and ceiling-oblique:1 got cut." The gable expansion logic was cutting instead of expanding.
- **Building e0155eef**: "ceiling-oblique:2 makes no sense to be hollowed out: of course it is a roof there is a floor below on the different stories." Height cap was incorrectly removing roof areas above lower stories.

**Martin's key insight on height caps**: "can you remove the height caps? we want to see the ridge intersections" followed by "ah was it for floors above? that sounds like a good idea. keep that." The distinction: clip where upper-story floors exist (correct), but don't clip just because a lower story exists below (wrong).

### 2026-04-11 — The ceiling-oblique vs roof-oblique confusion
**Changed**: `reconcile/roof_algorithms_py/pipeline.py`, `reconcile/roof_algorithms_py/oblique_surface_generation.py`
**Why**: Martin was confused by duplicate surface types: "what, I'm super confused. what is ceiling oblique? what happens if we delete it? what algos is it using? we should merge the two."

Investigation revealed two overlapping oblique surface sets (roof_oblique and ceiling_oblique) rendering identically. Ceiling's clipping logic (footprint narrowing, L-junctions, opposing cuts, height caps) was strictly better. Martin: "that seems important multi-stage clipping with L-junctions, opposing plane cuts."

**Fix**: Unified into single pipeline using ceiling clipping for all oblique surfaces. Removed ceiling_oblique rendering from viewer.

**Lesson for colleagues**: There is only ONE oblique surface pipeline now (ceiling clipping → roof_surfaces.oblique). If you see references to a separate "ceiling oblique" output, it's dead code.

### 2026-04-11 — Simple slant selection: wrong algorithm
**Changed**: `reconcile/roof_algorithms_py/simple_slant.py`
**Why**: Martin tested building 117d172e: "ah it should not be simple. clearly that's a wrong selection algorithm for simple slant. when there are 4 rooms with slanted ceilings, some with multiple orientation, that floor / room is a terrible example of a simple slant."
Also building a6cb04fa: "this is not a good sample slant either. no segments are slanted, it's just a wall higher than the rest (next room is higher)."
**Lesson**: Simple slant should only fire when a room has a SINGLE dominant slope direction with consistent evidence. Multiple orientations or height differences from adjacent rooms should NOT trigger it.

### 2026-04-11 — Dormer detection
**Changed**: Created `reconcile/roof_algorithms_py/dormer_detection.py` (408 lines), `dormer_geometry.py` (439 lines)
**Why**: Scanner captures partial dormer geometry. Martin tested on specific buildings and provided element IDs: "it didn't work detect these: e0155eef::wall-computed::142888CB..., b8cefbc4::wall-merged::A14118E0..., 49762ea7::wall-computed::DD391130..."
**Problem after first implementation**: Martin: "well but i didn't see the cheeks nor the header in full-view?" — dormer geometry was generated but not routed to the full model rendering. Also: "for this d32d5562::wall-merged::FBA4930A... why didn't the dormer header get created. also, i'm not sure it's you but now roofs are the same color as walls etc. please keep them light blue and transparent like we've worked with."
**Lesson**: Always test new geometry in the full-model view, not just individual toggles. And never change existing colors without asking.

### 2026-04-11 — Thermal ceiling layer
**Changed**: Created `reconcile/roof_algorithms_py/thermal_ceiling.py` (961 lines)
**Why**: Downstream energy calculations need "ceiling as seen from above" — the thermal envelope. Martin: "and thermal ceilings should be the default in full-view" and "and the dormer cheeks, headers and cutout due to that need to be included as well."
**Problems**: Martin: "can't see anything else but flat ceilings as thermal ceilings" — oblique thermal ceilings weren't rendering. Also: "well first it needs be flat" — thermal ceiling surface orientation was wrong.
**Later assessment**: This module grew to 950 lines of multi-pass fallbacks. When V3 was designed, this was explicitly cited as an anti-pattern: "thermal_ceiling.py is 950 lines of multi-pass fallbacks. Fallback atoms have no traceable source. Ceiling clipping swallows exceptions silently."

**Lesson for colleagues**: thermal_ceiling.py works but is over-engineered. Don't add more passes to it. The V3 approach (ask before acting, emit unresolved instead of guessing) is the right direction.

### 2026-04-11 — Gap wall ceiling assignment problem
**Changed**: `reconcile/extract3d/gaps.py`, `reconcile/roof_algorithms_py/thermal_ceiling.py`
**Why**: Martin noticed gaps without ceilings: "i'm more concerned these are all gaps that don't have a formally assigned room. you should assign rooms to them so they get a ceiling." Also: "well I don't get why f16973df::thermal-ceiling::thermal:gap:2 is at the floor level, not ceiling."
**Root cause**: Gap detection ran after ceiling inference, so gap regions were invisible to the ceiling pipeline.
**Martin's caution**: "yup. that is very important. verify however there is no circular dependencies or at least think in depth the consequences for the pipeline."
**Fix**: Reordered gap detection before ceiling inference. No circular dependency found.

### 2026-04-11 — Knee wall problem on Bakkevej 2
**Changed**: `reconcile/roof_algorithms_py/thermal_ceiling.py`
**Why**: Martin: "check Bakkevej 2, 8783 Hornsyld. it's still problematic due to a single room" and (with screenshot) "knee walls are cutting through the floor... the top of wall height of this room is the same as the story above but also overlapping the story below."
**Root cause**: Half-level rooms at same story index but different floor elevations broke the single-floor-Y-per-story assumption.
**Fix**: Per-zone floor height lookup instead of per-story. Raised `max_half_floor` from 0.50 to 1.50m.

---

## Phase 4: V2 Topology, Modular Architecture & Infrastructure (2026-04-11 to 2026-04-14)

### 2026-04-11–14 — reconcile_v2 subsystem
**Changed**: Created entire `reconcile_v2/` package (15 modules, ~7,500 lines)
**Why**: V1's scattered heuristics weren't converging. Martin was skeptical initially: "explain to me the usefulness of this topology? i haven't see anything yet that proves me this was smart." After seeing it work on building 5c557e06: "well why don't you look at what's happening in the input and why it can't determine room boundaries?"
**Key design**: Exact-on-lattice polyhedral kernel, property graph with typed nodes/edges, IFC mapping. Martin: "backward compatibility is not required unless it has impact" — freed us from maintaining V1 output format.
**Result**: Full V2 pipeline on all 223 buildings. Commit `8e0ddf4`.

### 2026-04-11–14 — Modular viewer with Three.js modules
**Changed**: Extracted monolithic `viewer.html` into `viewer-modules/` (7 JS modules) + `viewer-main.js` + `viewer_server.py`
**Why**: Martin: "the screen is too wide for all the options, can you tweak the viewer screen" — the toggle bar had grown too long. Also, multiple agents working on different viewer features were causing merge conflicts.
**Viewer issues caught by Martin**:
- "error in the html, the buildings are not rendering" (happened multiple times — JS errors breaking initialization)
- "did you change the styling to our full model and removed the steps etc?" (unintended side effects)
- Multiple screenshots showing rendering bugs
**Result**: MapLibre orthophoto overlay, element locator, roof visualization. Each module independently loadable.

### 2026-04-11–14 — Element locator: right-click debugging
**Changed**: Created `reconcile/element_locator.py` (233 lines)
**Why**: Martin was constantly providing element IDs like `e0155eef-34a5-4642-bca6-39b83ee42af1::ceiling-oblique::ceiling-oblique:2` in his feedback. Needed a system to go from viewer → element → pipeline step → threshold.
**Result**: Right-click any element → copy shareable ID → paste to search bar → highlights element. CLI: `python -m reconcile.element_locator --element-id "<token>"`.

### 2026-04-11–14 — Gap detection: parallel walls and chimneys
**Changed**: `reconcile/extract3d/gaps.py`, `reconcile/extract3d/stitch.py`, `reconcile/extract3d/exterior.py`
**Why**: Martin: "check consequences of increase max_distance_m to 0.8m in find_parallel_edges" and when asked about small internal gaps: "most likely a closet or a fireplace."
**Building bb013161** rooms 4↔5: parallel walls 0.69m apart, no gap wall. Root cause: floor polygons overlap by 1.9m², so `find_adjacent_rooms` excluded them. Martin: "ok and ceilings and floors are also created (or are we associating the gap to a room or something)."
**Fixes**: Allow overlapping rooms in adjacency (change `0 < dist` to `dist`), increase `max_distance_m` 0.4→0.8, add corridor filter (>30% gap filled by another room → skip), lower `min_width` 1.0→0.50, add floor/ceiling caps to stitch walls.
**Impact**: 491 new edge pairs; 362 genuine, zero false positives.

**Lesson for colleagues**: Danish door widths are 0.625-0.926m. The old `min_width=1.0m` threshold missed all of them. Current `min_width=0.50m` catches most.

### 2026-04-11–14 — Martin's directive on testing
**Key conversation**: Martin repeatedly asked "did you check the consequences on other buildings? like the actual consequences" and "hmmm sure. ensure the consequences are well measured so check across all buildings." He always wanted full-corpus validation, not per-building fixes.
**Also**: "did you test the impact across the buildings?" and "try on all buildings please."

**Lesson for colleagues**: ALWAYS run full-corpus validation before committing a threshold change. Martin's rule: measure the cohort size across all buildings before proposing heuristic changes. A fix-of-one is a red flag.

### 2026-04-11–14 — Skills and infrastructure
**Changed**: Created `pyproject.toml`, `Makefile`, CI, 17 test files, 8 agent skills
**Why**: Martin: "search online for three.js based and for 3d pipelines skills.md in general" and "Look in-deep at skills and create what we're going to need in depth please" and "sounds great, for each skill, really research online and find inspiration for existing skills."
**Also**: "Nope. fix them all. I also don't like you expanding to 120 characters. Do it properly once for all." (on linting)
**Result**: Standardized workflow with `make verify`. Skills guide agents on geometry, extraction, roof pipeline, viewer, topology, testing, Danish geodata, run-and-verify.

---

## Phase 5: Rich Spatial Ontology — From Skepticism to 31 Steps (2026-04-12 to 2026-04-14)

### 2026-04-12 — Cell decomposition prototype
**Changed**: `reconcile_v2/cell_decomposition.py`, `reconcile_v2/ontology.py`
**Why**: The fundamental V1 problem: algorithms independently re-derive context with hardcoded thresholds. A unified cell complex would be the single source of truth.
**Martin's skepticism**: "explain to me the usefulness of this topology? i haven't see anything yet that proves me this was smart." He tested on building 5c557e06 and challenged: "well why don't you look at what's happening in the input and why it can't determine room boundaries?"
**Also**: "please check the complexity of reimplementing the specific algorithms (CellComplex from faces + adjacency queries) in Shapely online" and "search online for shapely equivalent" — Martin wanted to verify we weren't reinventing the wheel.

**Assessment concerns**: (1) 15.3K lines of new code without consolidation, (2) duplicate code (`polyhedral_kernel.py` and `roof_arrangement_kernel.py` byte-for-byte identical), (3) old heuristics still running in parallel, (4) runtime 24s→47s (2x slower), (5) 23,353 knee walls across 223 buildings (~105 per building — absurdly many).
**Immediate fixes**: Deduplicated kernel, fixed stale docs, created shared utilities, added knee-wall area filter, real-building integration test.

### 2026-04-12–14 — Full-model from ontology: 31 steps (the longest single Codex session: 179 messages, 56MB)
**Changed**: 11 modules across `reconcile/roof_algorithms_py/` and `reconcile/viewer-modules/`
**Why**: Convert ontology from partial layer into full geometry backend. Martin: "i'm not sure removing oblique faces is the target, I'd say it's more the opposite. Flat is easy, but detecting if a roof is oblique and assigning oblique faces, especially in adjacent rooms that logically also have a slanted roof."
**Martin's design inputs**:
- "first we should identify which rooms are covered by slanted roof and THEN figure out if there is an attic (flat ceiling) and knee walls (vertical walls intersecting against slanted roof) and dormers"
- "the decision is also not at the room level, it's also at the individual segment level, as some rooms have slanted roof segments on both sides (could in theory be 4 sides!) but can also have a flat ceiling (for example if there is an unheated attic above)"
- "a gable roof can potentially cover a building part, not the entire building. and sometimes there can be multiple building parts with different gable roofs"
- "remember to take a step back to think about the overall objective" (said multiple times)
- "we want an exact volumetric arrangement kernel that is portable across languages" — the portability requirement shaped the exact-on-lattice design
- "backward compatibility is not required unless it has impact" — freed us from maintaining V1 format
**The frustration cycle (Apr 14, Codex session)**:
After implementing, Martin tested visually and was increasingly frustrated:
- "I have to say I looked at the results and it doesn't look too good. Far from entire building is covered, my cpu is struggling."
- "i don't know if it's visualisation issues or what, but this should be slanted and is not. the second one is completely off course"
- "I have to say, I don't really get what I can use it for. It doesn't seem that useful to me? The reconstruction looks nothing like the real building"
- "but I'm not seeing the slanted roof segment? not all rooms are covered? what's the purpose?"
- "i need to see the final model. basta."
The "sticking out" saga: Martin reported the same element extending beyond building boundaries 12+ times in rapid succession for buildings 117d172e, a6cb04fa, ed5231c3, c87c1e25, bb013161. Root causes varied: missing footprint clipping, wrong flat-atom heights, roomless fallback surfaces.
**Strategic pause**: Martin: "I think you should take a step back. I'm unsure whether you're operating strategically or just fixing things here and there" and "What? It seems you're trying to overfit right now when something is fundamentally not making sense" and "but isn't everything hypothesis geometry? I'm very confused."
This led to the Phase A/B systematic approach instead of per-building fixes. Martin: "Please take a step back and write an .md that describes what we've done so a colleague with no context can give his opinions on next steps."
**Performance optimization**: `build_topology_graph` went from 2.172s→0.235s (replaced repeated NumPy allocation in T-junction checks, restricted edge comparisons to same cluster).
**Coverage journey**: 115 ok → 215 ok (after footprint fix) → 223 ok. Test growth: 9→158 tests.

**Lesson for colleagues**: The ontology/cell-complex approach is architecturally sound but the gap between "topology graph works" and "full model looks correct" is enormous. The graph correctly models spatial relationships but translating that into renderable geometry that matches a real building requires dozens of semantic decisions at the atom level. Each decision can go wrong in subtle ways visible only through visual inspection.

---

## Phase 6: Full-Model Parity Push — The Most Intense Day (2026-04-14)

This was the most intense day of the project — roughly 15 separate changes driven by corpus-wide audits revealing specific failure classes.

### 2026-04-14 — The parity audit shock
**Changed**: `scripts/audit_full_model_payloads.py`, `scripts/audit_ceiling_parity_deficits.py`
**Why**: We thought we had good coverage. The audit revealed we didn't:
- `base_window`, `base_door`, `base_opening` = **0/223** (fenestration entirely absent)
- `unresolved_region` = **0/223** (no honest uncertainty reporting)
- Roof only on 121/223 buildings
- Semantic ceiling overlap: only **37%** vs heuristic (shell was 96%)

**The insight that changed the approach**: The problem wasn't shell absence (96%) — it was semantic *promotion*. The system had the geometry but wasn't classifying it correctly. We were missing 21,356 ordinary flat ceilings that should have become semantic output.

### 2026-04-14 — Phase A: top-boundary atoms for ALL rooms (biggest single impact)
**Changed**: `reconcile/roof_algorithms_py/top_boundary_graph.py`, `reconcile/roof_algorithms_py/pipeline.py`
**Why**: `ceiling_partitions` only generated atoms for "exposed rooms" (rooms with no floor above). Non-exposed rooms got nothing — they fell through to synthetic fallback.
**Evidence**: Building `9c42b8bc`: 14 rooms, 5 exposed, 5 partitioned, 81 synthetic atoms. Building `60f2f02b`: 13 rooms, 7 exposed, 54 synthetic. Most rooms were completely unpartitioned.
**Fix**: Generate implicit flat shell-cap atoms for ALL non-exposed rooms.

### 2026-04-14 — Phase B: remove roomless flat fallback
**Changed**: `reconcile/roof_algorithms_py/roof_flat_intermediate.py`, `reconcile/roof_algorithms_py/roof_coverage_graph.py`
**Why**: 450 roomless flat surfaces across 211 buildings — floating patches with no room attribution.
**Fix**: Reject to unresolved instead of rendering as fallback.

**Combined Phase A+B impact**:
| Metric | Before | After |
|--------|--------|-------|
| buildings_with_roof_surface_fallback | 211 | 1 |
| total_roof_surface_fallback | 450 | 2 |
| buildings_with_unresolved_region | 219 | 155 |
| total_unresolved_region | 5,139 | 2,765 |

### 2026-04-14 — Upstream top-boundary validation
**Changed**: `reconcile/roof_algorithms_py/top_boundary_graph.py`
**Why**: Invalid flat atoms with heights below room minimum were creating bogus attic/upper-void cells downstream.
**Fix**: Shell-validity gate. Building `5c557e06`: rejected 25 flat candidates, eliminated all synthetic atoms.

### 2026-04-14 — Shell contract: no continued surfaces in committed geometry
**Changed**: `reconcile/roof_algorithms_py/roof_partitioning.py`
**Why**: Continuation surfaces (extrapolated geometry filling gaps) were being promoted to committed shell → spikes and over-extensions in the full model. False positives that looked worse than honest gaps.
**Contract**: Continuation stays diagnostic-only. Only explicit arrangement faces can be committed.

### 2026-04-14 — Knee wall filtering: 30,145 → 81
**Changed**: `reconcile/roof_algorithms_py/thermal_ceiling.py`, `reconcile/roof_algorithms_py/roof_coverage_graph.py`
**Why**: 30,145 raw knee walls (~135/building). Most had no physical basis.
**Fix**: Require bottom edge alignment with occupied-room exterior wall. **99.7% reduction**.

### 2026-04-14 — Synthetic ceiling demotion: honest reporting
**Changed**: `reconcile/roof_algorithms_py/roof_coverage_graph.py`
**Why**: Synthetic ceilings rendered as `fallback_room_ceiling` made it look like the pipeline was confident about geometry it manufactured.
**Fix**: Demoted to `unresolved_region`. Building `5c557e06`: `fallback_room_ceiling` 37→0, `unresolved_region` 0→37.

### 2026-04-14 — Targeted semantic fixes per building
**Changed**: `reconcile/roof_algorithms_py/top_boundary_graph.py`
- **Building 1f03f6e0**: Room 0 atoms all `attic_floor_candidate` despite no local sloped support — overfitting to global building-part family. Fix: prefer `flat_ceiling` when no local sloped support. Semantic overlap 0.944→0.990, unresolved area 157.8→3.9 m².
- **Building a317a543**: Flat atoms without exact upper cells marked as candidates despite strong upper-void context. Fix: infer `flat_transition_cap_inferred`. Semantic overlap 0.905→0.981.
- **Building c87c1e25**: Empty floor polygon causing fallback. Fix: fallback to `floor_polygon_original`. Fallback 1→0, unresolved 3→0.

### 2026-04-14 — Final parity numbers (commit db4aa7c)
- Shell ceiling overlap: **99.88%** vs heuristic
- Semantic ceiling overlap: **99.56%** (up from 37%)
- Roof coverage: **99.18%**
- Runtime: **1.024s**/building
- 162 tests passing

---

## Phase 7: Parity Finalization & Deep Research Pivot (2026-04-15 to 2026-04-16)

### 2026-04-15 — Oblique positive-clearance kernel fix
**Changed**: `reconcile_v2/polyhedral_kernel.py`, `reconcile/roof_algorithms_py/roof_partitioning.py`
**Why**: Buildings 71ee522c and e028... had shell ceiling overlap well below parity. Oblique planes dipping below base_y created degenerate cells (face_count 1-2, no top).
**Fix**: (1) XZ clipping of oblique footprints against `top_y >= base_y + 1mm`, (2) fallback to prism-face construction from clipped footprint.
**Result**: Building 71ee522c room 6: occupied area 10.965→32.639 m². Shell overlap: 0.829→0.997.

### 2026-04-15 — Residual classification: shell is done, semantics remain
**Finding**: Shell construction at parity (99.88%). Remaining gap is semantic attribution. Two groups: (1) shell undercoverage (2 buildings), (2) mixed-room semantic mismatch (5 buildings, candidate atoms in rooms with strong roof evidence remain unresolved).

### 2026-04-16 — Stale sidecar discovery
**Changed**: `reconcile/viewer_server.py`, `scripts/build_roof_algorithms_py_results.py`
**Why**: `roof_algorithms_py_results.json` was from April 12 but `buildings_3d.json` from April 16. Stale data caused confusing viewer artifacts.
**Fix**: Freshness gate + regeneration script (223 entries in 272.5s). Also fixed `GeometryCollection` serialization bug.

### 2026-04-16 — Deep research: "Please really take a step back"
**Why**: Martin: "Please really take a step back and use /deep-research ultra deep to think if what we're doing makes sense."
**Key findings from the research**:
1. **RoomPlan does not capture ceiling geometry.** The entire roof reconstruction is *inference* from walls. There's a hard ceiling set by input fidelity.
2. **The customer may not need a 3D mesh.** Danish EPC requires heated floor area, envelope surface area, U-values, roof type + inclination. A flat energy schema (LOD200) might suffice.
3. **The threshold-tuning loop is Sisyphean.** Per-atom arbitration + another layer + another threshold = grinding toward a ceiling set by data quality, not algorithm design.
**Recommendations**: Keep graph topology. Reframe output to match customer contract. Consider BBR roof type as prior. Stop per-building threshold tuning.
**Decision**: Proceed with solver-based V3. Also check with Lun Energy if current Full model is "enough."

**Lesson for colleagues**: RoomPlan fundamentally cannot give us ceiling geometry. We are always inferring from walls. Don't chase perfect ceiling reconstruction — it's impossible with this input data. Focus on getting the roof type and envelope dimensions right for the energy model.

---

## Phase 8: Debugging & V3 Design (2026-04-16 to 2026-04-17)

### 2026-04-16 — The headline defect: attic-over-slope bias
**Finding**: Building `5c557e06` rooms 0 and 3: visually under slanted roof with strong perimeter evidence, but rendered as flat attic. Root cause: room-level flat atoms win early before evidence is assembled regionally.
**This defect motivated the entire V3 approach**: per-segment/per-atom reasoning can't solve building-level roof geometry.

### 2026-04-17 — Element locator expansion for ontology kinds
**Changed**: `reconcile/element_locator.py` (+587 lines)
**Why**: Martin started using `/debug-element` skill heavily on specific buildings. Original locator only handled 14 legacy kinds. Needed ontology-renderable-* support.
**Martin's approach**: Send 3-5 element IDs per session, challenge the root cause analysis: "first, fix the element locator has a gap — it doesn't handle roof-atom-patch:* source prefixes" and "the Cell/face composite should be easy to trace and probe. improve this."

### 2026-04-17 — Debug: gap closure on Degnemarken 5 (24% of buildings affected)
**Changed**: Diagnostic analysis
**Problem**: Spurious gap-closure `gc:1`. Side closures are degenerate ribbons.
**Root cause**: `interp_wall_y` assumes `corners[0..1]` is bottom edge. Parent wall has 6 corners with top corners first → returns top Y instead of floor Y.
**Cohort**: **38/223 buildings (24%)** — not one-off. Martin's emphasis: "it's also super important the skill looks for a general problem first, ie try to find similar cases across different buildings to avoid overfitting."

### 2026-04-17 — Debug: flat cap over sloped roof (30% of buildings)
**Problem**: Building 72122129 room 0/story 2: flat ceiling cap extends past roof above correct slanted ceiling. 13.5cm clearance (not a real void).
**Root cause**: `top_boundary_graph.py` promotes "1 upper_void cell" to full `flat_transition_cap` without checking if the "void" is physically meaningful.
**Cohort**: **418 atoms across 68/223 buildings (30%)**.
**Martin**: "in this case it's the flat part that is wrong. the slant below is correct" and "well maybe it has a flat ceiling below a slanted roof? but the flat ceiling shouldn't extend beyond the roof then?"

### 2026-04-17 — Debug: wall overlap from legacy extraction (14% of buildings)
**Problem**: Building `bb013161`: two walls from different rooms overlap despite non-overlapping floors.
**Root cause**: `clip_floor_overlaps()` midpoint heuristic. For long walls, midpoint can be outside overlap while wall segment crosses it.
**Cohort**: **31/223 buildings** with same-story overlap > 0.5 m².

### 2026-04-17 — Martin's meta-feedback on debugging approach
**Key quotes**:
- "it's also super important the skill looks for a general problem first" — always check cohort size
- "In the skill.md, you should confirm your hypothesis by looking at multiple cases to figure out if the root cause is problematic always or only in this case, so the fixes would create a 'whack-a-mole' consequence"
- "and I'm wondering if you should create more scripts to super quickly understand what may be wrong"
- "but did you practically look at more cases? 428 atoms seems like a lot"
- "but how much what's the blast ratio of the fix? think holistically"

**Lesson for colleagues**: Before implementing ANY fix: (1) measure the cohort size, (2) check if the fix creates new problems on other buildings, (3) if it only helps 1 building and hurts 5, it's a bad fix.

---

## Phase 9: V3 Clean-Slate Architecture (2026-04-17 to 2026-04-18)

### 2026-04-17 — V3 design: why start over
**Changed**: Created `reconcile_v3/` directory structure
**Why**: V1's fundamental problems:
- `thermal_ceiling.py` is 950 lines of multi-pass fallbacks
- Fallback atoms have no traceable source
- Ceiling clipping swallows exceptions silently
- Thresholds scattered across ≥7 files (0.08, 0.12, 0.15, 0.3, 0.5, 0.75 m)
- Each fix adds a parameter + silent-failure path
**V3 philosophy**: (1) Linear stages, no cascading fallbacks, (2) emit `unresolved` instead of fake geometry, (3) tolerances in `constants.py` only, (4) silent except → lint-fail test, (5) every element carries `HypothesisTrace(stage, rule, inputs, decision_reason)`, (6) fail loudly.
**Martin's insight that shaped Stage 4**: V3 asks "is this a knee wall?" BEFORE extending walls (Stage 4). V1 extends first, clips after — much harder to reason about.
**Milestone 1**: 223 buildings emit results with 2,368 slabs, 1,631 flat ceilings, 737 unresolved. Martin: "viewer integration is not out of scope, how would i otherwise verify?" — viewer toggle added immediately.

### 2026-04-17 — V3 evidence fusion: Martin's insight on slope indicators
**Changed**: V3 Stage 6 design
**Martin's idea**: "I had a small idea that beyond oblique segments, maybe knee walls (wall less tall than the max height wall in room) or absence of wall towards the outside (from the ridge) could be an indication of a slanted roof as well. could be useful for rooms where the wall segments don't have oblique edges."
**This became the 3-source evidence fusion**: (1) oblique segments (direct), (2) wall-height asymmetry (tall wall ≥ 0.8m taller than short), (3) missing exterior wall (room edge touches boundary without wall → slope runs to floor).

### 2026-04-17–18 — Greedy roof proposer with human-in-the-loop labeling (the labeling marathon)
**Changed**: V3 proposer + viewer labeling UI (session e89eb1ac: 270 messages — longest single Claude session)
**Why**: Need data before committing to rules. Emit every (cluster × slab) pair permissively. Martin: "I have a crazy idea. make me an interface for the buildings where we're in doubt so I can easily identify the slanted roof faces."

**The labeling UI went through ~8 major iterations in a single session**:
1. First version showed all proposals on one building → Martin: "please do an endpoint where I can go through them instead of one by one"
2. Navigation added → Martin: "i don't get it, it should be individual segments I approve... and those should be very very permissive slanted"
3. Click-to-select added → Martin: "it's maybe easier for me to click on the proposed segments and then assign them with a letter?"
4. Split functionality requested → Martin: "be aware that i should be able to cut polygons" and "two click split. I could have to cut in multiple directions"
5. Definition clarified → Martin: "the segments should be split by the portions of the rooms that are exposed to 'vertical rain', not all of rooms"
6. Merge tolerance issues → Martin: "it also looks like the merged planes are not going well. you didn't merge them with tolerance as we did in the viewer.js earlier"
7. Per-piece labeling → Martin: "label halves independently, each piece needs its own persisted id" and "delete existing labelled db so I can start from scratch" (said 4 times as format changed)
8. Final spec (after extensive back-and-forth): "You keep misunderstanding: I need the individual segments on the merged planes to be what I approve or not. These segments of planes are created by splitting the planes based on intersections with other merged planes and in the x,z coordinates by the rooms and gap parts that are 'exposed to vertical rain'. The planes are clipped by the building boundaries as defined by the perimeter of the union of floor slabs."

**Specific bugs during labeling**: "i got a 400 when trying to cut", "it seems you're clipping segments instead of splitting them", "the segments are diverging from the planes after they are split" (inclination changed after XZ splitting), "it seems you're only showing the merged model on the labeler. I would like you to show the model that we have after step 2 in viewer.html", "manual split doesn't seem to work."

**Martin's building-specific feedback during labeling**:
- "720c2f50: there is a little building extension but the segments are not extending above it"
- "7dbc53a6: is not being extended to building boundaries"
- "016980bc: segment-5:room-0:piece-0 the filtering to 10cm is not working"

**Result**: 5,760 labels across 70 buildings. 25% accepts, 74% rejects, 0.3% skips. Later scaled to 8,865 labels across 111 buildings.

### 2026-04-18 — Reverse-engineering detection from human labels
**Changed**: Analysis scripts, feature expansion
**Why**: Use Martin's labels to understand what "correct" looks like, work backward to find predictive signals.
**Martin's key domain insight about staircases**: "I'm pretty sure many of the planes that are not roof stem from segments that come from internal staircases especially in very large buildings or with many stories" and "staircases were often detectable as they would often be internal, ie crossing internally through the building heavily, where the roof segments usually are outside (parallel to the building)."
**Martin's exhaustive feature request**: "Alright now I've labelled a few thousand segments. prepare a plan to analyse and reverse engineer how we should detect slanted roofs in the future. It is absolutely crucial you think about ALL parameters that could be relevant. edge, vertices, faces, 3d position, neighbours, physics principles, architectural principles, relative positions, segments, kneewalls, absolutely a complete, complete exhaustive approach."
**Feature expansion**: Started with 9 features on merged segments, expanded to 150+, then Martin pushed further: "I'm surprised. didn't the document list 600 features?" and "I think we should try the remaining gaps: Band-4 literature exotics (~163) and finer Band-2 source-wall aggregates (~50) anyways, what do we have to lose?" Final count: 444 features computed.
**Gaps identified**: (1) feature sparsity still limiting, (2) `reasons[]` empty (have accept/reject but no "why rejected" taxonomy).
**Martin's growing doubt**: "but there's more and more to review. I'm just unsure we're getting closer." and "why do we only have 2 rules? I'm surprised tbh."
**7-phase pipeline designed**: join labels → expand features → descriptive stats → GroupKFold model (tree + LightGBM + SHAP) → rule extraction → disagreement audits → deliverables.

---

## Phase 10: The Critical Pivot — From Classification to Reconstruction (2026-04-19 to 2026-04-20)

### 2026-04-19 — Deep research: "is it a hard problem?"
**Martin's session** (session eb3f8a1d, 140 messages): "create a very deep implementation plan for the above, search online" → "i'm just surprised. is it a hard problem we're trying to solve?" → **"but it is easy for 97% of properties. i just don't know if looking at each segment is correct."** → **"for me we have all the planes. we just need to figure out which planes to pick and how to cut them."**

This last quote was the pivot moment. The problem isn't classifying segments — it's selecting and clipping planes to form a valid roof envelope.

**Also critical**: "We will not use BBR as it is too crude. Our problem is determining the extent of the gable roof where BBR is general." This rejected the deep research recommendation to use BBR roof types as a strong prior. Martin knows the data limitations better than the research.

**Lesson for colleagues**: Do not use public Danish building data (BBR, Datafordeler, GeoDanmark) as ground truth for geometry. It may be wrong or too coarse. Use only scan-derived geometry for reconstruction constraints.

### 2026-04-19 — Phase A: candidate face generation (done)
**Changed**: `reconcile_v3/` candidate generation
**Why**: The BIP solver needs a menu of possible roof faces. Generate by pairwise-intersecting plane hypotheses → define ridge/hip/valley lines → clip each plane to footprint + neighbors.
**Result**: **13,105 candidate faces** across 223 buildings (9,543 ridge-extended). Viewer integration complete.

### 2026-04-19 — Phase B: BIP solver design
**Solver**: Python-mip with CBC backend (no Gurobi needed).
- Variables: `x_i ∈ {0,1}` per candidate face
- Objective: maximize coverage quality − complexity penalty
- Constraints: footprint coverage ≥ θ, non-overlap, azimuth coherence (≤ K bins), topology connectivity
**Hyperparameter search**: 100 random trials on 20-building pilot. Score = `mean_iou + 0.3 × frac(iou ≥ 0.9) − 0.5 × review_rate`.
**Triage policy**: auto_accept if solved + low gap + clear winner. Review if ambiguous or tight runner-up. Target: ≤10% review rate (≤5% ideal).

### 2026-04-19 — Label loop scaling
**Martin's session** (session e89eb1ac, 270 messages — the longest single session): Started with 70 buildings labeled, went through building after building providing accept/reject on proposed segments. "what should I open to test them all" → labeling infrastructure built → scaled to 111 buildings, 8,865 labels.

### 2026-04-19–20 — Viewer enhancements for V3
**Changed**: `reconcile/viewer-main.js` (+1742 lines), `reconcile/viewer_server.py` (+1351 lines), viewer modules
**Why**: V3 needs candidate visualization, solver output overlay, reconstruction envelope layer, state URL with camera presets.

### 2026-04-19–20 — Extract pipeline refinements
**Changed**: `reconcile/extract3d/exterior.py`, `reconcile/extract3d/overlaps.py`, `reconcile/extract3d/stitch.py`, `reconcile/extract_3d.py`
**Why**: V3 surfaced edge cases in exterior surface generation, overlap detection, and stitching.

### 2026-04-19–20 — Test expansion
**Changed**: 6 test files (+763 lines total)
**Why**: New V3 code paths and expanded element locator need coverage.

### 2026-04-20 — BIP solver first results and confusion
**Martin's session** (eb3f8a1d continued): After candidate faces were generated, the solver was run. Martin: "hmmm i think they're too many now. maybe we need the BIP solver now?" Then after seeing results: "wait but I looked at it. it seems like it's accepting all faces now?!" and "no the problem here is that there is one small part of this that is correct but it's using the entire plane" and "i'm confused. now we're going back and forth. some of the other examples are also completely off" and "well I don't know. are we even getting closer?" and finally: "i don't know tbh i'm a bit lost about next steps."

**The ridge/eave idea (Martin's breakthrough)**: "I had an idea: given that the correct planes are among the planes that are identified, what if we used the ridges and eaves to determine if the planes are correct? ie a ridge that is approximately half-way and perpendicular to the building part, etc?"
**First implementation**: Compute against building-part medial axes. Martin: "i think it is pretty good BUT it is bad at splitting building parts and not great when there is a dormer (i guess it skews the avg etc)." Then: "for dormers it is the opposite — when there is a dormer the computed ridge is skewed so good planes get bad scores." Then: "nah it's gotten worse. I feel you're bad at detecting building parts (ie which parts should the planes be allocated to) and you're bad at detecting dormers (which should be discounted)."
**Pivot to shapes**: Martin: "now you're using heuristics with hardcoded numbers. I don't want that. use shapes or something." This led to `shapely.ops.split(scan_polygon, ridge_line)` as the scoring foundation.
**Final direction**: "alternatively, why don't you look at all pairs that are 90° or 180° and have mirroring vectors (inclination, orientation, height)?" — this became the mirror-parity scorer.

### 2026-04-20 — Ridge/eave scorer: shape-based split (no more OBB heuristics)
**Changed**: `scripts/score_candidates_ridge_eave.py` (OBB metrics → shape-based `shapely.ops.split`), `reconcile/viewer-modules/v3-model.js` (multi-line eaves, side-polygon outlines, dropped OBB/medial-axis overlays), `reconcile/viewer-main.js` (cache-bust v=20260420c).
**Why**: Previous scorer used OBB corner distances with hardcoded widths/sigmas (EAVE_FOOTPRINT_SIGMA, OBB half-width). Per Martin's directive ("now you're using heuristics with hardcoded numbers… use shapes or something"), retained only `HORIZONTALITY_SIGMA_DEG=3°` as a physical construction-precision constant; all other score components derive from `shapely.ops.split(scan_polygon, ridge_line)`.
**Result**: 5 components (`horizontality`, `halves_balance`, `sides_aligned`, `eave_balance`, `ridge_span`) combined via geometric mean. Full-corpus run 223 buildings / 331 pairs: 57% GREEN (≥0.6) / 30% ORANGE / 13% RED. Target set: 117d172e, 16784bad, e0155eef all show GREEN pairs; c87c1e25 has 1 GREEN + 1 ORANGE (0.541; asymmetric cross-wing → genuinely low halves_balance).

### 2026-04-20 — Ridge/eave scorer: mirror-parity rewrite with physical wall-top eaves
**Changed**: `scripts/score_candidates_ridge_eave.py`. Rewrote `_score_plane_pair` to score plane *mirror parity* instead of shape-based split: 4 components (`horizontality`, `azimuth_opposition`, `inclination_match`, `eave_height_parity`) combined by geometric mean. Per-piece `_assign_sides` handles pair domains split into 3+ pieces (tangent ridges on extension lobes). Eave Y is derived from top-story `walls_merged[].corners` in `reconcile/buildings_3d.json`: for each plane, cluster wall-top y's where `|plane_y(xz) − wall_top_y| ≤ 0.3m`; per pair, pick the cluster pair with smallest |Δ| so the two sides' shared-eave interpretation is chosen automatically. Falls back to union min-Y when a plane has no wall-top matches. New CLI flag `--buildings reconcile/buildings_3d.json`.
**Why**: Previous 5-component shape-based scorer fired GREEN off ridge-extrapolated geometry — mirror-like planes passed even when their downslope/inclination/eave Y didn't physically match (false positives), and the eave_balance metric couldn't distinguish a real extension pair from a straight extrapolation. Martin directed the pivot: "why don't you look at all pairs that are 90° or 180° and have mirroring vectors (inclination, orientation, height)?" and then "try to get a realistic idea of where the eaves are based on the room and the rooms in the storeys below". Wall-top y's are physical ground truth — if a plane doesn't come to rest on any top-story wall, it can't claim an eave.
**Result**: All 4 target buildings score GREEN. 117d172e: 0.995, 16784bad: 0.997, c87c1e25 (extension cross-gable): 0.984, e0155eef: 0.995. Full-corpus 223 buildings / 393 pairs: 45.3% GREEN / 0.4% ORANGE / 54.3% RED — 78% of pairs use wall-top-sourced eaves, rest fall back to union min-Y. ORANGE collapse is expected: mirror parity is binary (planes either mirror or they don't), so borderline scores are rare. RED includes buildings with hip roofs, single-plane sheds, and buildings where the scan doesn't cover a plane's eave side.

### 2026-04-20 — Ridge/eave scorer: ridge-corner exclusion via partner plane
**Changed**: `scripts/score_candidates_ridge_eave.py`. Reverted `_extract_top_story_wall_tops` to return ALL top-story `walls_merged` corners (no per-shape filtering). Added `partner_plane` param to `_plane_eave_y_clusters`: a candidate wall corner is dropped as a "ridge corner" when the partner plane's predicted y also agrees with the corner's y within `WALL_TOP_MATCH_TOL_M`. Since base-of-wall corners are naturally rejected by the per-plane match tolerance (planes don't extrapolate that far down), and ridge/apex corners are the only corners both mirror planes pass through at the corner's elevation, the remaining matches are eave corners by definition — no shape heuristics.
**Why**: Prior "highest y-cluster with ≥2 corners" rule was a shape heuristic that broke on pentagon walls with shapes (2,1,1,1) (asymmetric gable — 1 cluster with ≥2 corners) and (2,1,2) (flat-top pentagons where the ridge IS the top edge). Regressed e0155eef from 0.995 → 0.155 and missed e028bcc5's L-shape pair 2. Ridge-corner exclusion is the true physical definition: an eave is where exactly one plane rests; the ridge is where both do.
**Result**: e0155eef restored to 0.995 (main pair). e028bcc5 pair 2 improved from 0.050 → 0.278 — remaining RED is genuine scan evidence (Δinc=5.3° between 141.1°/41.3° and 322.0°/46.6° planes; 1m eave-height delta). Corpus-wide 108 buildings with pairs: 93.5% GREEN / 0.9% AMBER / 5.6% RED, median best-score 0.992. Versus prior snapshot: 0 GREEN↔RED threshold flips, max drop -0.076 (all stayed GREEN), one big gain (fe829d59: 0.736 → 0.998).

---

## Key Lessons for Colleagues (Summary)

### Things that DON'T work
1. **Per-room ceiling inference** — tried 6 times, failed 6 times. Need building-wide pipeline.
2. **Centroid-based anything** — unreliable for non-convex rooms. Use per-vertex/per-edge tests.
3. **Convex hull as footprint** — fills L-shape concavities. Use floor polygon union.
4. **90° azimuth filter** — causes false clips. Use 180° (documented as CRITICAL in AGENTS.md).
5. **Transparent materials for coplanar geometry** — z-fighting in Three.js. Use opaque + depthWrite.
6. **Per-segment classification for roof detection** — F1 plateaus at 0.84, 22% review rate. Building-level optimization is the right frame.
7. **Midpoint-in-overlap wall selection** — too aggressive, removes external walls.
8. **Uniform story height assumption** — breaks on split-levels (Bakkevej 2).
9. **thermal_ceiling.py's multi-pass fallback pattern** — 950 lines, untraceable, swallows exceptions.
10. **BBR/Datafordeler as geometry ground truth** — too coarse, sometimes wrong.

### Things that DO work
1. **Full-corpus validation before committing threshold changes** — Martin's #1 rule.
2. **Cohort analysis before fixing** — measure blast radius across all buildings.
3. **Emit "unresolved" instead of guessing** — honest > wrong.
4. **Volume-based ceiling construction** — per-vertex plane check within footprint union.
5. **Element locator for debugging** — right-click → element ID → pipeline trace.
6. **Phase A/B approach** — extend atoms to all rooms + remove roomless fallback = biggest single improvement.
7. **Building-level constraint optimization (BIP)** — the right frame for roof selection.
8. **Shape-based scoring** — derive from geometry (shapely.ops.split), not hardcoded heuristics.

### Key test buildings
| Building | Address | Why it matters |
|----------|---------|---------------|
| 5c557e06 | — | Attic-over-slope bias; slanted rooms rendered as flat |
| bb013161 | — | L-shaped with extension; ceiling cuts through entire building |
| 71ee522c | — | Oblique positive-clearance kernel bug |
| 117d172e | — | Gable expansion bug; ridge/eave scoring target |
| d32d5562 | — | Extension-grade gable detection prototype |
| 72122129 | Degnemarken 5, Ringe | Gap closure malformation + flat cap over slope |
| 38f71f1d | Birkemosevej 62 | Edge-touching room boundary bug |
| Bakkevej 2 | 8783 Hornsyld | Split-level house; breaks story height assumptions |
| Åløkkehaven 41 | 5000 Odense C | First roof detection test building |
| Brydevej 24 | 5700 Svendborg | Dormer detection test; roof through dormer area |
| Enebærvej 6 | 5550 Langeskov | Wide gaps (>0.40m) not detected |
| Bøgebakken 3 | 5260 Odense S | Wall overlap clipping too aggressive |
| e0155eef | — | Hollow ceiling-oblique bug; dormer detection target |
| 1f03f6e0 | — | Attic candidate overfitting to building-part family |
| c87c1e25 | — | Asymmetric cross-wing; ridge/eave low halves_balance |

---

## 2026-04-20 — `reconcile_ext` extension-detection pipeline + standalone viewer

**What changed**
- New top-level package `reconcile_ext/` — diagnostic pipeline for extension seam detection. Reads the V3 result snapshot + `buildings_3d.json`, emits `reconcile/reconcile_ext_results.json` with one entry per building.
- Four Phase-1 diagnostic stages (no geometry feedback into V3):
  - `stages/reflex_vertices.py` — ACD-style notch vertices on the simplified merged footprint.
  - `stages/roof_discontinuities.py` — pairwise ridge/eave Δh + azimuth/inclination mismatch between adjacent oblique clusters.
  - `stages/wall_plane_steps.py` — parallel-wall offset across different rooms.
  - `stages/ceiling_floor_deltas.py` — room-adjacency floor-Y and ceiling-Y steps.
- `pipeline.py` synthesises seam hypotheses by clustering Tier-1 (reflex) + Tier-2 (corroborating) signals within 4m.
- CLI: `python -m reconcile_ext --uuid <uuid>` or `--all`.
- Standalone viewer at `reconcile/viewer-ext.html` + `viewer-ext-main.js` — 223-building sidebar sorted by signal strength, per-overlay toggles, Three.js rendering independent of the main `viewer.html`.

**Why**
- Research (`/plans/system-instruction-you-are-working-mighty-wilkes.md`) argues extensions need first-class part seams + primitive library. Diagnostic-only signals let iteration on thresholds happen without regressing the 200+ V3 reconstructions. Standalone viewer keeps iteration independent of the main proposal-labeler viewer.

**Result**
- Full-corpus: 466 reflex vertices, 438 strong seams + 28 medium across 223 buildings; 162 buildings have ≥1 strong seam, 56 have no signal.
- Named corpus targets: `bb013161` (L-shape worst case) → reflex=3 strong=2 medium=1; `c87c1e25` (asymmetric cross-wing) → reflex=1 strong=1; `d32d5562` (extension prototype) → reflex=0 (nearly rectangular footprint — signal must come from roof-disc/wall-steps; neither fired, still a gap).
- **Sign-convention fix during corpus run**: interior-angle formula used `(a-b)×(c-b)` instead of `(b-a)×(c-b)`, inverting convex vs reflex. Corrected; reflex count jumped from 0 → 3 on bb013161.
- **Known over-triggering**: wall_plane_steps fires 14153 times corpus-wide — walls within the same room layout often look parallel-with-offset. Needs exterior-only filtering before it's useful as a Tier-2 signal; currently toggles default ON but the signal drowns out everything in complex buildings.
- Viewer verified in-browser on bb013161 — reflex sticks, roof-disc column, wall-step dots, and seam markers all render; sidebar auto-sorts signal-rich buildings first.

## 2026-04-20 — `reconcile_ext`: heal V3-closed gaps before reflex detection

**What changed**
- `reconcile_ext/models.py`: added `ExtSnapshot.gap_fill_footprints: list[Polygon]`.
- `reconcile_ext/io/v3_snapshot.py`: populated it from V3 `slabs` entries with `room_id=None` (V3's gap-closure output).
- `reconcile_ext/stages/reflex_vertices.py::_merged_footprint` and `reconcile_ext/pipeline.py` building_footprint_xz block: union gap-fill footprints with part footprints before Douglas-Peucker simplify.

**Why**
- Reflex detection was treating V3-closed scan-registration gaps as extension seams. V3 already decided "these two rooms are one volume, just scanned with 5-15cm drift" and emitted a gap-fill slab to bridge them; the ext pipeline then read the raw part footprint (pre-closure) and saw a notch at the bridged gap, producing a false reflex vertex that got promoted to a strong seam hypothesis. Healing the notch by unioning V3's gap-fill polygons upstream honors V3's decision rather than re-litigating it.
- Probe on `bb013161` confirmed: part footprint 139.19 m², union with 2 gap-fill slabs = 140.81 m² (+1.6 m² of healed notch). Each gap-fill's `ratio_inside=0` against the raw part footprint — they're strictly outside and strictly bridging.

**Result**
- Corpus: reflex 466→451 (-15), strong seams 438→425 (-13), medium 28→26. 176/223 buildings had V3 gap-fill slabs to consume.
- `bb013161` went from reflex=3 strong=2/1 (before gap healing) to reflex=3 strong=2 medium=1 (essentially unchanged — its reflex corners are the real L-junction, not gap artefacts).
- The drop is modest because V3 already does tight morphological closure at 0.05m before emitting `V3Part.footprint_xz`, so only gaps V3 couldn't close at that stage (5-50cm registration drift) get picked up here as healing targets. The more impactful cohort would be cross-part seams V3 doesn't close at all, which we should surface separately rather than heal.
- Cross-story gap-fill slabs are almost all `contained_in_parts=True` (they fill vertical gaps between stories, not footprint notches) so they're a no-op for this union — correct behaviour, no filtering needed.
- **Follow-up (same day):** audited V3 for other closure outputs worth consuming.
  - `flat_ceilings[over="gap"]` (854, 1-to-1 with gap slabs): ceiling counterpart to each floor slab. Adding both *raised* reflex count (466→455 instead of 466→451) because ceiling XZ drifts from slab by ~wall-thickness, and unioning both injects staircase edges. Keep slabs only.
  - `flat_ceilings[over="fill"]` (5 across corpus, from `fill_remaining`): added — caps leftover top-story footprint pieces V3 committed to as envelope. No empirical effect on this corpus (too few) but conceptually correct.
  - `flat_ceilings[over="room"]` (1726): per-room interior, already inside `V3Part.footprint_xz`. Skipped.
  - `wall_extensions`: vertical strips, not footprints. Skipped.

## 2026-04-20 — Ridge/eave scorer: widen soft sigmas for asymmetric gable extensions

**What changed**
- `scripts/score_candidates_ridge_eave.py`: `INCLINATION_MATCH_SIGMA_DEG` 5.0→10.0, `EAVE_HEIGHT_PARITY_SIGMA_M` 0.5→2.0.
- `reconcile/viewer-main.js`: added `candidateFaces`, `reconstruction`, `ridgeEave`, `gableExtension` to `getVisiblePickRoots()` so plane faces are right-clickable; right-click handler now appends score/azimuth/inclination/plane-group summary to the copy-to-clipboard status line.

**Why**
- User flagged four valid asymmetric-gable pairs scoring RED: e028bcc5 (L-shape, Δinc=5.3°, Δeave=1.0m), c87c1e25 (cross-wing extension, Δinc=3.8°, Δeave=1.29m), 720c2f50 (shallow extension, Δeave=1.16m), 146ecf8b (shallow-pitch extension, no eave-wall contact, fallback Δ=2.17m).
- Diagnosis: `horizontality` and `azimuth_opposition` were near-perfect (>0.98) in all four; the score collapsed on `inclination_match` (σ=5° too tight for real pitch asymmetry) and `eave_height_parity` (σ=0.5m admits only mirror-symmetric gables, rejects salt-box / dropped-eave / cross-wing extensions). Widening both σ to cover real architectural asymmetry, not just scan noise.

**Result**
- All four flagged pairs now GREEN: e028bcc5 pair1 0.278→0.871, c87c1e25 pair0/1 0.165→0.870, 720c2f50 pair0 0.263→0.920, 146ecf8b pair0 0.032→0.745.
- Corpus: 393 pairs, GREEN share 49.9%→63.6% (+54 RED→GREEN flips, 0 GREEN→RED flips). No regressions on previously-GREEN pairs.
- Viewer: right-click on a ridge-eave / candidate / reconstruction / gable-extension face now copies the element UID and shows `az=… inc=… score=… pg=…` in the status bar, making it possible to share IDs back in chat.

## 2026-04-20 — Ridge/eave scorer: cubic-envelope exterior gate; revert widened sigmas

**What changed**
- `scripts/score_candidates_ridge_eave.py`:
  - Reverted sigmas to scan-noise bands: `INCLINATION_MATCH_SIGMA_DEG` 10.0→5.0, `EAVE_HEIGHT_PARITY_SIGMA_M` 2.0→0.5.
  - Added `_top_story_wall_top_y` (max Y of top-story `walls_merged` corners — building's wall-top envelope).
  - Added `_load_scan_y_max_by_parent` (indexes `merged_roof_segments[].corners` Y-max by segment id from `reconcile/reconcile_v3_results.json`).
  - New exterior gate in `_score_building`: candidates whose physical scan `y_max < wall_top_y − EXTERIOR_SCAN_TOL_M` (0.5 m) are dropped before plane-group construction.
  - New CLI flag `--v3-results` defaulting to `reconcile/reconcile_v3_results.json`.

**Why**
- Regression flagged by user on the previous widening turn: `d32d5562-5763-4c71-a816-6732c638fa6a::ridge-eave-candidate::segment-0:gap-cross_story-0-4:piece-0:seg-28` scored GREEN as an "obvious non-gable". Diagnosis showed its `Δeave_y=1.17 m` sits inside the band the widened σ=2.0 m opened — the same band the four target gables need. Pure σ tuning could not separate them.
- User's directive: use the building's "cubic envelope" — x,y,z bounds from walls and floors — to drop planes whose scan sits well below wall tops. These are interior geometry (cellar/attic vault faces, lower-floor scan noise); their extrapolated planes produce spurious mirror matches against real roof planes. Top-story `walls_merged` Y-max is the cheapest, most physical realization of "roof envelope ceiling".
- Diagnostic script confirmed: on the regression building (`d32d5562` wall_top=2.43 m) seg-28 sits at scan `y_max=−0.11 m` — **2.5 m below** the wall tops. It is cellar geometry, not roof. The four previously-widened target pairs (e028bcc5, c87c1e25, 720c2f50, 146ecf8b) are also 3.0–4.4 m below their wall tops and correctly drop out — the user confirmed these are interior features, not valid roof extensions.

**Result**
- Corpus: 13,105 → 7,673 kept candidates (5,432 interior filtered, 41.4%). 260 pairs (from 445 plane-groups / 107 buildings with ≥1 pair) with a clean bimodal score distribution: 44.2% ≥ 0.95, 30% < 0.3.
- Regression fix: `d32d5562` no longer pairs seg-28 (dropped as interior); only a legitimate gable pair (score 0.99) and one low-score pair remain.
- The four previously-target buildings now have only their real main-gable pairs scoring GREEN (e028bcc5 0.99, c87c1e25 0.98, 720c2f50 0.95, 146ecf8b 0.83); the asymmetric-extension candidates the widened σ admitted have been filtered as interior geometry, which matches the user's refined framing.
- Output written to `reports/ridge_eave_scores_20260420/scores.json` (9.6 MB). Each building now reports `wall_top_y`, `n_candidates_input`, `n_filtered_interior` alongside the pair list.

## 2026-04-20 — Ridge/eave scorer: plane-group selection + envelope union

**What changed**
- `scripts/score_candidates_ridge_eave.py`:
  - Added `SELECTION_SCORE_THRESHOLD = 0.30`.
  - Each plane-group now carries a `selected` flag (`best_score >= threshold`); candidates inherit it.
  - Per-building `envelope_xz` / `envelope_area_m2` = union of selected plane-groups' footprints, clipped to scan footprint — the surviving roof surface after competing invalid planes are dropped.

**Why**
- User pointed at two Phase A candidates on `d32d5562` — a GREEN segment-10 plane (45° pitch, score 0.99, real main-gable face) and a RED segment-7 plane (26° shallow pitch, score 0.03, no valid mirror) — and asked why the green plane doesn't continue through where the red one sits. Diagnostic confirmed both plane-groups are extrapolated over the **same 55 m² footprint** with full XZ overlap; Phase A just clipped each against the other's ridge so they tile the same ground. The exterior gate passes both (both have scan_y at or above wall tops); the scorer labels them green/red; but nothing was consolidating them into a single envelope. Selection by `best_score` lets the green mirror-paired plane absorb the red competitor's footprint.

**Result**
- `d32d5562` pg-7d1e (0.99, 45°, az 297.7°) + pg-ab09 (0.99, 46°, az 117.6°) selected; pg-27c8 (0.03, 26°) dropped. Envelope 55.08 m². 26/33 candidates selected — both user-flagged IDs correctly labelled (`segment-10:seg-17` selected, `segment-7:seg-1` not selected).
- Corpus: 298/445 plane-groups (67%) selected; 102/223 buildings have ≥1 selected plane-group. Each building now exposes `envelope_xz` for viewer overlay and `n_plane_groups_selected` for aggregate tracking.
- Threshold chosen below the corpus's bimodal RED/GREEN elbow (median of "not-selected" pg's is < 0.1; median of "selected" is > 0.9) so architectural asymmetry isn't pruned while clear false planes are.

## 2026-04-20 — Ridge/eave scorer: exterior gate at plane-group granularity; viewer renders plane-group unions

**What changed**
- `scripts/score_candidates_ridge_eave.py`:
  - Exterior gate moved from per-candidate to **per-plane-group**. A plane-group survives iff `max(scan_y_max across its members) >= wall_top_y − EXTERIOR_SCAN_TOL_M`. Plane-groups are built first from all candidates, then filtered wholesale.
  - Per-plane-group output now includes `union_xz` (exterior ring of the union footprint) and `plane` (rep plane equation).
- `reconcile/viewer-modules/v3-model.js`: for each **selected plane-group**, render ONE face using `union_xz` lifted via the rep plane — replaces fragmented per-piece rendering. Unselected plane-groups still render individual pieces at 0.12 opacity for inspection. Locator on the union face carries `plane_group_id`, `memberIds`, and `area_m2=total_area`.

**Why**
- User pointed at `d32d5562::candidate-face::segment-10:...seg-29` — physically on the GREEN plane (same plane equation, az 297.7°, inc 45.3° as the `seg-17` piece rendered green) but its parent merged_roof_segment has `scan_y_max = −0.06 m` (cellar-level scan). The per-parent exterior gate dropped it before plane-grouping, so it never entered pg-7d1e and the union didn't include its footprint.
- A plane either IS or ISN'T part of the roof envelope — the question should be decided per plane (group), not per raw scan segment. A real roof plane routinely has some pieces scanned from below (gable ends, dormer returns); dropping them splinters the envelope. Using `max(scan_y)` across members — the plane reaches the wall tops *somewhere* — is the right invariant.
- Viewer rendering fragmentation was the second-order symptom: even after scoring, each plane was drawn as ~14 Phase A pieces whose edges come from intersections with every other candidate plane (including dropped RED ones). Drawing the plane-group's union polygon unfragments it — user sees a single clean face per surviving plane.

**Result**
- `d32d5562` pg-7d1e now has 21 members (was 14), union area **55.1 m²** (was 37.1 m²); pg-ab09 22 members, 55.1 m². `seg-29` correctly in pg-7d1e, selected, score 0.99. `seg-7:seg-1` still in pg-27c8, RED, dropped.
- Corpus: 447 plane-groups, 259 selected (57.9%). Pair count up to 291 (from 260) because more members → more supporting geometry for each plane → more valid mirror pairs found.
- Viewer: selected plane-groups render as single ~55 m² faces per side; dropped planes still visible at low opacity so the Phase A arrangement remains debuggable.

## 2026-04-20 — Raw per-room ceiling polygons exposed in viewer

**What changed**
- `reconcile/extract3d/scan_data.py`: added `load_raw_ceilings()` and `build_raw_to_merged_index()`. Parses `ceiling_merged_<room-id>.json` (+ `ceiling_metadata_<room-id>.json`) from `.scan-cache/` — files that `load_raw_rooms()` has always skipped.
- `reconcile/extract3d/builder.py` and `reconcile/extract_3d.py`: per-room `raw_ceiling_polygon` (3D world-space) and `raw_ceiling_source` ("scan" / "noMesh" / etc.) now attached to each room in `buildings_3d.json`. The existing derived `ceiling_polygon` (built from wall-tops) is untouched so the roof pipeline stays stable.
- Viewer: new `ceiling-raw` element kind (`<story>:<room_index>`) rendered as a per-room polygon mesh + edge loop in `groups.rawCeilings`. Constants `RAW_CEILING_COLOR`/`RAW_CEILING_EDGE` added; `rawCeilings` wired into `LAYER_CONTROL_IDS` + `PIPELINE_STEPS` ("openings and slabs"). Checkbox added in `reconcile/viewer.html` (defaults to on). `VIEWER_MODULE_VERSION` bumped to `20260420a` to bust the cache.
- `CLAUDE.md`: element-kinds table updated with `ceiling-raw`.

**Why**
Apple RoomPlan writes a per-room ceiling polygon alongside each room scan, but the extraction pipeline discards it. This leaves us with only the synthesized `ceiling_polygon` (flat, derived from wall tops) — which drops any real ceiling geometry the scan captured. Surfacing the raw scan polygon lets us (a) compare scan-truth against the derived placeholder, (b) spot vaulted/sloped ceilings where the derivation loses information, and (c) have a scan-anchored ceiling signal available for reconstruction work (per the "physical scan features over extrapolation" feedback).

**Result**
- Tested on `9c07bf97-...` (Agertoften 11, Otterup): all 11 rooms populated with `raw_ceiling_polygon`. Source reports `noMesh` (no true ceiling mesh captured) so the polygons are planar; floor-to-ceiling delta ~2.35 m, a plausible dwelling height.
- 237 of 238 tests pass; the lone failure (`test_score_results.py`) is unrelated scoring-parity code.

---

## 2026-04-20 — Ceiling planes: use raw variant + SVD, keep all planes

**What changed**
- `reconcile/extract3d/scan_data.py` + `reconcile/extract_3d.py::load_raw_ceilings`: now read `ceiling_<room-id>.json` (raw-session frame) instead of `ceiling_merged_<room-id>.json`, and return ALL `walls` entries from each file — not just `walls[0]`. Each file can carry several planes (one flat panel plus sloped panels for vaulted/pitched rooms).
- `reconcile/extract3d/builder.py::_merge_ceilings_by_room` (new helper) + equivalent block in `reconcile/extract_3d.py`: for each raw room, apply the plane's own transform to get raw-session-world corners, then apply the per-room SVD `(rot, trans)` already computed for walls/openings so the output sits in merged-building space. Rooms now carry `raw_ceiling_planes: [{corners}, ...]` instead of a single `raw_ceiling_polygon`.
- Viewer (`viewer-main.js`): iterate `room.raw_ceiling_planes` and render each plane as a separate mesh + edge. Element IDs gain a `:<plane_index>` suffix (`<story>:<room_index>:<plane_index>`); `CLAUDE.md` updated accordingly. Cache-bust `VIEWER_MODULE_VERSION=20260420b`.

**Why**
User report: raw ceilings rendered as uniformly flat with no slope/vault, and appeared to sit in the wrong coordinate frame. Two distinct bugs were in play. (1) The previous loader took only `walls[0]` and dropped every additional plane, so vaulted ceilings collapsed to their first panel. A corpus sweep across `.scan-cache/` showed 842 of 2443 raw ceiling files carry >1 plane; the richest building (`1f03f6e0-…`) has 182 planes across 29 rooms. (2) Using the `ceiling_merged_*` transform relies on an internal Apple pose that is not, in fact, aligned to `merged.json` — walls/doors/windows all go through `compute_room_transforms`' SVD (raw→merged) instead, and ceilings must do the same or they float in the wrong frame. Using the raw file + the existing per-room SVD keeps ceilings co-located with the walls they sit above.

**Result**
- Extraction on `1f03f6e0-…` yields 182 ceiling planes across 29 rooms; 113 of them have >0.2 m Y-variation (genuine slopes), up to a 3.0 m delta — i.e. the previously-lost vaulted/pitched geometry is now preserved.
- Multi-plane test building source reports `userScannedMesh` (actual captured mesh, not a synthesized flat), confirming we are no longer discarding scan-captured ceiling shape.

---

## 2026-04-20 — Viewer: dispose rawCeilings on building switch

**What changed**
- `reconcile/viewer-main.js::loadBuilding`: added `groups.rawCeilings` to the disposeGroup list that runs when `currentBuilding` changes. Cache-bust to `20260420c`.

**Why**
User report: when stepping through buildings in the viewer, raw ceilings from previously-viewed buildings persisted in the scene — making it look like a single building had scans from multiple properties stacked on it. The cause was simply that the new `groups.rawCeilings` layer I added earlier in the day wasn't included in the per-building disposal sweep, so its Three.js children accumulated across loads.

**Result**
Switching buildings now clears prior raw-ceiling meshes; the layer reflects only the current building's scan planes.

---

## 2026-04-20 — Ceiling planes: per-plane spatial reassignment to rooms

**What changed**
- `reconcile/extract3d/ceilings.py`: new `reassign_raw_ceiling_planes_spatially(rooms_out)` helper. For each plane on each room, take its XZ centroid, find the same-story room whose floor polygon contains it, and move the plane there. Falls back to the room with max XZ overlap area, then to the current assignment — never silently drops a plane.
- `reconcile/extract3d/builder.py` and `reconcile/extract_3d.py`: run the reassignment right after `clip_floor_overlaps` / `_clip_floor_overlaps` so floor polygons are final before spatial lookup. `extract_3d.py` carries a `_reassign_raw_ceiling_planes_spatially` inline twin for the CLI path.

**Why**
User report persisted after the viewer-side disposal fix: raw ceilings still "looked like" they belonged to neighbour rooms/properties. Investigation: Apple RoomPlan's ceiling file per room captures a *mesh region* that can extend well past that room's floor — 20 rooms in the corpus had planes whose corners sat >2 m outside their own floor bbox. Concrete case `d8308bfc-… room 11`: seven planes, several centred at x≈+1…+2.8 while the room's floor spans x=[-6.3, -2.3]. Those planes physically belonged to neighbouring rooms (13, 2, etc.) in the same building but got attached to room 11 because the ceiling filename keyed off room 11's scan. The spatial pass reassigns each plane to the room whose footprint actually sits beneath it.

**Result**
- Post-fix on `d8308bfc-…`: every room's ceiling planes now sit within its own floor bbox (0 outliers across the building). Room 11 drops to 0 planes (its captured mesh was entirely over neighbours); room 13 gains 8 planes; room 2 picks up 11 planes — all spatially correct.

**What changed**
- `scripts/score_candidates_ridge_eave.py::_score_building`: `best_per_group` now also tracks `best_ridge_xz` (XZ endpoints of the best-partner pair's ridge). New helper `_split_pg_union_at_ridge` splits each selected plane-group's union polygon at that ridge using the existing `_split_scan_by_ridge`, then classifies each piece by `centroid·downslope_xz` — `>=0` = physical downslope side, `<0` = upslope side past the ridge. The plane_group_summary now emits `union_below_ridge_xz` (physical) and `union_above_ridge_xz` (extrapolation) as lists of XZ rings, plus `best_ridge_xz` passthrough for the viewer.
- `reconcile/viewer-modules/v3-model.js::renderRidgeEaveScoring`: the per-plane-group render loop now draws the below-ridge rings in `scoreColor(best_score)` and the above-ridge rings in a light-blue `0x88CCFF`, sharing the same plane for Y-lift. Element inner-id gains a `::below-ridge` / `::above-ridge` suffix and a `ridgeSide` locator field. Falls back to the full `union_xz` with score color when a plane-group has no ridge split (no best partner or degenerate split).

**Why**
For a symmetric gable pair (`azimuth_opposition ~ 180°`, `inclination_match`, `horizontality`, `eave_height_parity` all high), Phase A ridge-extrapolation extends each plane past the ridge onto the partner's side — physically, that portion of the plane isn't a roof surface, it's just the mathematical continuation. Rendering the full union in a single color hides that distinction; splitting it and painting the above-ridge portion light blue lets a reviewer immediately see which part of each plane is real (scanned / resting on walls) and which part is Phase A extrapolation.

**Result**
- Corpus run: 223 buildings / 447 plane-groups / 291 pairs in 3.8 s; `scores.json` grew from 16.3 MB → 16.8 MB with the new per-plane-group split rings.
- Smoke check on first 3 buildings: selected plane-groups get 1 below-ridge ring + 1 above-ridge ring each (e.g. `016980bc::plane-group::bca2326594b1 score=0.91`). Unselected groups emit empty arrays. Viewer syntax-check (`node --check`) clean.

---

## 2026-04-20 — reconcile_ext units: replace reflex-vertex cuts with rectangular decomposition

**What changed**
- `reconcile_ext/stages/units.py`: full rewrite. Dropped `_inward_edge_extensions` + polygonize-with-snap approach. New pipeline: `_principal_azimuth_deg` (edge-length-weighted, 2° bins, folded to [0,90°)) → `shapely.affinity.rotate(-az)` → `_grid_decompose` (unique X/Y snap at 0.12m → axis-aligned cells whose centre is interior) → `_merge_boxes` (greedy pairwise merge of rects sharing a full horizontal or vertical edge) → rotate back. Fallback: if rotated-frame axis-aligned edge fraction < 0.70 (`_rectilinearity_coverage`), emit the whole footprint as a single unit. Cut lines derived from `unary_union(rect_boundaries).difference(footprint_boundary.buffer(0.02))`, filtering segments shorter than 0.2m. Constants: `_MIN_UNIT_AREA_M2 = 4.0` (up from 2.0), `_GRID_SNAP_TOL_M = 0.12`, `_AXIS_TOLERANCE_DEG = 12.0`.
- `reconcile/viewer-ext.html`: cache-buster `?v=20260420d` → `?v=20260420e`.

**Why**
Martin: "I find now that there are maybe too many divisions. wdyt?" followed by "it's maybe more that rectangular units should be the primitive?" The reflex-vertex cut approach produced a cut at every concave corner, which over-segments buildings whose wall jogs are cosmetic rather than true part boundaries. Rectangular decomposition in the building's own frame forces each emitted unit to be an axis-aligned rectangle (relative to the dominant wall orientation), which matches how residential extensions are actually built — a main rectangle plus smaller rectangular annexes — and suppresses oblique/noisy cuts by construction.

**Result**
- Corpus run: 187 buildings processed. Unit distribution: 1=43, 2=53, 3=51, 4=25, 5=8, 6=6, 8=1. Median 2-3 units per building; long-tail of 5-8 units on complex footprints indicates the greedy merge is not globally minimal — e.g. `2f382701` at 6 units (33/24/10/8/7/6 m²) or `e9f0631f` at 8 units (63/32/23/21/20/19/17/10 m²). `019e1376` yields 3 clean units (main 59.3 m² + 18.5 m² + 16.2 m², all 4-pt rectangles) with 14 interior cut-line fragments at the azimuth-rotated boundaries. Not yet visually verified in the viewer; pending Martin's reload.

---

## 2026-04-20 — Ridge/eave scorer: ridge_reach_parity catches interior planes

**What changed**
- `scripts/score_candidates_ridge_eave.py`: new physical check `ridge_reach_parity` compares the scan `y_max` (over all member parent segments) between the two planes of a pair. Constant `RIDGE_REACH_PARITY_SIGMA_M = 2.0`. Plane-groups now carry `scan_y_max` precomputed in `_score_building` (also reused by the exterior gate). Score aggregation changed from `GM(4 parity components)` to `GM(4 parity) × ridge_reach_parity` — mirror-parity components stay as a geometric mean while ridge-reach is a killable multiplicative gate (0.1 on one side drops an otherwise-perfect 0.97 match to 0.097). Each pair now also emits `ridge_reach_gap_m`, `scan_y_max_a`, `scan_y_max_b`; each plane-group summary emits `scan_y_max`.

**Why**
User flagged `b8cefbc4::plane-group::540114200d86` as "way too internal". Diagnosis: the plane passed all four existing mirror-parity checks (horizontality 0.94, azimuth_opposition 0.99, inclination_match 0.97, eave_height_parity 0.998 → GM 0.974) but its physical scan max_y was 5.77 m while its partner `030b8d39b8b2` reached 8.86 m. A real gable pair has both planes terminating at the same ridge elevation; a 3 m vertical gap means the plane literally stops meters below where the ridge would sit, i.e. it's an interior attic face that happens to share coefficients with a mirror of a real roof plane. The existing four components check plane-equation parity but not physical ridge reach — this gap is the missing signal.

**Result**
- `540114200d86`: score 0.9739 → **0.089** (ridge_reach_parity 0.092 on 3.09 m gap) → now unselected ✓
- Real gable pair `5a18e00cc344 × 030b8d39b8b2` (scan gap 1.17 m): 0.9804 → 0.70 → still selected ✓
- `4526a48ad367` (already dropped on eave_height_parity): score 0.026 → 0.0001 — unchanged dropped
- `f4d638b6e2eb` (scan gap 1.88 m, possibly a dormer/wing): 0.80 → 0.33 — still selected, borderline
- Corpus: 259 → 147 selected plane-groups (40% drop). Reflects that many prior "selected" pairs were plane-equation twins with mismatched physical extents; most of those are buildings like `1f03f6e0` (182 ceiling planes, complex multi-level / mixed-use) where pair-ridge_y differences of 10+ m indicated the mirror matches weren't real roofs at all.

---

## 2026-04-20 — Ridge/eave scorer: robust scan_y_top vs outlier parents

**What changed**
- `scripts/score_candidates_ridge_eave.py`: split the per-plane-group scan-Y statistic into two quantities. `scan_y_max` remains the hard max across all member parent segments (still used by the cubic-envelope exterior gate, which wants the absolute tallest point). `scan_y_top` is new: median of the top-3 per-parent maxes (or the single max when <3 parents). `ridge_reach_parity` now reads `scan_y_top` rather than `scan_y_max`, so a single chimney / dormer parent whose scan shoots past the ridge no longer pulls the estimate up and kills an otherwise-valid gable. Both values are persisted in `plane_group_summary` and in the pair output (`scan_y_top_a`, `scan_y_top_b` alongside `scan_y_max_a/b`) for debuggability.

**Why**
User flagged `0b75d30e::segment-{0,1}:gap-cross_story-1-4:piece-0:seg-7` as a regression: a visually valid gable pair turned red. Diagnosis: plane A had six member parents whose per-parent scan maxes were [15.92, 10.34, 8.75, 6.25, 5.66, 5.63]. The 15.92 m value is an outlier — a chimney / dormer / small protrusion on one parent. The bulk of the plane and its partner both cap at ~10 m (partner's top was 10.22 m, top-3 median 10.04 m). The hard `scan_y_max = 15.92 m` produced a 5.70 m gap against the partner → `ridge_reach_parity = 0.0003` → killed the pair even though 5/6 parents agreed with the partner's elevation. Using the top-3 median trims the outlier without losing the "plane physically reaches the ridge" signal, because at least three parents at that elevation is enough physical evidence. The interior-plane kill is preserved: `540114200d86`'s top-3 = [5.48, 5.76, 5.77] → median 5.76 m, and its partner's scan still tops out around 8.86 m, so the gap (3.09 m) remains wide enough that `ridge_reach_parity ≈ 0.09` still fires.

**Result**
- `0b75d30e` (regression target): `ridge_reach_parity` recovers from 0.0003 to 0.978 (gap 0.30 m), best score 0.0003 → **0.929** — pair re-selected ✓
- `b8cefbc4::540114200d86` (interior kill target): `ridge_reach_parity` stays at 0.092 (gap 3.09 m), score stays at 0.090 — still unselected ✓
- Corpus: 147 → 165 selected plane-groups (+18). The robust statistic recovers plane-groups that the hard max had falsely demoted due to single-parent outliers (chimneys, dormers, low-area protrusions) without readmitting the genuinely-interior planes the previous pass caught.

---

## 2026-04-20 — Gap walls: polygon-wide floor + ceiling caps for within-story gaps

**What changed**
- `reconcile/extract_3d.py:_compute_gap_walls` (lines ~1282–1310): after the existing per-edge vertical wall quads, emit a single `gap_floor` quad using all gap-polygon vertices at `gap_floor_y`, plus a matching `gap_ceiling` quad at the median per-vertex ceiling Y (from `_snap_vertex_y`). Strips the duplicate closing vertex before emission. Preserves `room_index` when present.
- `reconcile/extract3d/gaps.py:compute_gap_walls` (lines ~542–590): same polygon-wide cap, placed immediately after the vertical-walls loop and before the existing short-edge cap logic. Ceiling Y uses `median(snap_ceiling_y(v) for v in edge_verts)` so the cap stays flat instead of slanting per-vertex.
- `reconcile/buildings_3d.json`: regenerated for `9bdc330e-6144-499b-9c70-3fc6f0c4ebf3` — `gap_walls` count 66 → 78 (6 new `gap_floor` + 6 new `gap_ceiling` entries across stories 0 and 1).

**Why**
User reported that the gap between `9bdc330e::floor::0:14` and `9bdc330e::floor::0:15` renders open in the full model but closed in v3. Rooms 14 and 15 share three exact XZ vertices but their floor Ys differ by ~3 cm, and Room 14's post-clip `floor_polygon` has 19 corners in a re-entrant zigzag. `compute_cross_floor_gaps` detects the leftover ribbon as a high-confidence `within_story` gap (2.001 m², 17 corners, min_edge≈0, **max_edge 7.011 m**). The old gap-walls code emitted only vertical wall quads around the perimeter (plus, in the module version, tiny 0.30 m × 0.25 m cap quads on wall-thickness cross-edges) — for long ribbons no floor cap was produced, leaving a visible hole. `reconcile_v3.close_obvious_gaps` already solves this by emitting a `V3Slab` covering the full gap polygon; this change ports the same idea into the heuristic full-model path, restoring v3/full-model parity for the closed-gap case without touching the clipping or detection stages.

**Result**
- `9bdc330e-6144-499b-9c70-3fc6f0c4ebf3`: 6 polygon-wide `gap_floor` caps emitted (story 0: 16-vertex cap bbox `(-2.02,-2.39)→(8.93,4.39)` covering the 14↔15 ribbon, plus the low-confidence story-0 ribbon at `(2.07,4.22)→(2.65,4.98)`; story 1: four more caps). Matching `gap_ceiling` caps use median per-vertex wall-top Y so the cap is flat.
- Tests: full suite 237 passed (the pre-existing `test_math_parity_from_label_records` failure is unrelated — inference column is `None` on the baseline branch too).
- Not yet visually verified in the browser (Chrome extension not connected in this session); data confirms the viewer at `localhost:8080` now serves the updated JSON, so reloading `?uuid=9bdc330e-6144-499b-9c70-3fc6f0c4ebf3` will pick up the new `gap-wall` floor quads.

---

## 2026-04-20 — Wall extensions: polygon-aware slab-above picker (v3 parity)

**What changed**
- `reconcile/extract3d/ceilings.py`: added `find_best_slab_above(wall_corners, wall_top_y, slabs_above, min_margin=0.05)`. Takes a list of `(shapely_polygon_xz, floor_y)` tuples; returns the slab Y whose polygon is closest (by XZ distance from the wall midpoint) to the wall and strictly above `wall_top_y + min_margin`, or `None` if no eligible slab. Mirrors `reconcile_v3.stages.wall_extensions._pick_slab_above`.
- `reconcile/extract_3d.py` (lines ~2830–2878): replaced the legacy `_find_closest_slab_y` centroid heuristic with the polygon-aware `find_best_slab_above`. `story_slabs` now keys each story to a list of `(shapely_polygon_xz, floor_y)` tuples built from room floor polygons. The old `_find_closest_slab_y` helper was removed. `from reconcile.extract3d.ceilings import find_best_slab_above` added at the top.
- `reconcile/extract3d/builder.py` (lines ~585–665): same migration. Adds `from shapely.geometry import Polygon`, includes `find_best_slab_above` in the `.ceilings` import, builds `story_slab_polys` from rooms only, keeps the existing same-story half-level inclusion (floors > 1.0 m above the room). Gap polygons deliberately excluded — they're too loose for XZ proximity (see below).
- `reconcile/buildings_3d.json`: regenerated for `9bdc330e-6144-499b-9c70-3fc6f0c4ebf3` using the builder path — 25 wall extensions (vs 25 pre-change), and 22/24 match v3's extension set exactly.

**Why**
User reported that wall extensions render better in v3 than in the full model. Root cause: the full-model picker (`_find_closest_slab_y`) minimised XZ distance to each slab's **centroid**, while v3's `_pick_slab_above` minimises distance to the slab's **polygon** (via `shapely.Polygon.distance(Point)`). For L-shaped or elongated stories where the wall midpoint is well outside the floor centroid, the centroid picker would reach for the wrong slab — or, worse, pick a same-story gap-derived slab high above when a room slab directly overhead was closer by polygon distance. Six walls on building `9bdc330e` demonstrated the failure: their extension tops were snapping to `y=1.67` (a cross-story gap slab) instead of `y=1.23–1.25` (the correct room slab above). Porting v3's polygon-aware picker fixes this; also restores v3/full-model parity for knee walls / cantilevers / interior extensions because the decision is now driven by the same spatial test.

**Why gap polygons excluded from the picker's candidate pool**
Initial port added `cross_floor_gaps` polygons to `story_slab_polys`, expecting them to act like v3's `V3Slab`s. That regressed six walls to the old Y=1.67 outcome. Reason: the full model's gap polygons are post-detection, loosely-bounded ribbons (e.g. a story-1 cross-story gap with 35 corners covering a broad L-shape), whereas v3's `V3Slab` polygons are shrunken/simplified per-room footprints. A big loose gap polygon "contains" the wall midpoint at distance 0 and wins the tie-break over the real room slab. The fix: restrict the candidate pool to room floor polygons (matches the existing behaviour in `extract_3d.py` prior to this change); same-story rooms floating > 1.0 m above are still included for half-level cases.

**Result**
- `9bdc330e`: six walls (rooms 12–16) that previously extended to `y≈1.67` now extend to `y≈1.23–1.25`, matching v3's cantilever decisions. 22 of 24 v3 wall-extensions now match the full-model set exactly; the 3 residual diffs are tie-breaks on near-equidistant slabs (v3's simplified `V3Slab` polygon vs full-model's raw `floor_polygon`), which is acceptable within v3/full design differences.
- Tests: 237 passed (`tests/ --ignore=tests/test_score_results.py`).
- Not yet visually verified in the browser.

---

## 2026-04-20 — Ridge/eave scorer: revert ridge_reach_parity from score

**What changed**
- `scripts/score_candidates_ridge_eave.py`: removed `ridge_reach_parity` from score aggregation. Score is back to `GM(horizontality, azimuth_opposition, inclination_match, eave_height_parity)`. The `ridge_reach_gap_m` is still computed and emitted in pair output for diagnostic use, and `scan_y_top` is still stored on plane-groups, but neither contributes to the decision. Constant `RIDGE_REACH_PARITY_SIGMA_M` deleted. Scoring manifest aggregation string restored to `"gm_of_4_mirror_parity"`.

**Why**
Corpus feedback revealed the check was too aggressive. User flagged valid gable pairs killed by it on three unrelated buildings (c87c1e25, e0155eef, 16784bad), all with `rr_gap` in the 2.8–3.6 m range — the same range that had killed the `b8cefbc4::540114200d86` "interior plane" we were trying to catch. Investigation showed the 2.8–3.6 m asymmetry band is populated by real gables where one plane had occluded or partial scan coverage near the ridge (trees, scanner position, room access on one side of the roof only). Without a reliable way to separate "plane A really stops here" from "plane A was scanned short here," the check cannot be a hard gate — it produces false positives that collectively outnumber the interior-plane kills it catches. Per the memory entry on physical-ground-truth-over-extrapolation, the 4 mirror-parity components remain scan-anchored via eave_height_parity (tied to wall-top Y) and are enough to exclude the cleanly-wrong cases without overconstraining.

**Result**
- c87c1e25 top pair: 0.065 → **0.984** ✓ (user-confirmed real gable)
- e0155eef top pair: 0.042 → **0.995** ✓
- 16784bad top pair: 0.128 → **0.997** ✓
- 0b75d30e (regression case): 0.929 → 0.950 — still selected ✓
- b8cefbc4::540114200d86 (earlier flagged as "interior"): 0.090 → 0.974 — now selected again, accepting that the physical scan-gap signal cannot be used to separate this from genuine gables. If we want to catch interior planes we need a different signal (viewer-side review, V3 reference-envelope overlap, or a per-plane-group bimodal-parent-Y split before pairing).
- Corpus: 165 → 259 plane-groups selected. The 94 recovered are presumed to be real gable pairs that happened to have scan-top gaps in the 2-5 m range from occlusion.

---

## 2026-04-20 — Ridge/eave scorer: widen sigmas for asymmetric structures

**What changed**
- `scripts/score_candidates_ridge_eave.py`: widened `INCLINATION_MATCH_SIGMA_DEG` from 5° to 12° and `EAVE_HEIGHT_PARITY_SIGMA_M` from 0.5 m to 2.0 m. Score aggregation unchanged (GM of the four mirror-parity components). Threshold unchanged (0.30).

**Why**
User flagged two plane-groups on e0155eef (`f7408c84a17c` and `595e10a43810`) that should be green but were being killed by inclination_match (~0.12-0.66) and eave_height_parity (~0.001-0.005) components. Direct question to the user about whether these were (a) a plane-grouping artifact, (b) a real secondary structure with genuinely different pitch/eave, or (c) a dormer — user confirmed (b): "Real secondary structure — a shed dormer, lower eave/roof section, or asymmetric dormer that genuinely has different pitch and eave from the main gable." The previous σ values were calibrated for symmetric gables only. They reject any asymmetric roof structure whose two sides have >5° pitch difference or >0.5 m eave offset — both common in real Danish housing (shed dormers, half-hips, stepped/tiered roofs, asymmetric extensions). The wider sigmas accept up to ~15° pitch and ~3 m eave variation before the score collapses, while still rejecting truly cross-element mismatches (30°/5 m absurd cases score ~0.04, far below threshold).

**Result**
- e0155eef `595e10a43810` (user flag 1): score 0.234 → **0.903** ✓ selected
- e0155eef `f7408c84a17c` (user flag 2): score 0.104 → **0.819** ✓ selected
- c87c1e25 main pair: 0.984 → 0.997 (no change in state)
- 16784bad main pair: 0.997 → 0.9994 (no change)
- 0b75d30e regression case: 0.950 → 0.991 ✓ still selected
- All 14 user-flagged segments across 3 buildings: selected ✓
- Corpus: 259 → 322 plane-groups selected (+63). The added ones are real asymmetric roof surfaces that previous σ values were rejecting as "not mirror-symmetric enough." Score distribution for newly-admitted plane-groups ranges from ~0.30 (threshold) to ~0.95 — the threshold gate still works, just against looser (more forgiving) sigma calibration.

## 2026-04-20 — Ridge/eave scorer: plane-coeff exterior gate + symmetry credit + unpaired-accept

**What changed**
- `scripts/score_candidates_ridge_eave.py`:
  1. Exterior gate now operates at the **plane-coefficient** level instead of per connected-component. A plane-group passes if ANY plane-group sharing the same canonical plane coefficients has a parent reaching wall-top (`scan_y_max ≥ wall_top_y − EXTERIOR_SCAN_TOL_M`).
  2. Added **symmetry credit**: a plane-group whose plane fails the direct gate still passes if it has a structural mirror partner (antiparallel downslope + footprint-adjacent within `MIN_FOOTPRINT_OVERLAP_OR_ADJ_M`) whose plane does pass.
  3. Added **unpaired-accept** at selection: plane-groups with no structurally valid mirror-pair (never entered `best_per_group`) are auto-selected as real one-sided roof planes (shed dormers, half-hips, wings whose opposite slope was filtered as interior). Plane-groups that DO have a pair but score below 0.30 remain red.

**Why**
User flagged `c87c1e25::segment-0::seg-65` (az=316°, real east-wing roof plane) and `c87c1e25::segment-1::seg-50` (az=136°, its mirror). `seg-65` lived in a spatially-disconnected connected-component of the main 316° plane whose own parents' scan_y_max was −1.14 m (below wall-top 0.84 m). The plane-coeff gate recognizes that the same plane elsewhere (main cluster) reaches y=4.19 m, so the east-wing cluster is kept. `seg-50`'s 136° plane has all parents below wall-top (surveyor never saw that slope from above), but it is the structural mirror of the 316° plane and is the real opposing side of the gable — symmetry credit admits it. Both are then selected as a valid mirror pair (score 0.8793).

**Result**
- `c87c1e25::seg-65` (316° east wing): `pgid=None, sel=False` → `pg=1bc8ebae0d30, sel=True, score=0.8793` ✓
- `c87c1e25::seg-50` (136° mirror, previously fully filtered as interior): `pgid=None, sel=False` → `pg=43aa23800ceb, sel=True, score=0.8793` ✓
- All earlier user-confirmed green elements on c87c1e25 / e0155eef / 16784bad: unchanged, still green.
- Corpus: plane-groups 458 → 503 (+45 via gate loosening + symmetry credit); selected 412 → 446 (+34); filtered interior: 394 (reflects the plane-coeff aggregation).
- No test coverage regression — existing green elements unchanged.

## 2026-04-20 — Preserve ceiling-partition holes + drop viewer fan-triangulation fallback

**What changed**
- `reconcile/roof_algorithms_py/roof_partitioning.py`: `_atom_corners` now returns `(exterior, holes)`. Shapely's `polygonize()` produces polygons-with-holes whenever the room's linework nests (a ceiling atom that encloses sibling partitions); the old code read only `atom.exterior.coords` and silently discarded interior rings. Both callers (`_build_implicit_flat_atom` and the main `derive_room_ceiling_partitions` loop) now write a `"holes"` field onto the atom record alongside `"poly"`.
- `reconcile/viewer_server.py`: `_renderable_surface_from_atom` propagates `atom["holes"]` into the rendered surface payload.
- `reconcile/viewer-modules/geometry.js`: `createPolygonMesh` no longer fan-triangulates from vertex 0 when `THREE.ShapeUtils.triangulateShape` throws or returns no triangles; it returns `null` with a console warning instead.

**Why**
Element `ebd94f02-abc2-476d-8bf9-9bdfbc2a58dd::ontology-renderable-ceiling::renderable:room_ceiling_flat:ceiling-partition:84e55cd1eaeafe6e2c05` rendered as a giant triangle spanning the attic. Root cause: the stored 35-vertex `poly` had shoelace area 44.92 m² but the atom's true `area_m2` was 18.98 m² — the ~26 m² gap was interior holes (sibling partitions) that `_atom_corners` silently dropped. With holes missing, the viewer either painted over every sibling or — when `triangulateShape` rejected the non-monotone exterior ring — fell back to a fan-from-0 triangulation that produces spanning triangles. A cohort scan over `roof_algorithms_py_results.json` found 23 partitions in 23 / 223 buildings (~10%) with the same shoelace-vs-stored-area mismatch, confirming this is a general heuristic bug rather than a one-off. A second reported case (`b01824fc-be43-451f-bc6e-aaab701c144d::floor::0:2`) is a different root cause — a self-intersecting floor ring from V1 extraction — but hit the same fan-fallback in the viewer, which Fix B now neutralizes.

**Result**
- Unit-test on a synthetic 10×10 square with a 4×4 hole: `_atom_corners` returns a 4-vertex exterior (shoelace 100) and one 4-vertex hole (shoelace 16), net 84 = `atom.area` ✓.
- `pytest tests/` → 237 passed, 1 pre-existing unrelated failure (`test_score_results.py::test_math_parity_from_label_records`, confirmed present on clean `HEAD`).
- End-to-end viewer verification requires regenerating `roof_algorithms_py_results.json` (451 MB baseline) — deferred pending user approval.

## 2026-04-20 — Cohort audit for dominant-height wall extension

**What changed**
- `scripts/audit_dominant_height_closure.py`: new, read-only audit script. Iterates `reconcile/buildings_3d.json`, groups `walls_computed` by story, span-weights their top-Y values, finds the dominant cohort (tolerance 0.15 m), and counts candidate walls under three progressively tighter gates: raw (span-outlier + delta), +floor match (bottom within 0.10 m of cohort floor-Y), +colinear with a dominant-cohort neighbour (angle 8°, perp 0.15 m, endpoint gap 0.80 m).

**Why**
User reported that on `d7f1aa19-5ca9-4e1b-ac1a-c86d63f9ede7::wall-computed::ECE2EC5E-D7FF-4A45-AF74-4508048CA73D:0:4` the top-of-wall gap should be closed because "all the walls of the building unit are sorta the same height and only a small part of the perimeter is lower". Existing `extend_wall_to_slab` only fires when a slab is found above the wall, so top-story / single-story walls stay short. Before touching the pipeline, generalize: measure how many buildings benefit from a dominant-height fallback so we don't ship a fix-of-one.

**Result**
- 319 stories across 187 buildings; 258 eligible (cohort ≥ 0.70 coverage).
- With an initial `MIN_PROMOTION_DELTA_M=0.05`, 390 walls passed all gates — but 38 % had delta < 0.08 m (scan noise, not real gaps) and the biggest promoter took 23 extensions.
- Tightening to `MIN_PROMOTION_DELTA_M=0.10`: **112 walls promoted across 48 / 187 buildings (26 %)**, top promoter drops to 8 walls, target wall `ECE2EC5E:0:4` (delta 0.170 m) is still captured. Locked as the production threshold.
- Chosen thresholds: `cohort_tol=0.15`, `min_cov=0.70`, `max_span_frac=0.25`, `min_delta=0.10`, `max_delta=0.40`, `floor_tol=0.10`, `colin_angle=8°`, `colin_offset=0.15 m`, `colin_gap=0.80 m`.
- Pipeline implementation (ceilings.py helpers + builder.py hook + tests) is the next step.

## 2026-04-20 — Dominant-height wall extension: pipeline implementation

**What changed**
- `reconcile/extract3d/ceilings.py`: added `compute_story_wall_top_cohort`, `should_extend_wall_to_dominant`, `extend_wall_to_dominant`, plus private helpers `_wall_bottom_chord_xz`, `_wall_record`, `_weighted_median`, `_is_colinear_neighbour`. Threshold module constants (`COHORT_TOLERANCE_M`, `MIN_COHORT_COVERAGE`, `MAX_OUTLIER_SPAN_FRAC`, `MIN_DOMINANT_DELTA_M=0.10`, `MAX_DOMINANT_DELTA_M=0.40`, `FLOOR_MATCH_TOLERANCE_M=0.10`, `COLINEAR_ANGLE_DEG=8`, `COLINEAR_OFFSET_M=0.15`, `COLINEAR_GAP_M=0.80`) live at the top of the module so they are tunable and discoverable.
- `reconcile/extract3d/lineage.py`: new step constant `STEP_EXTEND_WALL_DOMINANT = "extend_wall_to_dominant"`.
- `reconcile/extract3d/builder.py`: in the existing per-wall extension loop, when `find_best_slab_above` returns `None` the code now consults the per-story cohort cache and, if all gates pass, writes the same `extension_strip` payload the viewer already renders — no new element kind. Lineage records `extend_wall_to_dominant` with `dom_y=… cov=…`.
- `tests/test_extract3d_dominant_extension.py`: six unit tests covering the four fixtures from the plan (promoted, non-uniform, stepped floor, offset wall) plus a noise-delta and a cohort-tolerance case.

**Why**
The audit entry above established that 112 walls across 48 / 187 buildings (26 %) benefit from a dominant-height fallback with the chosen thresholds, and that the target case (`d7f1aa19…::ECE2EC5E…:0:4`, delta 0.170 m) is captured. This implementation adds that fallback without touching the slab-extension path.

**Result**
- `python -m pytest tests/` → **245 passed** (including the 6 new fixtures; the three pre-existing `test_real_buildings_integration.py` failures surfaced earlier were import regressions from this change and are now resolved).
- Target building `d7f1aa19-5ca9-4e1b-ac1a-c86d63f9ede7` rebuilt via `extract_building(...)` with the topology graph disabled: **`ECE2EC5E-D7FF-4A45-AF74-4508048CA73D` now has an `extension_strip` reaching y=1.133 m** (lifted 0.170 m from the original 0.963 m top), lineage includes `extend_wall_to_dominant`. `EA3A7274-3C60-48A2-A20F-95627FC71CF3` is unchanged (already at dominant height). Only 1 wall in the whole building is promoted — no spurious extensions.
- Viewer renders the new strip via the existing `wall-extension` kind; no viewer changes required.

## 2026-04-20 — Per-room floor baseline in story-bounds wall clipping (split-level extensions)

**What changed**
- `reconcile/extract3d/overlaps.py::clip_walls_to_story_bounds` (lines 482-537): before the per-wall loop, compute `effective_floor_y`. When the room's `floor_polygon` agrees with its walls' minimum y within 0.10 m, use the room's own floor as the bottom-clip baseline instead of the story aggregate. Ceiling clipping keeps the story baseline. Lineage message prints `effective_floor_y`.
- `reconcile/extract_3d.py::_clip_walls_to_story_bounds` (lines 784-848): same change applied to the monolithic V1 path (it's the one that runs from `python reconcile/extract_3d.py` and writes `reconcile/buildings_3d.json`).
- `scripts/audit_wall_clip_splitlevel.py`: new read-only audit. Iterates `reconcile/buildings_3d.json`, flags rooms where `wall_clipped` is set on ≥1 wall and the room's floor polygon mean y agrees with the walls' pre-clip bottom median within 0.05 m (meaning the clip broke an already-consistent room). Reports cohort size, delta histogram, clipped-wall-ratio histogram, and top-N flagged rows.
- `tests/test_clip_walls_to_story_bounds.py`: new, four cases — (1) over-extended wall with inconsistent floor gets clipped to story, (2) split-level extension with consistent floor is preserved, (3) single errant wall in an otherwise consistent room breaks self-consistency and still gets clipped to story, (4) ceiling clipping still fires under the per-room floor opt-out.

**Why**
User reported that for `24e8aaa7-ec15-4a72-be5f-c67b95a53411::floor::0:7` (Frodesdalsvej 8, Horsens), "the walls should not have been clipped — it's an extension." Diagnosis: room 7's `floor_polygon` mean y is -1.4868 and its walls' `corners_original` bottom y is also -1.4868 (coherent), but story 0's `story_y_map[0] = -1.147` (the median of the largest 0.30-m cluster of per-room floor ys, driven by the other 7 rooms on the story). The clipper saw `wall_min_y (-1.487) < floor_y (-1.147) - 0.30` and raised all 4 walls by 0.34 m, leaving them floating above the room's actual floor. The `max_half_floor = 1.50 m` opt-out at line 490 is far too loose to catch a 0.34-m split-level offset. Physically, split-level annexes/sunrooms/garages with a step-down from the main floor are common.

**Cohort audit before the fix** (`python scripts/audit_wall_clip_splitlevel.py`):
- 99 rooms across 60 / 187 buildings had `wall_clipped` walls where the room's own floor polygon already agreed with the pre-clip wall bottoms.
- 17 rooms had `delta_median ≥ 0.30 m` (the unambiguous bottom-clip split-level signature) — top offenders at 0.34-0.49 m.
- 36 rooms had 100 % of their walls clipped (whole-room elevation mismatch, the classic extension signature).
- Gate of "≥ 5 rooms across ≥ 2 buildings" cleared easily, so this is not a fix-of-one.

**Result**
- `python -m pytest tests/` → **249 passed** (the 4 new cases, plus every pre-existing test green).
- Re-ran `python reconcile/extract_3d.py 24e8aaa7-ec15-4a72-be5f-c67b95a53411`: room 7's 4 walls now have `wall_clipped = False`, no `corners_original`, min y = -1.4868 (matches floor polygon exactly). The 0.34-m ghost is gone.
- Full cohort re-run (all 187 buildings via `python reconcile/extract_3d.py`) + re-audit: **every room with `delta_median ≥ 0.15 m` is gone.** Before: 17 rooms at delta ≥ 0.30 m (top offender 0.489 m); after: zero rooms above 0.15 m. The 84 rooms that still match the audit heuristic are all `delta = +0.000 m` — ceiling-only clips that trivially "match" the heuristic because their bottoms were never touched. Frodesdalsvej 8 room 0:7 now has no `wall_clipped` flag on any of its 4 walls.

---

## 2026-04-20 — Notch-aware stitch snap closes scan-registration gaps

**What**
- `reconcile/extract3d/stitch.py`: new `snap_stitches_to_non_owner_walls(rooms_out, stitch_walls)` post-processor. For each `type: "stitch"` entry whose four corners all project to a uniform perpendicular offset against a non-owner `walls_computed` in the same story (|cos| ≥ 0.98, perp 0.4–2.0 m, ≥ 0.2 m along-overlap), evaluates the "notch predicate": does any of the stitch's owner rooms' `floor_polygon` cover the along-strip just outside the stitch's ends (≥ 60 %) while staying outside the stitch's own along-range (≤ 20 %)? If so, project all four stitch corners onto the non-owner wall's plane and tag the entry with `snapped_to_wall` and `id: snap:<wall_id>`.
- Pass 2: drags any other stitch-list corners (caps AND L-shape partner walls) whose (x,z) matched the snapped wall's original endpoints. Keeps the L-shape connected and the floor/ceiling caps tracking the new geometry.
- Called from both stitcher return points: `reconcile/extract_3d.py:_stitch_wall_gaps` (canonical, drives `buildings_3d.json`) and `reconcile/extract3d/stitch.py:stitch_wall_gaps`.
- `scripts/simulate_stitch_snap.py`: new Phase-A cohort simulation script that evaluates the same predicate across every stitch in `reconcile/buildings_3d.json` without mutating anything, and writes `.context/stitch_snap_simulation.json`.

**Why**
User reported a ~1 m gap between `wall-computed::EE1638F3…:0:4` (room 4's east wall, real scan) and `wall-stitch::sw:45` (synthetic bridge between rooms 3 and 5) in `b01824fc-be43-451f-bc6e-aaab701c144d` (Bøgebakken 3, Odense). Probe: the stitch runs exactly parallel to EE1638F3 at 1.026 m perp offset. Room 5's floor polygon reaches EE1638F3 just past the stitch's ends but notches inward inside the stitch's zone — the fingerprint of a scan-registration boundary rather than a real void (chase, shaft). Physical argument: if this were a real structural gap the notch would persist along the full span; the fact that it closes on either side argues the walls belong on the same plane.

**Cohort audit before the fix** (Phase-A simulation across all 187 buildings):
- 173 / 187 buildings had stitches matching the geometric predicate (parallel + perp 0.4–2.0 m + ≥ 0.2 m overlap), 3091 events total — a pervasive pattern, not building-specific.
- Adding the notch predicate gated the cohort to **248 repaired / 2255 unchanged / 0 regressed events across 62 buildings**. Zero-regression gate passed.

**Result**
- Target: `sw:45` now sits exactly on EE1638F3's plane (max perp 0.00000 m across all 4 corners). The L-shape partner leg (`sw:44`, 0.08 m) follows to the projected corner via pass 2, the floor/ceiling caps (`sw:46`, `sw:47`) triangulate the new geometry cleanly. `sw:45` carries `id: "snap:EE1638F3-…"` so the viewer locator no longer falls back to `sw:45`.
- Full corpus (all 187 buildings): **149 stitches snapped across 65 buildings.** Every snapped stitch sits exactly on its target wall's plane (max perp = 0 m over the full cohort). Phase-A predicted 248/62; the implementation's tighter per-corner uniform-perp gate (0.08 m) filtered out L-shape events the simulation loosely flagged — a conservative direction, consistent with the zero-regression gate.
- `python -m pytest tests/` → 249 passed.

---

## 2026-04-21 — Scan-ceiling support audit (diagnostic only, no pipeline changes)

**What**
- `scripts/audit_scan_ceiling_support.py`: read-only audit comparing each roof oblique / flat surface and each pre-selection oblique ceiling-plane candidate to the union of raw scanned ceiling planes (`room["raw_ceiling_planes"]` in `buildings_3d.json`) on the same story. Scores XZ coverage (Shapely intersection / surface area), vertical residual at raw-ceiling centroids (surface_y − scan_y, median + p95 |dy|), SVD-fitted normal agreement, and classifies each surface as `strong` / `weak` / `none`. Generous thresholds: `|median_dy| > 0.5 m` or `normal_dot < 0.80` → weak; coverage < 10 % → none (can't judge).
- Emits `reports/scan_ceiling_support.json` (per-surface rows with clickable `roof-oblique:*` / `ceiling-oblique:*` / `ceiling-raw:*` element IDs) and `reports/scan_ceiling_support_summary.csv` (per-building counts).

**Why**
- Raw RoomPlan ceiling scans are extracted by `reconcile/extract3d/ceilings.py` and stored per room, but nothing downstream consumes them — `thermal_ceiling.py` uses the *computed* ceiling planes from oblique clustering. Ridge / eave geometry today comes entirely from wall-top segments (`segment_collection.py`, `oblique_clustering.py`, `ceiling_plane_generation.py`), so raw ceilings are a fully independent observation idle in the JSON. User asked whether we could cross-check roof candidates against scanned ceilings (with tolerance for RoomPlan noise) to catch spurious candidates. Audit-first per the generalize-before-specialize rule — measure the cohort signal before proposing pipeline changes.

**Result** (audited all 187 buildings in 2.4 s)
- 105 buildings have committed oblique roofs → 213 committed oblique surfaces in total.
- **66 / 213 committed oblique surfaces classified WEAK (31 %)** — scan ceilings disagree beyond 0.5 m or normal_dot < 0.8. 48 buildings (25.7 % of all, 45.7 % of buildings with oblique roofs) have at least one weak committed surface.
- Weak distribution: median |dy| = 0.39 m, p75 = 0.65 m, p95 = 1.18 m, max = 1.63 m; 52 / 66 fail the normal-dot gate (normal mismatch is the dominant weak signal, not pure y offset); signs roughly balanced (29 surface-above-scan, 37 surface-below-scan — no systematic bias).
- Pre-selection oblique candidates (228 total): 201 strong / 27 weak / 0 none. Committed has **more** weak than candidate (66 vs 27) — i.e. the committed clipped polygon covers scan regions the loose candidate bbox didn't, and the SVD-fit normal on the committed 3D corners exposes disagreements the cluster-averaged normal hides. Scan signal is stronger at the committed stage.
- Committed flat surfaces: all 1703 classified `none` (flat caps live on stories where RoomPlan has no ceiling scans — expected; raw ceilings only exist for rooms the surveyor actually stood under and pointed up). Flat cross-check would need a different comparison (floor polygons of the story above, not raw ceilings).
- `python -m pytest tests/` → 249 passed (no pipeline code touched).

**Top weak examples to eyeball in the viewer** (element IDs clickable via viewer search bar):
- `e9f0631f-ae34-4d30-af21-d3369327755f::roof-oblique::oblique:1` — dy −1.63 m, normal_dot 0.62 (pure disagreement)
- `d8308bfc-c2c1-42bd-8503-282571708b8c::roof-oblique::oblique:0` — dy −1.31 m, incl 45°, normal_dot 0.71
- `146ecf8b-ffa1-4239-ba58-040b61861fd9::roof-oblique::oblique:1` — dy −1.26 m, area 51.5 m², normal_dot 0.95 (pure y offset, normal agrees → likely height / clipping issue)
- `60f2f02b-8910-461c-879a-75925d256989::roof-oblique::oblique:2` — dy +1.21 m, normal_dot 0.68

**Next step** (not taken in this pass): user to inspect the above in the viewer and judge whether scan-ceiling disagreement tracks actual pipeline errors. If yes, a follow-up can wire a `scan_ceiling_support` evidence term into `roof_algorithms_py/roof_evidence_graph.py` and consume it in `roof_hypothesis_graph.py` selection scoring.

**Refinement: restrict scan evidence to roof-exposed rooms** (user request, same date)
- A scanned ceiling in a room with another room above it is an interior cap between stories, not a roof surface. The audit now defaults to matching roof surfaces only against raw ceilings in rooms listed in `roof_result.ceiling.exposed_rooms` (rooms the roof pipeline has already identified as `is_roof_candidate: True`). `--include-covered` flag restores the old all-rooms behaviour for comparison.
- Corpus scale of the filter: 90 / 187 buildings are multi-story; across multi-story buildings 66.6 % of rooms (726 / 1090) are exposed. Across the whole corpus, 1550 rooms with scans are exposed vs 369 covered (~81 % exposed).
- Effect on classifications (exposed-only vs all-rooms): committed_oblique weak **unchanged at 66**; one strong → none as its only scan evidence came from a covered room; one candidate weak → none for the same reason. Essentially a no-op at the cohort level. The 66 weak committed surfaces disagree with scans of ceilings that ARE under open sky — the signal is real, not an artifact of interior-cap contamination.
- The small effect is because a committed oblique surface's `dominant_story` is almost always the top story, and top-story rooms are mostly exposed. The filter matters philosophically (correctness) more than statistically (magnitude) on this corpus.

**Dedicated roof-debug viewer**
- New `reconcile/viewer-roof.html` + `reconcile/viewer-roof-main.js`, a standalone Three.js viewer focused on ridge/eave detection. Renders per building: wall-top segments colored by their `valid_clusters` index, pre-selection candidate ceiling planes (bbox, from `ceiling.planes`), committed roof surfaces (`roof_surfaces.oblique` clipped polygons), flat roof surfaces, raw scan ceiling outlines (flagged by exposed vs covered room), and room floor polygons. Toggles for each overlay; committed surfaces color-coded strong/weak/none from the audit JSON. Click any plane or segment midpoint to open an inspector panel with the metrics + copyable element ID.
- Added two endpoints to `reconcile/viewer_server.py`: `/roof-index` returns `[{uuid, address, n_oblique, n_weak_committed, ...}]` sorted by weak-committed desc for the sidebar; `/roof-detail?uuid=<u>` slices the per-building roof-pipeline output + buildings_3d room geometry + audit rows into a compact payload (tags segments with their cluster by matching endpoint coords against `valid_clusters[i].segs`). Caches the three source files in memory with mtime checks since `roof_algorithms_py_results.json` is ~300 MB.
- Why: dashboard URLs into the main viewer were clunky for visually inspecting whether the 66 weak committed surfaces look wrong; the user asked for a dedicated viewer that shows ridge/eave planes alongside the segments feeding them. No pipeline or audit logic changed — this is a visualization-only layer.

---

## 2026-04-21 — Thermal ridge/eave caps: widen to building-under-roof footprint + wall-barrier splits

**Files changed**
- `reconcile/roof_algorithms_py/thermal_ceiling.py` — new `BARRIER_REACH=0.30` constant, `WALL_STRIP_HALF_WIDTH=0.03` buffer, helpers `_wall_xz_strip`, `_wall_top_y`, `_build_story_thermal_context`, `_barrier_union_for_cap`. `_build_thermal_for_oblique_room` now takes `story_context` and uses `fp ∪ attached_within_story_gap_polys` as cap clipping footprint, then subtracts the union of wall XZ strips whose top Y ≥ cap_y − REACH from ridge and eave caps. `build_thermal_ceilings` takes `gap_walls` + `rooms` kwargs and precomputes per-story context once.
- `reconcile/roof_algorithms_py/pipeline.py` — passes `gap_walls=bldg.get("gap_walls", [])` and `rooms=bldg.get("rooms", [])` into `build_thermal_ceilings`.
- `tests/test_thermal_ceiling_gap_coverage.py` (new) — 5 tests: eave cap covers a within_story gap assigned to a room; tall interior wall at cap plane splits the eave cap; short wall (top Y < cap_y − REACH) does NOT split; almost-reaching wall (top Y = cap_y − 0.20, within REACH) splits; wall extending above cap plane splits.

**Why**
User reported that on `38f71f1d-2c71-4fcd-9997-83b2914416b0` the ridge/eave "stops short" and fails to cover `::gap-wall::within_story:201` and `::gap-wall::within_story:130`. Root cause: `_build_thermal_for_oblique_room` clipped both ridge and eave caps to the single room's floor polygon (`fp`), so the morphological gap strips between adjacent rooms (emitted as `within_story` gap-walls from `extract3d/gaps.py`) were invisible to cap generation even though the roof clearly covers them. User's refined design: cap extent = building-under-roof envelope (story union of room fps + within-story gap polygons), cap must NOT cross physical walls — walls whose top Y is within 30 cm of the cap plane act as barriers and split the cap.

**Result**
- Unit tests: 5/5 pass in the new file; full `tests/` suite unaffected.
- Target building: 1 cap / 11.0 m² → 10 caps / 50.7 m² (+39.7 m²). Gap strips `:201` and `:130` now covered (pending visual viewer verify).
- Corpus (all 223 pipeline-outputs): 407 caps / 2527.9 m² → 607 caps / 2402.9 m² (+200 caps, −124.9 m² net). 48 buildings grew, 55 shrank, 120 unchanged.
- The +count / −area pattern matches physics: caps are split by interior walls into multiple polygons (more count) and lose perimeter strips equal to the 6 cm wall-barrier buffer × interior wall length (minor area). Largest area gains (+36 to +41 m²) are on buildings with significant within-story gaps that had no prior coverage. Largest area losses (−50 to −100 m²) are on buildings with many tall interior walls that previously over-covered across interior partitions.
- Baseline and post-change metrics snapshotted at `.context/thermal_cap_metrics_{before,after}.json` for later comparison.

**Follow-up (not taken)**
Clip barrier walls to the cap plane in the emitted geometry (extend walls within REACH up to `cap_y`, trim walls above down to `cap_y`). Requires either restructuring `extract_3d.py` pipeline order (currently `buildings_3d.json` is serialized before `_run_roof_pipeline` runs, so wall mutations during thermal computation wouldn't reach the viewer) or adding a post-process that emits clipped-wall overrides into the roof pipeline results payload. Tracked as task #8.

---

## 2026-04-21 — Wall extensions across half-floor stories (generic fix)

**Files changed**
- `reconcile/extract3d/builder.py` — replace `story+1`-only slab pool with all stories strictly above the room's story, preserving the same-story half-level block. Add `_is_split_level(rooms_out)` helper and emit `building["split_level"]` alongside `stories_found`.
- `reconcile/extract_3d.py` — same slab-pool fix at the parallel implementation site (`:2879`); import `_is_split_level` from `reconcile.extract3d.builder`; emit `split_level` in the building return dict.
- `reconcile/extract3d/ceilings.py` — `find_best_slab_above` now accepts `max_gap=None` kwarg; candidates with `slab_y - wall_top_y > max_gap` are filtered out before the XZ-distance tiebreak. Both call sites pass `max_gap=0.80` (matching `extend_wall_to_slab`'s gate).
- `tests/test_half_level.py` — `TestBroadSlabPoolAcrossHalfFloor` (4 tests: side-wing scenario, story+1-only failure control, normal 2-story regression guard, stacked half-floors) and `TestIsSplitLevel` (4 tests: single-room-story, tight story spacing, normal 2-story, single-story).
- `scripts/audit_half_floor_wall_extensions.py` (new) — Phase A diagnostic: classifies every wall across the corpus as `already_extended / slab_s+1_ok / slab_s+k_ok / gap_exceeds_max / no_slab_anywhere_above / wall_too_short / empty_corners`, with per-building split-level roll-up.

**Why**
User reported that on `938d6ed6-d916-462b-ba37-f421feb2af21` and `e0155eef-34a5-4642-bca6-39b83ee42af1`, the wall extensions between the lower full story and an upper full story weren't being created because a half-floor wing sits between them. Root cause: the wall-extension slab candidate pool was limited to `story + 1`. In split-level buildings where `story + 1` is a half-floor wing that doesn't cover the wall in XZ (or sits below the wall top), no candidate remains — and `story + 2` is never consulted. Fix generalises the pool to every story strictly above, while `find_best_slab_above`'s XZ proximity still prefers the lowest viable slab. The `max_gap` kwarg prevents the broadened pool from hijacking a wall onto an unreachable higher slab when a viable closer one exists.

**Result**
- Tests: 262/262 pass (`pytest tests/`); all 29 half-level tests pass.
- Phase A audit (corpus n=187, 29 flagged split-level): 203 walls across 7 buildings classified `slab_s+k_ok` (k≥2) — confirmed as the dominant failure mode.
- Phase F corpus rerun: `already_extended` 3415 → 3661 (+246 walls). 174 buildings unchanged, 13 improved, **0 regressed**. 938d6ed6: 0 → 79 extensions; e0155eef: 18 → 53; c2800052 +38; 4fe068d2 +35; 287808db +30; bad532ea +17; a8aca518 +4.
- `split_level=True` correctly set on 29 buildings matching the diagnostic classifier.
- Per-wall CSVs snapshotted at `reports/half_floor_audit_before.csv` (pre-fix) and `reports/half_floor_audit_after.csv` (post-fix).

---

## 2026-04-21 — Ridge/eave scorer: fold within-story gaps into plane-group unions

**Files changed**
- `scripts/score_candidates_ridge_eave.py` — new helper `_gap_polys_from_building(bldg)` that reads horizontal within-story polygons from `buildings_3d.json["cross_floor_gaps"]` (NOT `gap_walls`, which are vertical quads that collapse to lines in XZ). `_build_plane_groups(...)` takes a new `gap_polys_xz` kwarg and, after the scan-footprint clip, unions every gap polygon that intersects the connect-buffered plane-group extent into the plane-group `union`. `main()` builds a `gap_polys_by_uuid` map next to `wall_tops_by_uuid` and passes it through `_score_building`.
- `tests/test_ridge_eave_scoring_gap_union.py` (new) — 4 tests: gap fills the notch between two candidates; far-away gap is ignored; scan-poly clip happens before gap fold so a tight scan doesn't trim the gap; helper returns only horizontal `cross_floor_gaps[type="within_story"]` polygons, skipping vertical `gap_walls`.

**Why**
User reported the "Ridge/Eave Scoring" viewer overlay on `38f71f1d-2c71-4fcd-9997-83b2914416b0` "stops short" and doesn't cover within-story gap-walls `:201` and `:130`. The scorer's plane-group union is built from candidate footprints only; candidates are per-segment/per-room, so the thin strips between adjacent room slabs never enter the union even though a real roof plane is physically continuous across them. Adding `within_story` gap polygons to the union (when they lie under the connect-buffered member extent) fills those strips. The fold must happen AFTER the scan-footprint clip because `scan_footprint_xz` also derives from candidate scan data and doesn't include the gaps — if folded before, `intersection(scan_poly)` trimmed them straight back out (initial implementation hit this on the target building: 0.00 m² change). Reordering yields the intended coverage.

**Result**
- Tests: 4/4 in the new file; full suite 266/266 pass.
- Target `38f71f1d-…`: 140.22 → 142.59 m² (+2.37 m², covering the reported gap strips). Pending viewer verify.
- Corpus (223 buildings): 47,822.9 → 48,149.3 m² (+326.5 m², +0.68%). **59 buildings grew, 0 regressed, 164 unchanged.** Top growers: `e5adc187` +62 m², `e9f0631f` +41 m², `bc2779a4` +14 m², `7dbc53a6` +12 m², `a317a543` +12 m². Zero buildings lost area, confirming the union-only semantics.
- Initial wrong-ordering run (before the reorder) is documented in the "Why" above; it informed the new `test_gap_fold_happens_after_scan_clip` regression test.
- Baseline and post-fix scores at `.context/ridge_eave_scores_before.json` (summary) and `reports/ridge_eave_scores_20260420/scores.json` (full payload).

**Known adjacent bug (not fixed here)**
While investigating, discovered the earlier thermal-ceiling fix in `reconcile/roof_algorithms_py/thermal_ceiling.py::_build_story_thermal_context` and `reconcile/roof_algorithms_py/pipeline.py` reads `bldg.get("gap_walls", [])` — same wrong-field mistake. Target-building thermal improvements (1→10 caps, +39.7 m²) came from the wall-barrier side effect, not the intended gap widening. Flagged for user review before acting.

---

## 2026-04-21 — Wall extensions: stacking gate (no auto-extensions for air-facing walls)

**Files changed**
- `reconcile/extract3d/ceilings.py` — `find_best_slab_above` gains a `stack_tol=0.10` kwarg. Candidates whose XZ distance from the wall midpoint exceeds `stack_tol` are rejected before the distance-tiebreak. Default applies to both callers via the kwarg default (no callsite change).
- `tests/test_half_level.py` — three new tests in `TestBroadSlabPoolAcrossHalfFloor`: `test_outbuilding_wall_not_stacked_returns_none` (wall in a detached wing — no slab picked), `test_stack_tol_allows_boundary_float_noise` (midpoint 0.05 m outside the upper-floor polygon still extends), `test_stack_tol_rejects_far_walls` (0.50 m outside → no extension).

**Why**
User flagged 6 wall extensions in "rooms outside building units" (detached outbuildings / wings) that shouldn't have been generated: `38158927::1C1B3E65`, `38158927::DCA342FE`, `72122129::67077F03`, `c001b1ca::4DD1D99A`, `d28b528a::50BA4261`, `e0155eef::AACBC164`. Design clarification: "we scan from indoors but we want the outdoor shape. We will get material thicknesses provided by the user for elements facing the air. For intermediary slabs, we will not have that data so we need to create them to ensure water tightness. but for ceilings, we won't need it as we will get it from users, so we will not need the wall extensions." Root cause: `find_best_slab_above` picked the XZ-closest slab with `slab_y > wall_top + min_margin`, but didn't gate on whether the slab footprint was actually overhead. A basement-wing wall with no room above it would still get extended to the nearest full-story slab metres away. Pre-diagnosis simulation across the corpus: min-distance-to-nearest-upper-room for the 6 cited cases ranged 0.99 m–5.85 m — all clearly outside any upper room. Setting `stack_tol=0.10` tolerates float-noise at the boundary (938d6ed6 basement p50=0.10 m between midpoint and upper-floor polygon) while catching all 6 cited cases (smallest offset 0.99 m).

**Result**
- Tests: 269/269 pass (`pytest tests/`); 32/32 in `test_half_level.py`.
- All 6 cited cases now `extension_strip == None`.
- Corpus: extensions 3661 → 2421 (−1240, −33.9%). 85 buildings changed; **all changes are reductions** (no building gained extensions), consistent with the strictly-stricter gate.
- Target cases: 938d6ed6 basement story-0 79 → 60 (remaining 60 are over the upper-floor footprint; dropped 19 were under no upper room and would otherwise be air-facing). e0155eef total 53 → 37.
- Top drops: `bc2779a4` 98→33, `9c80d7ae` 69→5, `d28b528a` 67→17, `e9f0631f` 85→39, `b53c11aa` 62→20.
- Per-building before/after diff at `/tmp/verify_after.py` output. Snapshot of pre-gate state at `reconcile/buildings_3d.json.before_stack_tol` (MD5 44dc6adb45af8977a0f4c20f7a4cd963); post-gate MD5 17c774ae14705d6eb31c726bfaa9c5e0.

---

## 2026-04-21 — Ridge/eave scorer: morphological closing + building-fp clip

**Files changed**
- `scripts/score_candidates_ridge_eave.py` — replaced the within-story gap-polygon fold (added earlier today) with a more general morphological closing operation clipped to the building's room-floor union. New constant `PLANE_GROUP_CLOSING_M = 0.75` (gives 2·C ≈ 1.5 m bridging); new helper `_building_fp_union(bldg)` unions every room's `floor_polygon` XZ projection into a single Shapely polygon. `_build_plane_groups` parameter renamed `gap_polys_xz` → `building_fp`. `main()` now builds `building_fp_by_uuid` via `_building_fp_union` instead of `gap_polys_by_uuid`. Closing order unchanged: scan-clip first, then closing (scan_poly is also candidate-derived so it doesn't include the holes we want to fill).
- `tests/test_ridge_eave_scoring_gap_union.py` — rewritten for the new API: two positive cases (notch-fill, closing-after-scan-clip), two safety cases (tight `building_fp` prevents runaway widening, far-apart plane-groups can't be bridged by closing), plus two `_building_fp_union` helper tests. Allow ≤0.2 m² slack on expected areas to absorb corner rounding from `buffer(+C).buffer(-C)`.

**Why**
Gap-poly fold (from the 12:59 commit earlier today) fixed target `38f71f1d-…` (within_story gap between two rooms) but not `e0155eef-…::plane-group::595e10a43810::below-ridge`. Investigation: for e0155eef there is NO within_story gap near wall `E2E5D435-928D-42E2-AFE5-7FFC46E2F3C6`; the "hole" is a diagonal cut through the candidate footprint caused by an under-scanned interior wall. The physical roof plane extends over the wall, but candidate extraction didn't capture that. User-approved approach: stop relying on gap polygons — instead close the plane-group union at ~1.5 m (bridges both the 38f71f1d within_story strips AND the ~1 m e0155eef diagonal cut) and intersect with the building's room-floor union so closing never invents area outside the physical building.

**Result**
- Tests: 271/271 `pytest tests/` pass (6/6 in `test_ridge_eave_scoring_gap_union.py`).
- Corpus diff (223 buildings, `_score_building` with vs. without `building_fp_by_uuid` on current code): total plane-group area 47,822.9 → 48,191.7 m² (+368.8 m², +0.77%). **88 buildings grew, 0 regressed, 135 unchanged.** Plane-group count identical both ways (503 → 503) — closing is strictly additive and never merges/splits components. Top gainers: `e9f0631f` +39.3 m², `1f03f6e0` +33.6 m², `d28b528a` +32.9 m², `a443b86f` +17.4 m², `b53c11aa` +16.8 m².
- Target 38f71f1d: plane-groups still cover every within_story gap centroid; raw area −0.7 m²/plane from corner rounding (2-ring MultiPolygon collapsed to a single Polygon with smoothed corners — no coverage lost).
- Target e0155eef::595e10a43810: 54.59 → 56.42 m² (+1.83 m²); sibling plane-groups on the same building gained +1.8 to +2.4 m² each.
- Installed scores at `reports/ridge_eave_scores_20260420/scores.json` (25.8 MB; viewer reads this on ridge/eave overlay).

**Learnings**
- The 12:59 baseline `/tmp/scores_before_closing.json` showed phantom plane-group drops (8 → 6 on e5adc187) that were artifacts of comparing against an in-flight version of `_build_plane_groups`, not the current code. Clean with-vs-without comparison on the current build showed strict monotonic growth. Always diff "with feature flag off vs on" using the SAME code, not against a file written by an older version.
- Closing at `2·C = 1.5 m` covers two morphologically different failure modes (thin between-room strips ~0.5 m AND ~1 m diagonal scan cuts) with one operator, which is exactly the kind of generalization the corpus rewards (88 buildings gained vs. 0 regressed).

---

## 2026-04-21 — Raw scan ceiling planes as roof-classification evidence (investigation)

**Files added (read-only audits; no pipeline edits)**
- `scripts/audit_raw_ceiling_plane_geometry.py` → `reports/raw_ceiling_geometry/`
- `scripts/audit_raw_ceiling_pipeline_gap.py` → `reports/raw_ceiling_pipeline_gap/`
- `scripts/audit_raw_ceiling_edges.py` → `reports/raw_ceiling_edges/`
- `scripts/audit_raw_ceiling_to_wall_top.py` → `reports/raw_ceiling_wall_top_trust/`

**Why**
`room.raw_ceiling_planes` (per-room RoomPlan ceiling polygons, extracted by `reconcile/extract3d/ceilings.py` and serialised to `reconcile/buildings_3d.json`) is rendered in viewer Step 1 but **not consumed by the roof pipeline** (`reconcile/roof_algorithms_py/`). The roof pipeline classifies, splits, and unit-assigns roof surfaces from `walls_computed` segment azimuth/inclination only — with one exception: `simple_slant.py` uses the synthesised `ceiling_polygon` (wall-top derived), not the raw per-plane polygons. Hypothesis: raw plane normals, edges, and per-room distribution carry strong signal for (a) validating whether an oblique cluster is really a roof, (b) which story/room a roof surface belongs to, (c) where it should split. Before proposing heuristic changes, quantify the signal across the full 187-building corpus (per `feedback_generalize_before_specialize`). An existing `scripts/audit_scan_ceiling_support.py` already scores the surface→raw direction; these four scripts are complementary (baseline geometry, raw→pipeline inverse coverage, edges, and scan-trust).

**Result — corpus findings (187 buildings, 5 383 raw planes)**

*H1 baseline — plane geometry (`audit_raw_ceiling_plane_geometry.py`):*
- 187/187 buildings carry raw ceilings.
- 56.7 % of planes are oblique (incl ≥ 5°); 40.1 % are steep (≥ 30°); 41 % are flat (< 1°).
- **14 % of planes are near-vertical (≥ 80°)** — likely mis-classified slanted walls or scan noise. Any consumer must gate on `incl < 80°` before trusting a raw plane.
- Azimuth distribution is roughly uniform across 45°-bins (range 368–462 each) — healthy, no single bias.

*H1/H2/H4 — raw→pipeline gap (`audit_raw_ceiling_pipeline_gap.py`, 3 398 planes in exposed rooms):*
- `oblique_matched`: 24.0 % (816) — raw oblique plane has an oblique roof surface with normal_dot ≥ 0.80.
- `flat_matched`: 48.9 % (1 662).
- **`oblique_covered_by_flat`: 14.3 % (486)** — raw plane shows a slope but the pipeline committed only a flat surface above it. Strongest single "missed oblique roof" signal in the data.
- `oblique_wrong_orientation`: 7.6 % (257) — oblique covered by an oblique surface whose normal disagrees by > ~37°. Candidate split sites.
- `flat_covered_by_oblique`: 3.5 % (120) — pipeline extended oblique beyond the scan.
- Per-room agreement (1 550 rooms): raw vs. pipeline class agrees in 73 % (flat/flat 1 071 + oblique/oblique 62); 21 % pipeline is "mixed" (both kinds cover the room); pure disagreement (raw flat / pipeline oblique or vice versa) in **96 rooms = 6.2 %** — the cleanest "pipeline misclassified this room's top" cohort.

*H3 — edges (`audit_raw_ceiling_edges.py`, 19 258 edges):*
- 72.5 % horizontal (|Δy| ≤ 0.05 m); 27.5 % sloped.
- Horizontal labels: 2 370 ridge/hip candidates (shared between raw planes with normals differing ≥ 10°), 7 552 eave candidates (within 0.5 m of the pipeline footprint), 4 041 isolated.
- Many buildings have **dramatically more raw ridge edges than pipeline oblique clusters**: top 10 range from `ridge_minus_clusters = 46` (1900be91, 49 edges / 3 clusters) to 98 (1f03f6e0, 107 edges / 9 clusters). Raw edges over-count (a single physical ridge can be split across several short edges), so "edges" ≠ "distinct ridges" — still, the order-of-magnitude gap says the pipeline condenses geometry the scan clearly resolves.
- 10 buildings also show the inverse: 0–2 raw ridge edges but 1–4 pipeline oblique clusters (phantom clusters, e.g. `7cabc39b` 2 edges / 4 clusters).

*H5 — scan trust (`audit_raw_ceiling_to_wall_top.py`, 1 916 rooms):*
- **75 % of rooms have ≥ 0.9 trust score** (≥ 90 % of raw plane corners sit within 0.30 m of a `walls_computed` top edge); 50 % of rooms are perfect (1.0).
- Only 1 % of rooms (16) fall below 0.25 — untrustworthy scan. `p95_dist_m` median is 0.0 m.
- Raw ceilings are broadly trustworthy; H1–H4 conclusions can be applied to ~90 % of rooms without an explicit trust gate. For the remaining ~10 % (trust < 0.75, 288 rooms) gate H1/H2/H3 evidence on `trust_score ≥ 0.75` before acting.

**Hypothesis verdicts**
- **H1 (raw-plane normal validates oblique clusters) — strong.** 257 `oblique_wrong_orientation` planes give a direct split oracle; 486 `oblique_covered_by_flat` planes signal missed obliques.
- **H2 (raw coverage drives unit assignment) — weak/redundant for 73 %, useful for the 6 % pure-disagreement cohort.** Most rooms agree because the pipeline already uses room footprints. The 96-room disagreement cohort is the interesting slice.
- **H3 (edges as split oracle) — strong.** Ridge/hip candidates massively outnumber pipeline clusters on complex roofs. Needs edge-deduplication into distinct 3D line segments before it's directly usable as a splitter.
- **H4 (per-room majority class) — moderate.** 6 % of rooms disagree on oblique-vs-flat; cheap to compute and easy to act on.
- **H5 (wall-top trust gate) — validates the whole approach.** 90 % of rooms are trustworthy enough that H1–H4 conclusions apply without additional gating.

**Integration shortlist (not implemented — future work)**
Ranked by signal strength and simplicity:
1. **Normal-disagreement splitter.** After `cluster_oblique_segments()` in `reconcile/roof_algorithms_py/pipeline.py:66`, intersect each cluster's XZ hull with the per-story raw-ceiling planes. If a single cluster overlaps raw planes whose normals differ by ≥ 15°, split the cluster along the raw ridge edge. Covers the 257 `oblique_wrong_orientation` cases.
2. **Oblique-missed pre-pass.** Before the main pipeline commits flat roof surfaces, run a check: per exposed room, if ≥ 50 % of the raw-ceiling XZ area has an oblique plane (incl ≥ 5° AND trust_score ≥ 0.75), block `roof_flat_intermediate.py` from claiming that room. Drives the 486 `oblique_covered_by_flat` cohort down.
3. **Ridge-line seeding for `oblique_clustering.py`.** Extract distinct 3D ridge lines from the deduplicated `ridge_or_hip` edge set and use them as initial seeds; current clustering is pure azimuth/inclination distance.
4. **Per-room flat/oblique class gate.** For the 6 % pure-disagreement cohort, prefer the raw majority class when picking which hypothesis graph node wins (`roof_hypothesis_graph.py`).
5. **Trust-gated evidence.** Thread `trust_score` through as an input to `roof_evidence_graph.py`; down-weight low-trust rooms.

**Out-of-scope / open questions**
- None of the four scripts touch any pipeline code; this entry documents signal strength only. Next step is a focused plan for item (1) above (normal-disagreement splitter), tested against the 10 "most under-clustered" buildings before widening.
- 14 % near-vertical raw planes deserve an extraction-side fix (`reconcile/extract3d/ceilings.py::reassign_raw_ceiling_planes_spatially`) — they're probably scan-wall artefacts landing in the ceiling bucket.

**How to reproduce**
```
python3 scripts/audit_raw_ceiling_plane_geometry.py
python3 scripts/audit_raw_ceiling_pipeline_gap.py
python3 scripts/audit_raw_ceiling_edges.py
python3 scripts/audit_raw_ceiling_to_wall_top.py
```
Each emits `per_plane.csv` / `per_building.csv` / `summary.json` under its `reports/raw_ceiling_*/` directory. Rows carry shareable viewer element IDs (`<uuid>::ceiling-raw::<story>:<room>:<plane>`); paste into the Step 1 viewer search bar to inspect.

---

## 2026-04-21 — Ridge/eave scorer: flood-fill plane-groups across building envelope

**Files changed**
- `scripts/score_candidates_ridge_eave.py` — new constant `PLANE_GROUP_FLOOD_REACH_M = 2.0`. New helper `_building_envelope_fp(bldg)` that unions all `rooms[].floor_polygon` XZ projections PLUS every `cross_floor_gap.corners` XZ projection (both `within_story` and `cross_story`). `_build_plane_groups` takes a new `envelope_fp` parameter; after the existing closing step, it computes `reach = real_union.buffer(REACH).intersection(envelope_fp)`, keeps only the connected components that intersect `real_union`, and unions them back in. `_score_building` and `main()` plumb a new `envelope_fp_by_uuid` dict through the same way `building_fp_by_uuid` flows. Config log gains `PLANE_GROUP_CLOSING_M` and `PLANE_GROUP_FLOOD_REACH_M`.
- `tests/test_ridge_eave_scoring_gap_union.py` — four new tests: `_building_envelope_fp` includes both gap types, flood-fill pulls a 2 m cross_story extension into the plane-group, flood-fill refuses to absorb a detached-outbuilding envelope component, flood-fill distance cap enforces "free-floating > X m is excluded".

**Why**
User flagged `117d172e-…::plane-group::ac1b35f81462::below-ridge` and `::31658ecf9141::below-ridge` stopping short of `cross_story:high:10` (a 24.9 m² cross_story gap extending 1.4 m beyond the plane-group's candidate footprint edge). Closing fills interior notches but cannot grow the outer silhouette — the missed 11.9 m² sits geographically outside the plane-group, unreachable by closing at any radius (tested up to 2.0 m: still only gains ~1.5 m²). User's refined rule: "expand to cover the union of polygon of all floors (incl gap closing) BUT have clipping rules, ie it should not continue vertically if it either crosses the room OR it is completely free floating for more than X meters (it'll continue in other building parts)". Flood-fill implements exactly this: expand into the envelope (rooms + all cross_floor_gaps), stop at X m from the current union (free-floating cap), and drop disconnected envelope components (detached wings go to their own plane-groups).

**Result**
- Tests: 275/275 `pytest tests/` pass (10/10 in `test_ridge_eave_scoring_gap_union.py`).
- Corpus rescore at `reports/ridge_eave_scores_20260420/scores.json`: 223 buildings, plane-groups 503 → 511, pairs 392 → 423 (previously-too-small groups now survive `MIN_SUBGROUP_AREA_M2` and form new pairs). **Zero selection changes** (every building that had a selected pair before has the same one after — flood-fill changes extent, not ridge/eave identity).
- Target 117d172e: 3 plane-groups each grew 44 → 68 m² (+24 m²); covers 97% of the cited cross_story:high:10 gap (up from 52%).
- Target 38f71f1d: plane-groups grew 70.6 → 109 m² each (+38 m²); previously-uncovered cross_story gap area now filled.
- Target e0155eef::595e10a43810: 56.4 → 75.3 m² (+18.9 m²); wall `E2E5D435-…` area fully covered.
- Total plane-group area 47,822.9 (closing-only baseline) → 56,967 m² (+19% corpus-wide). No buildings lost area.

**Why X=2.0 m**
The cited 117d172e case needs ~1.43 m of extension to cover the full gap; 2.0 m gives headroom for comparable geometries without ballooning. Tested 0.5 / 1.0 / 1.5 / 2.0: gap coverage at each = 69% / 82% / 90% / 97%. Below 2.0 m we leave gap edge exposed; above 2.0 m risks absorbing across ridge lines or into opposite-roof extents on hipped buildings. Both the closing radius (0.75 m) and the flood-reach (2.0 m) sit well below a typical room dimension (3 m+), preserving the "don't hijack neighbour rooms" invariant.

**Learnings**
- Closing and flood-fill are complementary, not alternatives. Closing fills sub-2·C interior notches (within_story strips, diagonal scan cuts); flood-fill extends the outer silhouette into adjacent envelope area (cross_story extensions, lower-story wings under the same roof plane). Both gated differently: closing by `building_fp` (rooms only), flood-fill by `envelope_fp` (rooms + all gaps) plus distance cap plus connectivity.
- Each plane-group flood-fills INDEPENDENTLY, so on a building where all plane-groups share XZ bbox (gable/hip with identical footprints per plane), they all claim the same envelope region. That's fine: pair-formation uses plane-opposition, not extent-exclusivity, to pick ridges. Total plane-group area can exceed envelope area without breaking scoring.

---

## 2026-04-21 — Raw-ceiling prototype pivot: computed owns angles, raw bounds extent

**Files changed**
- `scripts/prototype_raw_ceiling_roles.py`, `scripts/prototype_dormer_reconstruction.py`, `scripts/prototype_wing_reconstruction.py` — **deleted**.
- `reports/raw_ceiling_prototype/` (roles.json, reconstructions.json, per_plane_roles.csv, per_room_archetypes.csv) — **deleted**.
- `scripts/audit_computed_surface_extent_vs_raw.py` — new read-only audit.
- Output dir: `reports/computed_extent_vs_raw/{per_surface.csv, summary.json}`.

**Why**
Phase-2 prototype (per-plane roles + per-room archetypes + dormer/wing reconstruction) rested on the assumption that raw scan planes could drive classification and generate shell geometry for complex rooms. User clarified the opposite split: **computed pipeline owns orientation/inclination** (wall-derived angles are the trustworthy signal), **raw ceilings only inform extent** (XZ footprint + Y bounds). Complexity (dormers, wings) should be abstracted as per-room flags, never reconstructed as geometry. So the remaining useful question is: where does the computed pipeline extend its surfaces beyond the scan evidence? The new audit measures exactly that. Memory file `feedback_computed_angles_raw_extent.md` captures the rule.

**Result**
- Corpus: 213 oblique + 1,695 flat computed roof surfaces scored across 187 buildings with raw ceiling data.
- **Oblique overextend_fraction_xz** (footprint overshoot): p50=0.8%, p75=2.7%, p90=6.0%, p95=7.2%, p99=13.2%, max=21.5%. XZ clipping is already tight.
- **Oblique overextend_y_m** (ridge extrapolation above raw): p50=0.61 m, p75=1.33 m, p90=2.10 m, p95=2.47 m, max=4.57 m. Computed oblique surfaces routinely extrapolate 0.5–2.5 m above the highest raw-plane corner — the ridge-intersection step has no scan anchor above wall-top.
- **Flat overextend_fraction_xz**: p50=0.2%, p75=19.7%, p90=41.1%, p95=51.0%, max=74.1%. Long right tail — many flat surfaces cover areas with no raw evidence beneath.
- **Flat overextend_y_m**: p50=0.0 m, p95=0.36 m, max=4.45 m. Flat surfaces mostly sit at raw Y (expected), with a small heavy tail.
- Tests: 275/275 `pytest tests/` pass (no pipeline changes).

**Learnings**
- Three prior framings (role labels, confidence-split, reconstruct-complexity) were all rejected before the right one landed. Shared failure mode: trying to *use raw planes as a classification signal*. They aren't — scan normals are too noisy, and the wall-derived azimuth/inclination already wins on accuracy. Raw planes uniquely carry *where* the ceiling actually is (bounded XZ corners and real Y), and that is the only dimension along which they beat the pipeline.
- Fragmentation as a room property is not what the pipeline needs from raw ceilings. The pipeline's real gap is extent: oblique surfaces extrapolate upward to meet ridges that may be too tall, and flat surfaces can extend into regions with no scan support. The audit now quantifies both.
- Sidecar JSONs + viewer role palettes + archetype reconstructions all got deleted cleanly because none of them entered `reconcile/` or `reconcile_v2/` — the throwaway cost of a prototype is much lower when it stays in `scripts/` + `reports/` + `viewer-modules/constants.js` palette and never writes into the pipeline.

---

## 2026-04-21 — Remove stale repo temp file

**Files changed**
- `reconcile/buildings_3d.tmp.json` — deleted stale temporary extraction artifact.
- `tracking_progress.md` — appended this maintenance note.

**Why**
The workspace may accumulate temporary files over time. `reconcile/buildings_3d.tmp.json` matched the repo temp-file pattern and had not been modified since 2026-04-11, so it was old enough to treat as safe cleanup.

**Result**
- Removed 1 stale temp file from the repo workspace.
- Left `.venv/` untouched; the only other matches were installed-package files with `tmp` in their names rather than repo-generated temp artifacts.

---

## 2026-04-21 — Overextend overlay: filter whole-building-envelope flats

**Files changed**
- `scripts/audit_computed_surface_extent_vs_raw.py` — skip `roof_surfaces.flat[i]` entries where `room_index is None` (whole-building envelope fallbacks) before scoring.

**Why**
User loaded the Step 1 "Computed overextend" overlay on a building and saw a 181 m² red rhombus blanketing the scene, unaligned with any rooms. Investigation traced it to `flat:8` of building `b4f7407a-…`: a 4-corner 181 m² rectangle with `room_index=None`, `gap=-0.079 m` (computed surface *below* the raw ceiling). The pipeline's flat-roof surface list mixes two populations:
1. Per-room flat roofs — one per room, bounded by the room's wall-top polygon (`room_index` set).
2. Whole-building envelope fallbacks — stitched from leftover segments when no single room hypothesis fits (`room_index=None`).

Corpus-wide the second population is 30% of scored surfaces (584/1908 with negative Y-gap) and has no valid "overextend" interpretation — the computed surface isn't reaching past raw evidence, it's living at floor/ceiling level because the envelope fallback is a different geometric entity entirely.

**Result**
- Post-filter: 1375 → 1247 rows in `per_surface.csv`, 931 → 417 polygons in `overextend_polygons.json`.
- Flat `overextend_fraction_xz` p95 dropped from 0.437 → 0.179 (phantom envelopes were padding the tail).
- Target building `b4f7407a` now shows 1 piece (`flat:1`, 8 m² per-room roof with 25 % XZ overshoot) instead of 2.
- Viewer server picks up the new sidecar via mtime cache; no server restart needed.
- Tests: 275/275 `pytest tests/` pass.

**Learnings**
- "Negative overextend gap" is a smoking gun that a surface isn't a roof. A real roof's top-y must be at or above the highest raw-ceiling corner underneath it. If it isn't, the pipeline is emitting a different kind of surface (ground plate, envelope fallback, misclassified floor) that doesn't belong in the overextend signal.
- The cleaner filter is on `room_index`, not on the Y-gap threshold — it attacks the source of the bogus surfaces rather than a consequence. The Y-gap filter (`MAX_NEGATIVE_GAP_M = -0.1`) stays as a defensive second line.
- "Generalize before specializing" mattered here: before adding any filter I checked 30 % of the corpus behaves this way (584/1908), confirming it's a structural property of the pipeline output, not a one-building oddity.

---

## 2026-04-21 — Dedup duplicate vertical stitch quads

**Files changed**
- `reconcile/extract3d/stitch.py` — added `dedup_duplicate_vertical_stitches`; its bucket hashes each `type='stitch'` quad by rounded xz-bbox + y-extent (0.15 m buckets) and rejects a quad that shares ≥2 near-matching corners with an earlier one. Called from `stitch_wall_gaps` after `snap_stitches_to_non_owner_walls`.
- `reconcile/extract_3d.py` — imported and invoked the same helper at the tail of the in-file `_stitch_wall_gaps` (the main-script path), so both extractors produce identical dedup.
- `tests/test_score_results.py` — added `bld_stitch_wall_count` to the math-parity `_SKIP` set with the same rationale already used for `bld_gap_wall_count`: it's a pass-through count from `buildings_3d.json` that drifts whenever V1 extraction changes, not a feature-code regression.
- `reconcile/buildings_3d.json`, `reconcile/roof_algorithms_py_results.json` — regenerated by `python reconcile/extract_3d.py` across all 187 buildings.

**Why**
User reported a visual "butterfly / bow-tie" in front of wall `d4665def-0566-4ccc-aa62-8d562ec6e424::wall-computed::AEAB141F-…` in the viewer, and couldn't right-click it to copy its locator. Probing confirmed none of the legacy polygons were self-intersecting as stored, and the ontology atoms at that point were only a flat roof above. A cohort scan across all buildings for "stitch pairs with different `room_indices` whose corners match within 10 cm" returned 1,771 hits over 162 buildings (87 %). Splitting the cohort showed 169/187 buildings (90 %) have the "same wall, two room-pairings" pattern — e.g. wall AEAB separates room 1 from both room 0 and room 5, so the endpoint-pair scan in `_stitch_wall_gaps` emits one stitch per pair, and both outward L-legs land on the same wall face. The `used_pairs` set doesn't catch this because the two pairs have different endpoint keys. The viewer then overlays two translucent quads with ~2–5 cm offsets, and their `createEdgeLoop` outlines (which carry no locator) visually cross as a bow-tie.

Pre-implementation simulation: removing vertical-only `type='stitch'` duplicates by xz-bbox+y-extent signature was projected to delete 1,890/10,395 vertical stitches (18.2 %) while leaving cap triangles untouched (they fan into genuinely different wedges per pair and would lose real coverage if merged). The full-file dedup variant (all types) was projected to delete 4,115/22,533 (18.3 %) but was unsound for caps, so only the narrow variant was implemented.

**Result**
- Corpus: 22,533 → 20,643 stitch entries after full re-extract. Vertical stitches: 10,395 → 8,505 (−1,890, exact match to the simulation).
- Target `d4665def-…`: 68 → 62 stitches. The duplicate vertical quad `stitch_walls[16]` (`room_indices=[1,5]`) at wall AEAB is gone; the load-bearing `stitch_walls[9]` (`room_indices=[0,1]`) that covers the full wall length is preserved, as is the cluster-B snapped extension (`snap:0CC07221-…`) that fills a genuinely different gap at the corner.
- Top-cohort spot-checks: Heisesvej 2 245→207 (−38), Kørbygade 9 330→303 (−27), Søvangsvej 16 296→273 (−23), Bakkegårdsvej 46 154→131 (−23). Reductions are consistent with a targeted duplicate-removal, not a structural loss of coverage.
- Tests: 275/275 `pytest tests/` pass after the `_SKIP` update.

**Limitations / follow-ups**
- 109/187 buildings still have `stitch_floor` / `stitch_ceiling` *triangle* caps from different room-pairs whose xz footprints overlap and whose y values sit within 30 cm of each other. These are not butterflies in themselves (triangles can't self-cross) but create z-fighting and visual clutter. Fix for those is a Shapely polygon union per wall, not a dedup — deferred.
- `reconcile/viewer-main.js:350 clipCornersToObliqueCeilings` still clips corner y's independently without inserting footprint-edge vertices; two clusters clipped against different room-pair obliques can still produce subtly mismatched top edges. Deferred — the main artifact driver was the duplicate quad, and it's gone.
- Tolerances used: `TOL_XZ = TOL_Y = 0.15 m`. Not swept — if a future building regresses, that's the first knob to adjust.

---

## 2026-04-21 — Clean ceilings: local-density flag + oblique/flat split reconstruction

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — replaced the pure room-area density heuristic with a combined rule: keep room-wide planes/m², but also compute a local connected-component density over nearby raw ceiling polygons so large rooms with a single chaotic patch can still be flagged. Added a second reconstruction mode for mixed rooms: use the best computed oblique surface for orientation, then fit a horizontal cap by splitting the room footprint along the oblique plane at the level whose cap best overlaps the raw flat-ceiling extent. The sidecar now emits either one clean oblique piece or a two-piece `oblique + flat-cap` reconstruction per room.
- `reconcile/viewer-main.js` — updated the clean-ceiling renderer to consume multi-piece sidecar entries (`piece_role`, `replacement_mode`, unique per-piece element IDs), keep the same green density ramp, and show the extra reconstruction metadata in the locator/source string.
- `reconcile/viewer-modules/constants.js` — updated the clean-ceiling overlay comment to reflect the new mixed reconstruction semantics.
- `reconcile/viewer.html` — bumped the viewer cache-buster query for the new clean-ceiling overlay payload.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated from the updated script.

**Why**
User feedback on the first clean-ceiling layer identified two concrete misses. First, some large rooms were not flagged because the room-wide density diluted a very local noisy patch. Second, many noisy rooms are not "just a sloped plane" — they are better represented by a sloped plane that transitions into a horizontal cap above it. The fix follows the repo's current ceiling rule split: computed geometry owns orientation, raw ceilings own extent. So the oblique plane still comes from the roof pipeline, but the location of the flat/sloped split is placed where it best matches the raw flat-ceiling footprint.

**Result**
- Corpus rerun (`python scripts/audit_noisy_slanted_ceiling_replacement.py`): noisy-slanted rooms **270 -> 278** via the local-density fallback; rooms with a clean computed replacement **195 -> 200**; rooms upgraded to a two-piece `oblique + flat-cap` reconstruction **124**.
- The local-density fallback is conservative: only **8** rooms were added beyond the original room-area heuristic, and **5** of those have an oblique replacement available.
- Full regression suite: **275/275** `pytest tests/` pass. Viewer syntax check: `node --check reconcile/viewer-main.js` passes.

**Learnings**
- Local chaos is better modeled as a spatial cluster than as a room property. A connected-component density catches "one bad corner in a big room" without broadly lowering the global threshold.
- The mixed-room split only works when the raw flat extent actually fits a straight cut against the computed oblique gradient. On this corpus that succeeds often enough to be useful (124 rooms), but not universally — fallback remains the single oblique clean plane when the fit is weak.

---

## 2026-04-21 — Clean ceilings: extend replacements over lower-floor gap envelopes

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — added `_expand_room_footprint_with_same_story_gaps`, which grows a room footprint into same-story `cross_floor_gaps` before clipping the selected clean-ceiling surface. The rule is intentionally bounded: include `within_story` gaps already assigned to the room plus same-story `cross_story` gaps, then keep only the connected subset inside a `2.0 m` flood-reach from the room. Mixed `oblique + flat-cap` reconstructions now apply the flat/sloped split over that expanded footprint, while the sloped piece remains clipped to the chosen oblique computed surface.
- `tests/test_noisy_slanted_ceiling_replacement.py` — new helper coverage for the gap-extension rule: absorb assigned / same-story gaps when connected, but ignore other-room, other-story, and far-away gaps.
- `reconcile/viewer-main.js`, `reconcile/viewer.html` — clean-ceiling locator text now reports how much extra area came from gap extension (`gap +Xm²`) so Step 1 inspections show when a plane was grown over lower-floor gaps; bumped the viewer cache-buster so the updated overlay loads without relying on stale module cache.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the new gap-extension pass.

**Why**
User asked for the clean replacement planes to extend over "gaps from below floors". Those are exactly the same lower-floor envelope holes already represented in `cross_floor_gaps`: roof-supported area that sits outside the current room floor polygon because the upper storey pulled back. Using only the room floor clipped the clean ceiling too tightly; the replacement should be allowed to claim nearby lower-floor gap area, but not jump across the whole building. Reusing the ridge/eave scorer's bounded flood-fill gives the physically-right rule without turning Step 1 into a building-wide flood.

**Result**
- Corpus rerun (`python scripts/audit_noisy_slanted_ceiling_replacement.py`): **170** noisy-slanted rooms with a replacement now extend into gap area, adding **1478.8 m²** of cleaned ceiling coverage over lower-floor gaps.
- Current Step 1 totals after the gap pass: **278** noisy-slanted rooms, **197** rooms with a clean replacement across **79** buildings, **124** of them still using the mixed `oblique + flat-cap` reconstruction.
- Spot-check building `0d3f2993`: room 1 gained **33.25 m²** of gap extension (7 same-story `cross_story` gaps), room 3 gained **4.43 m²**, room 4 gained **5.60 m²**.
- Validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes; full suite `python -m pytest tests/` passes (**277/277**). `node --check reconcile/viewer-main.js` passes.

**Learnings**
- The right extension primitive is not "grow into neighbouring rooms"; it is "grow into the room's connected gap envelope". That keeps the per-room semantics of Step 1 intact while still honoring lower-floor support beneath the roof.
- Mixed reconstructions need asymmetric clipping: the flat-cap can follow the expanded room+gap footprint, but the sloped piece must stay clipped to the actual oblique computed surface or it will invent roof where the pipeline has no supporting plane.

---

## 2026-04-21 — Clean ceilings: trust computed planes more in `noMesh` slanted rooms

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — added `_should_promote_nomesh_computed_room`. New Step 1 trigger: if `raw_ceiling_source == "noMesh"`, raw support still shows both a slanted and a flat ceiling signal, density is below the chaos threshold, and the best computed oblique surface covers at least `80%` of the room footprint, then the room is promoted into the clean-ceiling pass even though fragmentation is low. This catches rooms where Apple's `noMesh` ceiling stub only emitted 2-3 planes, which was suppressing computed replacements despite strong roof support.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added unit coverage for the `noMesh` promotion gate.
- `reconcile/viewer-main.js` — locator/source text now labels these as `noMesh computed-backed` so the viewer makes it obvious when a room was promoted by this rule.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the new promotion gate.

**Why**
User flagged building `7153d532-16c1-45e8-b7c9-f5cd1ba5cc85` as under-using computed planes. Diagnosis: three top-story rooms (`10`, `13`, `15`) had extremely strong computed oblique support (`overlap_ratio = 0.991 / 0.867 / 0.955`) but only `2-3` raw `noMesh` planes each, so they never tripped the density-based "noisy" gate. This is a different failure mode from chaotic scan fragmentation: not *too much* raw, but *too little* raw because `noMesh` is a coarse placeholder. The fix is to trust the computed oblique more when `noMesh` already agrees on the room archetype (flat + slanted) and the overlap is strong.

**Result**
- Target building `7153d532`: clean-ceiling replacements **3 -> 6** rooms. Newly promoted rooms: `10`, `13`, `15`. Room `10` now renders as `oblique-plus-flat`, room `13` as `oblique-plus-flat`, room `15` as `single-oblique`. Rooms `11` and `14` still stay out because computed oblique coverage is weak (`0.119` and `0.403`) rather than merely under-triggered.
- Corpus rerun (`python scripts/audit_noisy_slanted_ceiling_replacement.py`): noisy-slanted / promoted rooms **278 -> 361**. New `noMesh computed-backed` additions: **85** rooms across **45** buildings. Rooms with a clean replacement **197 -> 280**. Mixed `oblique + flat-cap` reconstructions **124 -> 199**. Buildings with replacements **79 -> 85**.
- Validation: targeted tests pass; full suite `python -m pytest tests/` passes (**279/279**). `node --check reconcile/viewer-main.js` passes.

**Learnings**
- There are two distinct Step 1 miss classes now: "high fragmentation" and "low-fidelity `noMesh` stub". The first is a density problem; the second is a source-trust problem.
- For `noMesh`, the right trust split is: use the raw planes only to confirm the room has both slanted and flat evidence; use computed overlap to decide whether the room should be cleaned. This preserves the earlier principle that computed geometry owns angle while raw geometry owns local extent.

---

## 2026-04-21 — Clean ceilings: match computed obliques by room orientation, then project across clipped misses

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — replaced the overlap-only oblique selector with an orientation-aware matcher. The script now derives a dominant raw slanted azimuth per room (area-weighted circular mean of the raw slanted ceiling planes), prefers computed oblique surfaces within `25°` of that orientation, and only falls back to the old overlap-only behavior when the room has no usable raw slanted azimuth. If the right computed oblique family is nearby but clipped short of the room, the script now projects that plane across the whole room footprint (and any already-admitted gap extension) instead of defecting to an opposite-facing surface just because it overlaps more. The sidecar and CSV now also record the selected surface azimuth, azimuth delta, surface distance, and selection mode (`orientation-overlap`, `orientation-projected`, `overlap-only`).
- `tests/test_noisy_slanted_ceiling_replacement.py` — added regression coverage for the new selector behavior: prefer a nearby same-orientation surface over an overlapping opposite-facing one, keep the old overlap-only fallback when no raw orientation is available, and allow the `noMesh` promotion gate to accept an orientation-projected match.
- `reconcile/viewer-main.js`, `reconcile/viewer.html` — clean-ceiling locator text now shows the selection mode and azimuth delta so viewer spot-checks make it obvious when Step 1 is using an orientation-projected substitute; bumped the viewer cache-buster to load the updated overlay text.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the selector change.

**Why**
User rejected the previous `noMesh` expansion because it was covering the wrong rooms and sometimes using the wrong roof family. In building `7153d532-16c1-45e8-b7c9-f5cd1ba5cc85`, rooms `11` and `14` had raw slanted ceilings aligned with the `~154°` oblique family, but the overlap-only selector still chose the opposite-facing `~335°` family whenever it happened to clip a larger polygon. That is physically backward: Step 1 should first respect the direction of the raw slanted ceiling it is replacing, then tolerate missing footprint overlap when the correct computed plane was simply clipped too tightly upstream.

**Result**
- Target building `7153d532`: clean-ceiling replacements **6 -> 8** rooms. Rooms `11` and `14` are now covered by the `~154°` family via `orientation-projected` selection, and room `8` no longer uses the opposite-facing family — it now projects the matching `~154°` family instead. Rooms `9`, `10`, `12`, `13`, and `15` keep using direct orientation-matched overlaps.
- Corpus rerun (`python scripts/audit_noisy_slanted_ceiling_replacement.py`): noisy-slanted / promoted rooms **361 -> 373**; rooms with a clean replacement **280 -> 302**; buildings with replacements **85 -> 89**. Only **37** rooms across **24** buildings use the new projected mode, so the change stays targeted rather than turning Step 1 into a broad plane flood.
- Validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**7/7**); full suite `python -m pytest tests/` passes (**282/282**); `node --check reconcile/viewer-main.js` passes.

**Learnings**
- The right ordering for Step 1 selection is now explicit: raw ceilings determine *which* computed oblique family is physically plausible, then computed geometry determines the clean substitute footprint and height.
- Footprint overlap is not a safe primary key when the computed oblique has already been clipped upstream. A nearby same-direction plane is more trustworthy than an opposite-facing plane with a stray overlap patch.

---

## 2026-04-21 — Clean ceilings: exact 3-part mixed rooms can reuse upstream multi-oblique partitions on 180°/90° raw-family matches

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — added a narrow multi-family detection path ahead of the single-plane replacement fallback. The script now clusters each room's raw slanted ceiling planes by azimuth, keeps only dominant families, and looks for a strong pair whose separation is near either `180°` or `90°`. When that signal exists *and* the upstream `ceiling_partitions.room_partitions` entry is a simple exact `3`-part mixed room (`2` obliques + `1` flat, no tiny parts), Step 1 now uses those upstream partition polygons directly instead of collapsing the room to one chosen oblique face. Fragmented mixed rooms remain on the old synthetic replacement path.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added regression coverage for the new gated path: accept a clean opposite-family (`180°`) case, accept a perpendicular-family (`90°`) case, and reject a fragmented `4`-part room partition so the small-crud room-partition cases do not come back.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the new multi-family mixed-room pass.

**Why**
User pointed out that some rooms are not "one sloped face plus a flat cap" at all; they are better represented by two distinct sloped families with a flat segment between them. Building `7153d532-16c1-45e8-b7c9-f5cd1ba5cc85`, room `14`, was the concrete example: raw ceilings show two strong slanted families around `155°` and `335°`, and the upstream roof pipeline had already partitioned the room into exactly `2` obliques plus `1` flat cap. The old Step 1 sidecar ignored that and still synthesized a single oblique replacement. The new rule tries the user's suggested geometry cue directly — two dominant raw families near `180°` or `90°` apart — but only trusts upstream room partitions when they are structurally simple enough not to reintroduce captured slivers.

**Result**
- Target building `7153d532`: room `14` now renders as `multi-oblique-flat` with `replacement_surface_kind=room-partitions` and `replacement_selection_mode=room-partitions-180`, producing two oblique clean pieces plus one flat cap instead of the previous single projected oblique.
- Corpus rerun (`python scripts/audit_noisy_slanted_ceiling_replacement.py`): rooms with a clean replacement **302 -> 303**. Only **4** rooms across **4** buildings switched onto the new `room-partitions` path, all as `multi-oblique-flat`; replacement source counts are now `oblique: 299`, `room-partitions: 4`.
- The gate stayed narrow by design: exact `3`-part mixed rooms only. That avoids the broad fragmented mixed-room cohort where many rooms contain numerous sub-`1 m²` parts.
- Validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**10/10**); full suite `python -m pytest tests/` passes (**285/285**); `node --check reconcile/viewer-main.js` passes.

**Learnings**
- The `180°`/`90°` raw-family cue is useful, but only when paired with a simplicity gate on the upstream mixed partition. On this corpus, that keeps the fix surgical.
- Exact mixed room partitions are a better Step 1 substitute than any single-plane reconstruction when the room truly has multiple sloped families. The synthetic fallback should remain the default for fragmented mixed rooms, not the other way around.

---

## 2026-04-21 — Clean ceilings: compress overly fragmented `noMesh` room partitions when one dominant computed group explains the room

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — added a second narrow `room-partitions` path for the user's "unnecessarily noisy" room class. This path is distinct from the earlier exact `2 obliques + 1 flat` reuse: it only applies to `noMesh` rooms whose upstream `ceiling_partitions.room_partitions` entry is already mixed and fragmented (`>= 6` parts), but whose parts collapse into exactly one dominant computed group after grouping by hypothesis / plane family. The grouped coverage must still explain at least `85%` of the room, and raw complexity must exceed the simplified computed group count by at least `3` planes. This intentionally targets de-facto simple ceilings that RoomPlan has chopped into many small captured parts, regardless of whether the dominant computed group is horizontal or sloped.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added regression coverage for this new simple-partitions path: accept a noisy `noMesh` room whose fragmented mixed partitions reduce to one dominant computed group, and reject a room that still has too many significant computed groups after simplification.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the new simplification pass.

**Why**
User pointed out that in building `5c557e06-393e-466e-a957-f7391b76b8ff`, the missed rooms are not "needs more oblique faces" cases. They are mostly de-facto simple ceilings whose captured raw ceilings are noisier than necessary. The earlier broad simplification attempt was too aggressive — it exploded to 355 replacements and started overriding many unrelated rooms. The refined rule now only trusts a fragmented upstream mixed partition when it really collapses to one dominant computed surface family. That matches the user's clarification that "flat" here means low-complexity / unnecessary fragmentation, not strictly horizontal.

**Result**
- Target building `5c557e06`: room `2` now uses `replacement_mode=simple-partitions`, `replacement_surface_kind=room-partitions`, `replacement_selection_mode=room-partitions-simple` instead of the previous `single-oblique`. This room had `15` raw ceiling planes, but its fragmented upstream mixed partition (`10` parts) collapses to one dominant computed group covering `95.8%` of the room, so Step 1 now uses that simpler computed ceiling.
- `5c557e06` room `1` still stays out. Its upstream mixed partition remains meaningfully multi-group after simplification, so it does not satisfy the "one dominant computed group" gate.
- Corpus rerun (`python scripts/audit_noisy_slanted_ceiling_replacement.py`): clean replacements stay bounded at **303** rooms across **89** buildings. `room-partitions` replacements increase from **4** to **11** rooms total; only **7** rooms use the new `room-partitions-simple` path.
- Validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**12/12**); full suite `python -m pytest tests/` passes (**287/287**); `node --check reconcile/viewer-main.js` passes.

**Learnings**
- "Unnecessarily noisy" needs a stronger safety condition than "computed can be simplified somehow". A broad simplifier regressed immediately; the narrow "exactly one dominant computed group" test did not.
- The right mental model is not horizontal-vs-sloped. It is raw complexity vs computed complexity: when `noMesh` raw ceilings explode into many parts but the computed room model still says "this is basically one surface family", Step 1 should trust the computed simplification.

---

## 2026-04-21 — Clean ceilings: do not flatten noisy-simple rooms to horizontal caps

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — corrected the new `room-partitions-simple` path so it can no longer emit a replacement when the only dominant computed group is `flat`. The simplifier now only applies when the dominant simplified group is an `oblique` family. This preserves the user's intended semantics: "simple" means low-complexity / smoothed, not "horizontal".
- `tests/test_noisy_slanted_ceiling_replacement.py` — updated the positive simplification fixture to use an oblique-dominant group and added an explicit regression test that rejects a flat-dominant simplification.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the fix.

**Why**
The first version of the noisy-simple simplifier misread the user's intent and replaced `5c557e06-393e-466e-a957-f7391b76b8ff` room `2` with a horizontal `flat-cap` because the fragmented upstream room partitions collapsed to a dominant flat group. That was wrong: the goal is to smooth ceilings, not to flatten them.

**Result**
- `5c557e06` room `2` now reverts to a sloped clean replacement: `replacement_mode=single-oblique`, `replacement_surface_kind=oblique`, `replacement_selection_mode=orientation-overlap`. The emitted clean-ceiling geometry is again an oblique piece instead of a horizontal cap.
- Corpus totals remain stable after the correction: **303** rooms with a clean replacement across **89** buildings. `room-partitions` replacements drop back to **4** rooms total, which are the intentionally narrow multi-oblique mixed-room cases.
- Validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**13/13**); full suite `python -m pytest tests/` passes (**287/287**).

**Learnings**
- A "simple ceiling" trigger must preserve slope semantics. Dominant flat-group simplification is unsound for this layer unless the user explicitly wants horizontal replacements.
- The current Step 1 code is safe again, but the broader "other noisy-simple rooms" request still needs a different trigger than the one that caused this regression.

---

## 2026-04-21 — Clean ceilings: promote shallow coherent `noMesh` rooms by weighted sloped evidence

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — added a second `noMesh` promotion path for borderline-density rooms that still have a coherent sloped ceiling signal. The new helper computes weighted raw-plane evidence per room: area-weighted slanted inclination plus slanted-vs-flat area share. Step 1 now promotes a `noMesh` room when raw density is just below the old threshold, there are enough raw planes to show real fragmentation, computed oblique overlap is still meaningful, and the weighted raw signal says the room is mostly sloped. This keeps the replacement sloped; it does not reinterpret shallow slopes as horizontal.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added regression coverage for the new weighted promotion gate: one positive case for a coherent shallow sloped room and negative cases for weak overlap or too-low weighted slope.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the new weighted promotion pass.

**Why**
User pointed out that the previous reasoning was wrong: a room averaging around `10°` is still sloped, and the useful signal is not a flat-vs-sloped binary but the weighted room-wide slope evidence. The missed rooms in `5c557e06-393e-466e-a957-f7391b76b8ff` were not being caught because the hard raw-plane density gate was too literal for shallow but coherent `noMesh` ceilings.

**Result**
- `5c557e06` room `1` is now included in Step 1 via `promote_nomesh_weighted=1`. Its raw ceiling has `5` planes over `12.72 m²` (`0.393` planes/m²), but its weighted slanted inclination is `12.1°`, slanted area share is `0.783`, and the best orientation-matched computed oblique overlaps `62.2%` of the room. It now renders as `single-oblique` against the matching `133.5°` computed family instead of being skipped entirely.
- `5c557e06` now has clean-ceiling replacements in rooms `0`, `1`, and `2`. The important change is room `1`; room `0` remained covered by the earlier strong-overlap `noMesh` gate, and room `2` remained covered by the existing noisy-slanted path.
- Corpus rerun (`python scripts/audit_noisy_slanted_ceiling_replacement.py`): noisy-slanted / promoted rooms increase from **373** to **376**; clean replacements increase from **303** to **306**; `noMesh weighted-average additions` contributes **3** rooms across the corpus; replacement source remains bounded at **302 oblique** + **4 room-partitions** across **90** buildings.
- Validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**15/15**); full suite `python -m pytest tests/` passes (**290/290**).

**Learnings**
- For shallow `noMesh` rooms, weighted raw-plane evidence is a better trigger than a hard density threshold. It preserves the physical interpretation: `10°` is still a sloped ceiling if most of the room supports that direction.
- This path stays narrow because it still requires both meaningful computed overlap and enough raw fragments to justify smoothing. It promotes coherent shallow slopes without reopening the earlier horizontal-flattening regression.

---

## 2026-04-21 — Clean ceilings: merge same-orientation oblique families before selecting a replacement

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — taught `_best_computed_surface()` to build room-local oblique-family candidates by merging nearby computed oblique surfaces with the same approximate azimuth and inclination, then fitting a weighted-average plane across that family. These family candidates now compete with individual surfaces during orientation-based selection. This fixes the case where a shallow roof family was split upstream into two adjacent computed surfaces and Step 1 only chose the single best overlap stub.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added a regression test showing that two same-orientation oblique surfaces should be merged into one family candidate when together they explain the room better than either individual surface.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the family-merge pass.

**Why**
User flagged that in `5c557e06-393e-466e-a957-f7391b76b8ff`, the new weighted gate still only covered room `1` partially. The underlying issue was not the promotion trigger anymore; it was the replacement selector. The roof pipeline had two shallow `~133.5°` oblique surfaces over that room, but Step 1 treated them as mutually exclusive alternatives instead of one shallow slope family.

**Result**
- `5c557e06` room `1` now renders with `replacement_selection_mode=orientation-family-overlap` and `replacement_overlap_ratio=0.982` instead of the previous `orientation-overlap` at `0.622`. It is still a single clean oblique piece, but now it uses the weighted-average plane from the merged `~133.5°` family rather than only one clipped member of that family.
- The building still has clean-ceiling replacements only in rooms `0`, `1`, and `2`. Rooms `3` and `4` remain outside Step 1 because they do not trip the noisy-room gates: each has just one raw ceiling plane, so they are not currently treated as “chaotic scan ceilings.”
- Corpus rerun (`python scripts/audit_noisy_slanted_ceiling_replacement.py`): clean replacements settle at **305** rooms across **90** buildings. `5c557` improves visibly even though the total count drops by one elsewhere because one previous room-partitions fallback no longer wins against the stricter family-aware oblique selector.
- Validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**16/16**); full suite `python -m pytest tests/` passes (**292/292**).

**Learnings**
- For shallow roofs, “same orientation” needs to be interpreted at the family level, not only per individual computed surface. Otherwise Step 1 under-covers rooms whenever the pipeline has already split one shallow roof family into adjacent pieces.
- This fix is still narrower than full room-wide projection: it only merges computed surfaces that are already close in azimuth/inclination and already local to the room.

---

## 2026-04-21 — Clean ceilings: include simple one-plane `noMesh` slope rooms backed by a merged oblique family

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — added a new narrow promotion path for simple sloped rooms that were still outside Step 1. The new `noMesh single-slope` gate applies only when a room has exactly one raw slanted ceiling plane, low density, and a near-total computed match from a merged same-family oblique candidate (`orientation-family-overlap`, overlap `>= 0.98`). This targets “simple but clearly sloped” rooms rather than chaotic ones.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added regression coverage for the new gate: accept a one-plane `noMesh` room with a merged-family computed match, and reject rooms whose support is only a single-surface overlap or whose computed support is not strong enough.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the new simple-room pass.

**Why**
After fixing room `1` in `5c557e06-393e-466e-a957-f7391b76b8ff`, the remaining misses were rooms `3` and `4`. They were not failing because computed support was weak; they were failing because Step 1 still only looked for noisy or fragmented rooms. In both rooms, RoomPlan had captured only one shallow sloped ceiling plane, while the merged `~133.5°` computed oblique family already explained the whole room.

**Result**
- `5c557e06` now has clean-ceiling replacements in all five rooms:
  - room `0`: unchanged, full support from the existing `noMesh computed-backed` path
  - room `1`: retained from the weighted/family fix, now `0.982` overlap
  - room `2`: unchanged partial `313.5°` oblique replacement (`0.236`) because upstream support there is still genuinely mixed/fragmented
  - room `3`: newly added, `replacement_mode=single-oblique`, `replacement_selection_mode=orientation-family-overlap`, overlap `1.0`
  - room `4`: newly added, `replacement_mode=single-oblique`, `replacement_selection_mode=orientation-family-overlap`, overlap `1.0`
- Corpus rerun (`python scripts/audit_noisy_slanted_ceiling_replacement.py`): `noMesh single-slope additions` contributes exactly **2** rooms, both in `5c557e06`; total clean replacements increase from **305** to **307** across **90** buildings.
- Validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**18/18**); full suite `python -m pytest tests/` passes (**294/294**).

**Learnings**
- There are two different “clean ceiling” problems: chaotic fragmented ceilings and overly sparse shallow-slope captures. The second class needs its own gate; forcing it through the noisy-room criteria just misses obvious wins.
- Requiring a merged-family match keeps this path narrow. A single raw slope plane is only trusted when the computed model already says “this whole room belongs to the same shallow oblique family.”

---

## 2026-04-21 — Clean ceilings: broaden the simple single-slope gate to any near-total computed oblique match

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — widened the new `noMesh single-slope` promotion path. It no longer requires the winning computed support to come specifically from a merged-family candidate; any orientation-matched computed oblique with near-total overlap now qualifies, as long as the room still has exactly one raw slanted ceiling plane and a meaningful weighted slope angle.
- `tests/test_noisy_slanted_ceiling_replacement.py` — updated the single-slope regression tests to reflect the broader rule: accept a strong `orientation-overlap` match as well, and keep rejecting low-support or non-sloped cases.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the broader single-slope pass.

**Why**
After seeing the narrow two-room rollout work, user accepted the broader blast radius of the originally simulated cohort. The earlier simulation suggested about `22` rooms would qualify if the rule trusted any near-total computed oblique support for one-plane `noMesh` rooms, not just merged-family support. That is the more useful production rule: the important signal is “one coherent raw slope, almost fully explained by computed oblique geometry,” regardless of whether that computed support comes from one surface or a merged family.

**Result**
- Corpus rerun (`python scripts/audit_noisy_slanted_ceiling_replacement.py`): `noMesh single-slope additions` rises from **2** to **21**, bringing total clean replacements from **307** to **324** across **94** buildings.
- The realized blast radius is `21`, not `22`, because one previously simulated case was already captured by an existing promotion path after the family-merge changes.
- `5c557e06-393e-466e-a957-f7391b76b8ff` still looks correct under the broader rule: rooms `3` and `4` stay covered with full `1.0` overlap, and the building retains clean ceilings in rooms `0` through `4`.
- Validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**18/18**); full suite `python -m pytest tests/` passes (**294/294**).

**Learnings**
- The deciding factor for sparse `noMesh` rooms is not whether the computed support had to be merged; it is whether the computed oblique already explains essentially the whole room.
- The broader rule is still disciplined because it only applies to the one-plane class with very high computed overlap, so it expands coverage without reopening the earlier “flattening” or mixed-room regressions.

---

## 2026-04-21 — Roof partitioning: repair snapped ceiling rings before serialization

**Files changed**
- `reconcile/roof_algorithms_py/roof_partitioning.py` — added snapped-ring sanitation inside `_atom_corners()`. The partitioner now snaps the atom exterior/interior rings in `x,z`, rebuilds a 2D polygon from the snapped coordinates, and runs `make_valid(...)` before lifting the ring back into 3D. When snapping collapses near-duplicate vertices onto the same millimeter coordinate, we now keep the repaired polygon component that best matches the original atom instead of serializing a self-intersecting bow-tie ring.
- `tests/test_roof_partitioning.py` — added a regression fixture based on building `38f71f1d-2c71-4fcd-9997-83b2914416b0`, room `6`, where a valid oblique partition used to become invalid after serialization because two vertices only `0.0002237 m` apart collapsed to the same snapped point.

**Why**
The user reported visibly overlapping "clean ceilings" over room `38f71f1d-2c71-4fcd-9997-83b2914416b0::wall-computed::377ECF36-8F90-46C0-95EE-8064FF276C47`. Tracing the room showed that the large oblique ceiling partition was valid before serialization, but `_atom_corners()` snapped two distinct `x,z` vertices to the same millimeter coordinate. That turned the stored ring into a self-intersecting polygon, and the viewer triangulation then rendered it as an apparent overlap.

**Result**
- The large oblique partition for the reproduced room now stays valid after `derive_room_ceiling_partitions(...)` emits it. The regression test asserts that the stored `x,z` polygon for the largest oblique partition is valid and still has the expected `12.976 m²` area.
- Validation: `python -m pytest tests/test_roof_partitioning.py -q` passes (**1/1**).

**Learnings**
- The bad visual overlap was not caused by two ceiling patches owning the same interior area. It was caused by a valid partition atom becoming invalid only after millimeter snapping during serialization.
- Repairing snapped rings at the serialization boundary is safer than trying to tune the earlier intersection logic. The upstream polygonization can stay exact; only the stored viewer payload needs the extra validity guard.

## 2026-04-21 — Viewer: make clean noisy ceilings clickable

**Files changed**
- `reconcile/viewer-main.js` — added `groups.ceilingReplacement` to `getVisiblePickRoots()` so the click/right-click raycaster includes the "Clean ceilings (noisy slanted)" overlay.

**Why**
Clean noisy-ceiling replacement polygons already had locators attached (`kind: clean-ceiling`), but their group was not part of the raycast pick roots. That made them visible but not clickable/selectable.

**Result**
- Clean noisy ceilings can now be clicked and right-clicked like other locator-backed overlays.
- Element locator interactions (`select`, copy UID, search-jump) work for these surfaces once the layer is visible.
- No pipeline logic changed; this is a viewer interaction fix only.

## 2026-04-21 — Clean ceilings: switch noisy-slanted replacement to local raw-vector voting

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — removed the dead `room-partitions-simple` fallback and rewrote `_best_computed_surface(...)` around local raw ceiling evidence. The script now polygonizes room-local `x,z` cells from clipped raw ceiling polygons, computes area-weighted average raw normals per cell, scores computed oblique candidates by local normal agreement (`dot >= 0.80`), and chooses the winning computed surface by supported slanted cell area rather than global overlap. Mixed `oblique + flat-cap` replacements now prefer a flat-support polygon derived from locally flat cells instead of the old room-wide raw-flat union.
- `tests/test_noisy_slanted_ceiling_replacement.py` — replaced the old orientation/simplifier regressions with coverage for the new local selector: raw-evidence cell polygonization, area-weighted mixed normals, local-vote winner selection, family-candidate selection, projection gating, local flat-support extraction, and retention of the narrow `room-partitions` multipart path.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated from the rewritten selector.

**Why**
The previous audit had drifted toward choosing one computed ceiling mostly from room-wide overlap, plus a now-unused `room-partitions-simple` branch. That was the wrong abstraction for noisy mixed ceilings: the useful evidence is local, because different parts of a room can be supported by different captured ceiling plane directions. The replacement pass needed to trust the average captured ceiling vectors at each local `x,z` region, then generalize from those locally-supported computed planes while keeping the existing `single-oblique` / `oblique-plus-flat` output contract.

**Result**
- Focused validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**20/20**).
- Full validation: `python -m pytest tests/` passes (**296/296**).
- Corpus rerun: `python scripts/audit_noisy_slanted_ceiling_replacement.py`
  - noisy-slanted rooms: **396 -> 388**
  - rooms with a clean replacement: **326 -> 302**
  - mixed `oblique + flat-cap` reconstructions: **221 -> 203**
  - buildings with replacements: **94 -> 92**
  - replacement source stays bounded at **299 oblique** + **3 room-partitions**
- Selector mode shift in the regenerated report:
  - `overlap-only`: **88 -> 0**
  - `local-vector-overlap`: **265**
  - `local-vector-projected`: **31**
  - `local-vector-family-overlap`: **3**
  - `room-partitions-180`: **3**
- Requested spot check `7153d532-16c1-45e8-b7c9-f5cd1ba5cc85` stays covered, now with explicit local support metrics. Rooms `8` and `11` remain projected, but projection is now justified by local slanted support ratios (`0.516` and `0.333`) instead of a room-wide azimuth-only rule.

**Learnings**
- The old `overlap-only` selector was broad but low-fidelity. Local raw-cell voting is stricter: it eliminates the generic overlap fallback for rooms that still have slanted raw evidence, and only permits projection when enough of the room is locally supported.
- Large azimuth deltas can still appear in the report because the new selector is based on full 3D normal agreement, not azimuth alone. That is expected for shallow slopes where two planes can be close in normal space even when their down-slope azimuths look far apart; the new local support fields are the authoritative diagnostic for those cases.

## 2026-04-21 — Clean ceilings: replace captured regions per local plane, not per room winner

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — changed the actual replacement builder so it no longer takes the single `_best_computed_surface(...)` winner and spreads that plane across the room. The script still uses the top winner for gating / promotion, but the emitted geometry is now built per local raw-evidence cell: each slanted captured region chooses its best-matching computed oblique plane by normal agreement, adjacent regions assigned to the same plane are merged, and the sidecar emits those merged plane pieces directly. Flat local cells are emitted as flat-cap pieces at the weighted average captured height instead of being synthesized only by splitting one room-wide oblique.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the per-cell replacement rewrite.

**Why**
The first local-vector rewrite still made the wrong final decision: it used captured ceilings only to pick one room-wide computed plane, then replaced the whole room with that plane. The user wanted the opposite relationship. Captured ceiling regions should decide which computed plane is correct at each local `x,z`, and the output should replace those captured regions with the corresponding computed planes rather than collapsing the room back to one winner.

**Result**
- Validation remains green: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**20/20**); full suite `python -m pytest tests/` passes (**296/296**).
- Corpus rerun: `python scripts/audit_noisy_slanted_ceiling_replacement.py`
  - noisy-slanted rooms remain **388**
  - rooms with a clean replacement increase **302 -> 305**
  - mixed reconstructions increase **203 -> 275**
  - buildings with replacements stay **92**
  - replacement source stays bounded at **302 oblique** + **3 room-partitions**
- Replacement modes now show the intended per-region behavior instead of mostly single-plane rooms:
  - `oblique-plus-flat`: **189**
  - `multi-oblique-flat`: **86**
  - `single-oblique`: **26**
  - `multi-oblique`: **4**
- Selection modes now include explicit multi-cell cases:
  - `local-vector-overlap`: **189**
  - `local-vector-cells-projected`: **60**
  - `local-vector-cells`: **27**
  - `local-vector-projected`: **26**
  - `room-partitions-180`: **3**

**Learnings**
- There are two separate decisions in this audit: `(1)` whether a room is trustworthy enough to replace at all, and `(2)` how replacement geometry should be emitted. Using local raw vectors for `(1)` is not sufficient if `(2)` still collapses back to one room plane.
- Once the output is built per captured region, many rooms that used to be forced into `single-oblique` naturally become `multi-oblique-flat`. That is a better match to the physical scan evidence and to the user’s requested semantics.

## 2026-04-21 — Clean ceilings: source replacement planes from ridge/eave scoring plane groups

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — stopped sourcing candidate planes from `roof_results["roof_surfaces"]["oblique"]` and added a ridge/eave adapter that loads the latest non-test `reports/ridge_eave_scores_*/scores.json`, keeps selected `plane_groups` per building, converts each group’s `plane` + `union_xz` into a local-voting candidate surface, and only falls back to legacy roof obliques when a building has no ridge/eave scoring output at all. The existing local-cell voting and per-cell replacement emission now run against those ridge/eave plane groups instead of the finalized roof surfaces.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added regressions that verify `_best_computed_surface(...)` accepts ridge/eave plane-group candidates directly and that the ridge/eave loader prefers selected plane groups over unselected ones.
- `reports/noisy_slanted_ceilings/{per_room.csv,summary.json,replacement_polygons.json}` — regenerated after the plane-source switch.

**Why**
The previous rewrite still chose from the wrong plane set. It used captured ceiling segments to decide among already-finalized roof surfaces, but the user’s intent was stricter: use the captured ceiling evidence only to decide which **ridge/eave scored planes** to keep. The audit therefore had to be rewired so the selectable surfaces come from ridge/eave scoring `plane_groups`, not from `roof_surfaces.oblique`.

**Result**
- Focused validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**22/22**).
- Full validation: `python -m pytest tests/` passes (**298/298**).
- Corpus rerun: `python scripts/audit_noisy_slanted_ceiling_replacement.py`
  - noisy-slanted rooms: **521**
  - rooms with a clean replacement: **495**
  - mixed reconstructions: **455**
  - buildings with replacements: **119**
  - replacement source: **490 ridge-eave-plane-group** + **5 room-partitions**
- Selection modes after the source switch:
  - `local-vector-overlap`: **273**
  - `local-vector-cells`: **206**
  - `local-vector-family-overlap`: **5**
  - `local-vector-cells-projected`: **5**
  - `local-vector-projected`: **1**
  - `room-partitions-180`: **5**
- Replacement modes after the source switch:
  - `oblique-plus-flat`: **246**
  - `multi-oblique-flat`: **209**
  - `single-oblique`: **33**
  - `multi-oblique`: **7**

**Learnings**
- The semantic source of a ceiling replacement matters as much as the local selector. Local voting over the wrong candidate set still preserves the wrong hypothesis family.
- Ridge/eave-selected plane groups are materially broader than `roof_surfaces.oblique`, so the corpus now repairs many more noisy rooms. The report metadata now makes that explicit by emitting `replacement_surface_kind=ridge-eave-plane-group` instead of generic `oblique`.

## 2026-04-21 — Clean ceilings: stop synthesizing flat caps when ridge/eave planes already explain those cells

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — changed `_replacement_from_local_cells(...)` so that when ridge/eave plane-group candidates are present, all local raw-evidence cells (including cells whose averaged normal is nearly flat) compete for those plane groups before any raw-derived `flat-cap` fallback is considered. The flat-cap path now only receives unassigned flat cells, rather than all flat cells by default.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added a regression showing that flat local cells are assigned to shallow ridge/eave planes first and therefore no synthetic flat cap is emitted in ridge/eave mode.
- `reports/noisy_slanted_ceilings/{per_room.csv,replacement_polygons.json,summary.json}` — regenerated after the flat-cap suppression change.

**Why**
The previous ridge/eave rewrite still had one absurd semantic leak: sloped raw cells were replaced by ridge/eave-selected planes, but flat raw cells in the same room were still converted into a synthetic flat cap even when the scored ridge/eave planes already explained those regions. That mixed two incompatible meanings in one room: "use scored planes" for one piece and "trust captured flatness" for another. The user’s intent was to replace captured regions with the selected planes, not to keep inventing a flat patch beside them.

**Result**
- Focused validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**23/23**).
- Full validation: `python -m pytest tests/` passes (**299/299**).
- Corpus rerun: `python scripts/audit_noisy_slanted_ceiling_replacement.py`
  - noisy-slanted rooms: **521**
  - rooms with a clean replacement: **495**
  - mixed reconstructions: **161** (down from **455**)
  - buildings with replacements: **119**
  - replacement source remains **490 ridge-eave-plane-group** + **5 room-partitions**
- The reported room `5c557e06-393e-466e-a957-f7391b76b8ff`, story `0`, room `1` now emits:
  - `replacement_mode=multi-oblique`
  - `replacement_selection_mode=local-vector-cells`
  - `local_supported_slanted_area_ratio=1.0`
  - `local_flat_support_area_m2=0.0`
  - only `oblique` clean-ceiling pieces, all with `replacement_surface_kind=ridge-eave-plane-group`

**Learnings**
- Once ridge/eave planes are the intended replacement basis, the `flat-cap` fallback has to be treated as a true last resort. Otherwise nearly-flat local cells near a ridge still look "supported" in the sidecar metadata while the geometry itself contradicts that support by staying flat.
- This change is narrower than deleting the flat-cap path outright: genuinely unmatched flat cells can still fall back, but only when no ridge/eave plane actually explains them.

## 2026-04-21 — Clean ceilings: flat cells cannot create a new ridge/eave family on their own

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — reworked `_replacement_from_local_cells(...)` so ridge/eave mode proceeds in two phases: `(1)` choose surviving candidate families only from true slanted local cells, then `(2)` allow flat cells to be absorbed only into those already-supported families. Flat cells can no longer introduce a second oblique family by themselves.
- `tests/test_noisy_slanted_ceiling_replacement.py` — renamed and tightened the ridge/eave flat-cell regression to assert that flat cells do not create a new plane family and that the result stays `single-oblique` rather than fragmenting into unsupported extra oblique pieces.
- `reports/noisy_slanted_ceilings/{per_room.csv,replacement_polygons.json,summary.json}` — regenerated after the family-survival fix.

**Why**
The previous patch removed the synthetic `flat-cap`, but it still let nearly-flat cells vote for a different shallow ridge/eave plane and emit nonsense extra roof fragments inside the room. That preserved the wrong semantics in a new form: the room no longer had a flat patch, but it still had an unsupported second roof family created only from flat raw evidence. The specific failure case was `5c557e06-393e-466e-a957-f7391b76b8ff`, story `0`, room `1`, where the bogus pieces `clean-ceiling::0:1:oblique:2` and `:oblique:3` came entirely from flat cells being assigned to the opposite ridge/eave group.

**Result**
- Focused validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**23/23**).
- Full validation: `python -m pytest tests/` passes (**299/299**).
- Corpus rerun: `python scripts/audit_noisy_slanted_ceiling_replacement.py`
  - noisy-slanted rooms: **521**
  - rooms with a clean replacement: **495**
  - mixed reconstructions: **250**
  - buildings with replacements: **119**
  - replacement source remains **490 ridge-eave-plane-group** + **5 room-partitions**
- The reported room `5c557e06-393e-466e-a957-f7391b76b8ff`, story `0`, room `1` now emits:
  - `replacement_mode=single-oblique`
  - `replacement_selection_mode=local-vector-overlap`
  - `local_supported_slanted_area_ratio=1.0`
  - `local_flat_support_area_m2=0.0`
  - only two `oblique` clean-ceiling pieces (`:oblique:0`, `:oblique:1`), both from the same ridge/eave plane group

**Learnings**
- “Use ridge/eave planes for all cells” is too broad if family admission is not also constrained. The physically meaningful rule is: only slanted evidence is allowed to decide which roof families survive; flatter cells may be explained by those families, but they cannot mint new ones.
- This fixes the exact nonsense case the user pointed out without reverting to synthetic flat caps or to global room-wide winner picking.

## 2026-04-21 — Clean ceilings: topology-filter suspicious single-oblique ridge/eave replacements

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — added a narrow topology filter for suspicious `single-oblique` clean-ceiling replacements sourced from ridge/eave plane groups. The script now computes per-room upper-story floor coverage, clips lower-story suspicious replacements to the room's top-exposed XZ region, suppresses suspicious top-story / fully covered cases, and writes explicit topology-filter metadata into both `per_room.csv` and `replacement_polygons.json`.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added focused coverage for the new cohort predicate, lower-story clipping, top-story suppression, fully covered suppression, tiny-crumb suppression, unchanged non-cohort cases, and piece-record topology metadata.
- `reconcile/viewer-main.js` — extended the clean-ceiling locator/source string so clipped replacement pieces report the topology clip note in the viewer.
- `reports/noisy_slanted_ceilings/{per_room.csv,replacement_polygons.json,summary.json}` — regenerated after the topology filter pass.

**Why**
The clean-ceiling sidecar was still emitting a narrow class of obviously wrong `single-oblique` ridge/eave replacements: low computed overlap, large azimuth disagreement, and geometry extending through interior-covered space. Building `117d172e-00d6-436e-8df2-050f25977602`, story `0`, room `4` was the concrete failure: its clean-ceiling oblique sat through the middle of a room that is mostly covered by a story-above room. The right fix was not to retune the roof pipeline, but to make the sidecar respect building topology and only survive where the room is actually top-exposed.

**Result**
- Focused validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**36/36**).
- Full validation: `python -m pytest tests/` passes (**312/312**).
- JS validation: `node --check reconcile/viewer-main.js` passes.
- Corpus rerun: `python scripts/audit_noisy_slanted_ceiling_replacement.py`
  - noisy-slanted rooms: **521**
  - rooms with a clean replacement: **483**
  - mixed reconstructions: **209**
  - topology filter applied: **7**
  - topology filter clipped: **2**
  - topology filter suppressed: **5**
  - buildings with replacements: **117**
- Building `117d172e-00d6-436e-8df2-050f25977602`, story `0`, room `4` now stays in the sidecar only as a topology-clipped replacement:
  - `topology_filter_action=clip-to-top-exposed`
  - `upper_cover_area_m2=6.608`
  - `top_exposed_area_m2=4.275`
  - the emitted clipped oblique pieces now sum to the exposed `4.275 m²` instead of painting a full-room sloped overlay
- Suspicious top-story cases are now removed instead of left as misleading roof-like overlays. Example suppressions from this run include `7153d532-16c1-45e8-b7c9-f5cd1ba5cc85`, story `1`, room `12` (`suppress-no-upper-coverage`) and `bad532ea-75de-411a-a390-77f4d6a93ff8`, story `1`, room `6` (`suppress-no-top-exposed-area`).

**Learnings**
- For this cohort, room-top topology is a stronger veto than raw ceiling fragmentation. If a suspicious sloped replacement has no upper-story cover relationship to justify a clip, the honest action is to suppress it rather than preserve a plausible-looking lie.
- The sidecar can absorb this kind of correction cleanly without destabilizing `roof_algorithms_py_results.json`, which is the right boundary for viewer/debug overlays versus core roof semantics.

## 2026-04-21 — Clean ceilings: widen suspicious single-oblique overlap gate so near-miss outliers are removed too

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — widened the suspicious `single-oblique` ridge/eave topology-filter overlap cutoff from `0.50` to `0.55`.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added a regression asserting that a `0.507` overlap / `98°` azimuth-delta room is now classified as suspicious.
- `reports/noisy_slanted_ceilings/{per_room.csv,replacement_polygons.json,summary.json}` — regenerated after the threshold widen.

**Why**
After the first topology-filter pass, the user pointed out that `117d172e-00d6-436e-8df2-050f25977602::clean-ceiling::1:6:oblique:0` was still present. Investigation showed the room was clearly the same failure class — `replacement_mode=single-oblique`, `replacement_surface_kind=ridge-eave-plane-group`, `replacement_azimuth_delta_deg=98.0` — but it missed the filter by `0.007` because its overlap was `0.507` instead of `< 0.5`. That made the first gate too brittle for near-boundary outliers.

**Result**
- Focused validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**37/37**).
- Full validation: `python -m pytest tests/` passes (**313/313**).
- Corpus rerun: `python scripts/audit_noisy_slanted_ceiling_replacement.py`
  - noisy-slanted rooms: **521**
  - rooms with a clean replacement: **482**
  - mixed reconstructions: **209**
  - topology filter applied: **9**
  - topology filter clipped: **3**
  - topology filter suppressed: **6**
  - buildings with replacements: **117**
- The reported element `117d172e-00d6-436e-8df2-050f25977602::clean-ceiling::1:6:oblique:0` is no longer present in `replacement_polygons.json`.
- Its room row now reads:
  - `has_replacement=0`
  - `topology_filter_applied=1`
  - `topology_filter_action=suppress-no-upper-coverage`
  - `replacement_overlap_ratio=0.507`
  - `replacement_azimuth_delta_deg=98.0`

**Learnings**
- A hard cutoff at `0.50` was too sharp for this cohort; the geometry signal was already bad enough that tiny overlap differences were not meaningful.
- Widening to `0.55` remained narrow in practice: it only expanded the filtered cohort from **7** to **9** rooms and removed the exact near-miss outlier the user flagged.

## 2026-04-21 — Clean ceilings: suppress bad oblique sub-pieces inside mixed oblique-plus-flat replacements

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — extended the topology filter with a narrow mixed-mode path that only targets suspicious `oblique` pieces inside `oblique-plus-flat` / `multi-oblique-flat` ridge/eave replacements. When the room has no upper-story coverage or no surviving top-exposed area, the script now drops only the `oblique` pieces and preserves any surviving `flat-cap` pieces.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added a regression asserting that a bad mixed-mode room with no upper-story coverage loses only its oblique piece while keeping its flat-cap piece, and kept `multi-oblique` rooms explicitly out of scope.
- `reports/noisy_slanted_ceilings/{per_room.csv,replacement_polygons.json,summary.json}` — regenerated after the mixed-mode suppression pass.

**Why**
The user then flagged `0b75d30e-c50c-4fc6-88ff-fce983078aa4::clean-ceiling::0:4:oblique:0`. Investigation showed it was not a `single-oblique` room, but a mixed `oblique-plus-flat` clean-ceiling replacement with the same bad support signature:
- `replacement_surface_kind=ridge-eave-plane-group`
- `replacement_overlap_ratio=0.254`
- `replacement_azimuth_delta_deg=82.4`
- `upper_cover_area_m2=0.0`

The first topology filter intentionally ignored mixed rooms, which left this bad oblique sub-piece visible even though the room still had a plausible flat-cap remainder. The correct follow-up was to suppress only the unsupported oblique sub-piece, not the entire room replacement.

**Result**
- Focused validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**42/42**).
- Full validation: `python -m pytest tests/` passes (**318/318**).
- JS validation: `node --check reconcile/viewer-main.js` passes.
- Corpus rerun: `python scripts/audit_noisy_slanted_ceiling_replacement.py`
  - noisy-slanted rooms: **442**
  - rooms with a clean replacement: **400**
  - mixed reconstructions: **172**
  - topology filter applied: **17**
  - topology filter clipped: **5**
  - topology filter suppressed: **5**
  - buildings with replacements: **113**
- The reported element `0b75d30e-c50c-4fc6-88ff-fce983078aa4::clean-ceiling::0:4:oblique:0` is no longer present in `replacement_polygons.json`.
- That room now keeps only:
  - `0b75d30e-c50c-4fc6-88ff-fce983078aa4::clean-ceiling::0:4:flat-cap:0`
  - `topology_filter_action=suppress-oblique-no-upper-coverage`
  - `has_replacement=1`

**Learnings**
- Mixed clean-ceiling rooms need piece-level topology filtering; a room-level suppress/keep decision is too coarse once a flat-cap and an unsupported sloped piece coexist.
- Keeping `multi-oblique` rooms out of this rule matters: the bad pattern here was “single bad sloped piece inside a mixed cap room,” not “all multi-piece slope reconstructions are suspect.”

## 2026-04-21 — Clean ceilings: suppress degenerate top-story multi-oblique rooms that collapse to one bad slope

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — added a narrow topology-filter predicate for `ridge-eave-plane-group` rooms reported as `multi-oblique` but geometrically collapsing to one real oblique piece plus only degenerate near-zero-area oblique crumbs. If that surviving piece is still `>= 90°` off the room’s raw slanted orientation and the room has no upper-story cover, the replacement is now suppressed entirely.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added a regression covering the degenerate `multi-oblique` top-story case, proving the room is removed rather than left as a misleading single oblique under a `multi-oblique` label.
- `reports/noisy_slanted_ceilings/{per_room.csv,replacement_polygons.json,summary.json}` — regenerated after the new degenerate-multi suppression pass.

**Why**
The user then flagged `117d172e-00d6-436e-8df2-050f25977602::clean-ceiling::1:6:oblique:0`. Inspection showed this was not a legitimate two-slope reconstruction:
- `replacement_mode=multi-oblique`
- `replacement_overlap_ratio=0.937`
- `replacement_azimuth_delta_deg=98.0`
- `upper_cover_area_m2=0.0`

But the room’s sibling piece `:oblique:1` had effectively zero XZ area, so the room was functionally “one surviving slope plus a degenerate stub,” not a real multi-oblique roof shape. That made the existing “leave multi-oblique alone” policy too permissive for this exact failure class.

**Result**
- Focused validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**43/43**).
- Full validation: `python -m pytest tests/` passes (**319/319**).
- JS validation: `node --check reconcile/viewer-main.js` passes.
- Corpus rerun: `python scripts/audit_noisy_slanted_ceiling_replacement.py`
  - noisy-slanted rooms: **442**
  - rooms with a clean replacement: **399**
  - mixed reconstructions: **172**
  - topology filter applied: **19**
  - topology filter clipped: **6**
  - topology filter suppressed: **6**
  - buildings with replacements: **113**
- The reported room `117d172e-00d6-436e-8df2-050f25977602`, story `1`, room `6` now has:
  - `has_replacement=0`
  - `topology_filter_action=suppress-degenerate-multi-no-upper-coverage`
  - no surviving entries in `replacement_polygons.json`
- The new rule stayed narrow on the current corpus: it matched only **2** rooms, including `117d172e-00d6-436e-8df2-050f25977602` and `bc2779a4-d0a2-4ba8-abbf-10129d3f82de`, both top-exposed `multi-oblique` rooms with only one non-degenerate oblique piece left.

**Learnings**
- A reported `multi-oblique` mode is not always physically meaningful; if all but one oblique piece collapse to zero-area crumbs, the room should be judged by the surviving piece rather than by the nominal mode label.
- This gives a safer extension of the topology filter than broad azimuth-based suppression for all `multi-oblique` rooms, which would have touched dozens of legitimate two-slope rooms.

## 2026-04-21 — Clean ceilings: suppress weak-support mixed oblique pieces that only survive over tiny exposed slivers

**Files changed**
- `scripts/audit_noisy_slanted_ceiling_replacement.py` — refined the mixed `oblique-plus-flat` / `multi-oblique-flat` topology filter so suspicious oblique pieces now trigger on either weak global overlap or weak local slanted support, with a slightly lower mixed-mode azimuth gate to absorb rounding drift. Added a narrow suppression path for cases where the suspicious oblique would only survive over a tiny top-exposed remainder after clipping.
- `tests/test_noisy_slanted_ceiling_replacement.py` — added regressions for:
  - mixed rooms whose oblique sub-piece should be suppressed due to weak local slanted support despite moderate room overlap
  - mixed rooms whose oblique sub-piece should be dropped because clipping leaves only a tiny exposed sliver
- `reports/noisy_slanted_ceilings/{per_room.csv,replacement_polygons.json,summary.json}` — regenerated after the mixed weak-support / tiny-sliver suppression pass.

**Why**
The user then flagged `c87c1e25-ff00-44ec-b823-b0966c81af70::clean-ceiling::0:1:oblique:0`. This room was a mixed `oblique-plus-flat` replacement where the oblique sub-piece still looked wrong even though it narrowly missed the previous filter:
- `replacement_overlap_ratio=0.731`
- `replacement_azimuth_delta_deg` rounded to `60.0`
- `local_supported_slanted_area_ratio=0.358`

On the real building topology, the room is almost entirely covered from above:
- `upper_cover_area_m2=4.753`
- `upper_cover_ratio=0.968`
- `top_exposed_area_m2=0.158`
- `top_exposed_ratio=0.032`

That meant the oblique piece only survived over a meaningless sliver after topology clipping; preserving it was not useful.

**Result**
- Focused validation: `python -m pytest tests/test_noisy_slanted_ceiling_replacement.py` passes (**45/45**).
- Full validation: `python -m pytest tests/` passes (**321/321**).
- JS validation: `node --check reconcile/viewer-main.js` passes.
- Corpus rerun: `python scripts/audit_noisy_slanted_ceiling_replacement.py`
  - noisy-slanted rooms: **442**
  - rooms with a clean replacement: **399**
  - mixed reconstructions: **172**
  - topology filter applied: **31**
  - topology filter clipped: **6**
  - topology filter suppressed: **6**
  - buildings with replacements: **113**
- The reported element `c87c1e25-ff00-44ec-b823-b0966c81af70::clean-ceiling::0:1:oblique:0` is no longer present in `replacement_polygons.json`.
- That room now keeps only flat-cap pieces:
  - `c87c1e25-ff00-44ec-b823-b0966c81af70::clean-ceiling::0:1:flat-cap:0`
  - `c87c1e25-ff00-44ec-b823-b0966c81af70::clean-ceiling::0:1:flat-cap:1`
  - `c87c1e25-ff00-44ec-b823-b0966c81af70::clean-ceiling::0:1:flat-cap:2`
  - `topology_filter_action=suppress-oblique-tiny-top-exposed`

**Learnings**
- For mixed rooms, “room overlap looks decent” is not enough if the oblique explanation itself has weak local support; the local raw slanted evidence matters more than the room-wide fit.
- When a suspicious oblique piece only clips down to a few percent of the room footprint, keeping it in the sidecar adds noise rather than useful roof context.

## 2026-04-21 — Viewer: make captured raw ceilings clickable

**Files changed**
- `reconcile/viewer-main.js` — added `groups.rawCeilings`, `groups.rawCeilingsRoles`, and `groups.rawCeilingsReconstructions` to `getVisiblePickRoots()`, so the viewer raycaster can select raw captured ceiling meshes and their prototype/reconstruction overlays.

**Why**
The viewer already attached valid `ceiling-raw` locators to captured raw ceiling meshes, but the click/right-click raycaster never considered the raw-ceiling groups. That made raw ceilings visible but impossible to select or copy IDs from in the viewer.

**Result**
- Raw captured ceilings are now eligible for normal click and right-click selection when their layers are visible.
- Validation: `node --check reconcile/viewer-main.js` passes.

**Learnings**
- In this viewer, attaching locators is not sufficient for interactivity; the mesh’s parent group must also be part of `getVisiblePickRoots()` or the raycaster will never see it.

## 2026-04-21 — Viewer: prioritize raw captured ceilings when overlapping other layers

**Files changed**
- `reconcile/viewer-main.js` — added `pickElementIntersection()` and updated both click and right-click picking to prefer `ceiling-raw` hits when a raw captured ceiling lies under the cursor alongside other visible surfaces.

**Why**
Making raw-ceiling groups pickable was necessary but not sufficient in crowded views. When raw ceilings overlapped other visible meshes, the raycaster still returned the nearest non-raw surface first, which made raw ceilings effectively unclickable in practice.

**Result**
- Clicking or right-clicking through overlapping viewer layers now picks the raw captured ceiling first when one is under the cursor.
- Validation: `node --check reconcile/viewer-main.js` passes.

**Learnings**
- In this viewer, practical pickability depends on both the pick-root set and the post-raycast hit ordering; overlapping diagnostic layers can still hide a valid locator unless the selection policy reflects the user’s inspection intent.

## 2026-04-21 — Viewer: bump bundle version so raw-ceiling click fix is loaded

**Files changed**
- `reconcile/viewer.html` — bumped the `viewer-main.js` query token so the browser fetches the updated viewer bundle instead of reusing a cached copy.

**Why**
The raw-ceiling click fix already lived in `viewer-main.js`, but `viewer.html` still referenced the old cache-busting token. That could leave the browser serving an older bundle where raw captured ceilings remained effectively unclickable.

**Result**
- Reloading `viewer.html` now fetches the updated bundle containing the raw-ceiling picking fixes.

**Learnings**
- For this viewer, UI interaction fixes are not complete until the HTML entrypoint’s cache-busting token changes; otherwise the browser can keep serving stale module code.

## 2026-04-21 — Viewer server: disable caching for local viewer assets

**Files changed**
- `reconcile/viewer_server.py` — added a `ViewerHandler.end_headers()` override that sends `Cache-Control: no-store` for local `.html`, `.js`, and `.css` viewer assets.

**Why**
Even after bumping the `viewer-main.js` token, the browser could still hang onto stale local viewer assets. That made UI fixes like raw-ceiling click handling appear to “not work” even though the JS code was already patched.

**Result**
- Local viewer HTML/JS/CSS assets are now served with `no-store`, so reloading the viewer fetches the current picker logic instead of a cached bundle.
- Validation: `python -m py_compile reconcile/viewer_server.py` passes.

**Learnings**
- For this viewer, interaction fixes need cache control at the server layer as well as cache-busting in `viewer.html`; otherwise stale local assets can mask correct code changes.
