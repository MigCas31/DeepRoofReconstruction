"""Backend resolver for shareable viewer element IDs.

Element IDs use the format:
<building_uuid>::<kind>::<id>

Two kind families are supported:

* Legacy kinds (``floor``, ``wall-merged``, ``roof-oblique``, ...) resolve
  against ``buildings_3d.json``.
* Ontology kinds (``ontology-renderable-*``, ``ontology-base-*``,
  ``ontology-knee-wall``, ``ontology-unresolved-coverage``,
  ``ontology-fallback-ceiling``) resolve against
  ``reconcile/roof_algorithms_py_results.json``. Their inner id is
  ``renderable:<category>:<source_id>`` (see
  ``reconcile/viewer_server.py:_renderable_surface_from_atom``), where
  ``source_id`` is one of:

  - a semantic atom id (``ceiling-partition:<hash>``, ``knee-wall:<hash>``, ...)
  - a cell/face composite — either a bare cell (``roof-cell:<kind>:<hash>``)
    or a face within a cell
    (``roof-cell:<kind>:<hash>:arr-face:<hash>``), resolved against
    ``roof_cell_complex.cells[*]`` and its ``.faces[*]``
  - a viewer-assembled ``roof-atom-patch:{kind}:`` prefix wrapping an
    atom id (e.g. ``roof-atom-patch:flat:ceiling-partition:<hash>``) —
    the prefix is stripped automatically during lookup.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedElementId:
    """Parsed viewer element locator token."""

    building_uuid: str
    kind: str
    element_id: str


def parse_element_id(token: str) -> ParsedElementId:
    """Parse a shareable element token.

    Expected format: ``building_uuid::kind::id``.
    """
    parts = token.strip().split("::", 2)
    if len(parts) != 3 or not all(parts):
        raise ValueError(
            "Invalid element ID. Expected format: <building_uuid>::<kind>::<id>"
        )
    return ParsedElementId(
        building_uuid=parts[0],
        kind=parts[1],
        element_id=parts[2],
    )


def _iter_room_elements(building: dict, room_key: str):
    for room_index, room in enumerate(building.get("rooms", [])):
        story = room.get("story")
        for element_index, element in enumerate(room.get(room_key, [])):
            yield room_index, story, element_index, element


def _split_wall_id_suffix(element_id: str) -> tuple[str, int | None, int | None]:
    """Split optional :<story>:<room_index> suffix appended by the full-model viewer.

    Full-model render path (viewer-main.js:1924) produces ``wall_id:story:ri``.
    Layer render path (viewer-main.js:1311) produces the bare ``wall_id``.
    Returns (wall_id, story_hint, room_index_hint); hints are None when absent.
    """
    parts = element_id.rsplit(":", 2)
    if len(parts) == 3:
        try:
            return parts[0], int(parts[1]), int(parts[2])
        except ValueError:
            pass
    return element_id, None, None


def _find_in_room_collection(
    building: dict, room_key: str, element_id: str
) -> dict | None:
    # Try exact match first (layer-mode IDs: bare wall UUID).
    # Also try stripping the :<story>:<room_index> suffix produced by the
    # full-model viewer (viewer-main.js:1924).
    bare_id, story_hint, ri_hint = _split_wall_id_suffix(element_id)
    for room_index, story, element_index, element in _iter_room_elements(
        building, room_key
    ):
        raw_id = str(element.get("id", ""))
        exact = raw_id == element_id
        stripped = raw_id == bare_id and (
            story_hint is None or story == story_hint
        ) and (
            ri_hint is None or room_index == ri_hint
        )
        if exact or stripped:
            return {
                "json_path": f"rooms[{room_index}].{room_key}[{element_index}]",
                "room_index": room_index,
                "story": story,
                "source": element.get("source"),
                "corners_count": len(element.get("corners", [])),
                "element": element,
            }
    return None


def _find_in_building_collection(
    building: dict, collection_key: str, element_id: str
) -> dict | None:
    for index, element in enumerate(building.get(collection_key, [])):
        candidate_id = element.get("id")
        if candidate_id is None:
            candidate_id = f"{element.get('type', '')}:{index}"
        if str(candidate_id) == element_id:
            return {
                "json_path": f"{collection_key}[{index}]",
                "story": element.get("story"),
                "source": element.get("source") or element.get("confidence"),
                "corners_count": len(
                    element.get("corners", [])
                    or element.get("element_corners", [])
                    or element.get("wall_corners", [])
                ),
                "element": element,
            }
    return None


def is_ontology_kind(kind: str) -> bool:
    """Return True for kinds produced by ``full-model-ontology.js``."""
    return kind.startswith("ontology-")


def is_v3_kind(kind: str) -> bool:
    """Return True for kinds produced by ``reconcile_v3``."""
    return kind.startswith("v3-")


_RECONSTRUCTION_KINDS = {
    "ceiling-reconstruction-dormer": "dormer",
    "ceiling-reconstruction-wing": "wing",
}


def is_reconstruction_kind(kind: str) -> bool:
    """Return True for Phase-2 raw-ceiling prototype reconstruction kinds."""
    return kind in _RECONSTRUCTION_KINDS


def find_reconstruction_element(
    reconstructions: dict, parsed: ParsedElementId
) -> dict:
    """Resolve a ``ceiling-reconstruction-*`` token against the sidecar JSON.

    ``reconstructions`` is the object loaded from
    ``reports/raw_ceiling_prototype/reconstructions.json``; its shape is
    ``{"buildings": {"<uuid>": {"dormer": [...], "wing": [...]}}}``.
    """
    subkey = _RECONSTRUCTION_KINDS[parsed.kind]
    by_uuid = (reconstructions.get("buildings") or {}).get(parsed.building_uuid)
    if not by_uuid:
        raise LookupError(
            f"No reconstructions for building {parsed.building_uuid}. "
            "Run the prototype scripts under scripts/prototype_*.py."
        )
    pieces = by_uuid.get(subkey) or []
    token = f"{parsed.building_uuid}::{parsed.kind}::{parsed.element_id}"
    for idx, piece in enumerate(pieces):
        if piece.get("element_id") == token:
            corners = piece.get("corners") or []
            return {
                "building_uuid": parsed.building_uuid,
                "kind": parsed.kind,
                "id": parsed.element_id,
                "json_path": f"buildings[{parsed.building_uuid}].{subkey}[{idx}]",
                "room_index": piece.get("room_index"),
                "story": piece.get("story"),
                "source": piece.get("piece_role"),
                "corners_count": len(corners),
                "element": piece,
            }
    raise LookupError(
        f"Reconstruction piece not found: {token}. The sidecar may be stale — "
        "rerun scripts/prototype_dormer_reconstruction.py / "
        "prototype_wing_reconstruction.py."
    )


_V3_COLLECTION_BY_KIND: dict[str, str] = {
    "v3-part": "parts",
    "v3-gap": "gaps",
    "v3-slab": "slabs",
    "v3-wall-extension": "wall_extensions",
    "v3-flat-ceiling": "flat_ceilings",
    "v3-slanted-roof": "slanted_roofs",
    "v3-roof-proposal": "roof_proposals",
    "v3-merged-roof-segment": "merged_roof_segments",
    "v3-dormer": "dormers",
    "v3-unresolved": "unresolved",
}

_V3_GABLE_KINDS = {"v3-gable-status", "v3-gable-ridge", "v3-gable-extension-target"}


def find_v3_element(v3_results_for_uuid: dict, parsed: ParsedElementId) -> dict:
    """Resolve a ``v3-*`` element ID against reconcile_v3_results.json."""
    if parsed.kind in _V3_GABLE_KINDS:
        return _find_v3_gable_element(v3_results_for_uuid, parsed)
    collection_key = _V3_COLLECTION_BY_KIND.get(parsed.kind)
    if collection_key is None:
        raise LookupError(f"Unknown v3 kind: {parsed.kind}")
    collection = v3_results_for_uuid.get(collection_key) or []
    token = f"{parsed.building_uuid}::{parsed.kind}::{parsed.element_id}"
    for idx, element in enumerate(collection):
        if element.get("id") == token:
            audit_entries = [
                entry
                for entry in (v3_results_for_uuid.get("audit_log") or [])
                if entry.get("element_id") == token
            ]
            return {
                "building_uuid": parsed.building_uuid,
                "kind": parsed.kind,
                "id": parsed.element_id,
                "json_path": f"{collection_key}[{idx}]",
                "element": element,
                "audit": audit_entries,
            }
    raise LookupError(
        f"v3 element not found for kind='{parsed.kind}' id='{parsed.element_id}'"
    )


def _find_v3_gable_element(
    v3_results_for_uuid: dict, parsed: ParsedElementId
) -> dict:
    """Resolve gable decorations — all carry the part's inner id (e.g. ``part-0``)."""
    part_token = f"{parsed.building_uuid}::v3-part::{parsed.element_id}"
    parts = v3_results_for_uuid.get("parts") or []
    for idx, part in enumerate(parts):
        if part.get("id") != part_token:
            continue
        gable = part.get("gable_extension")
        if gable is None:
            raise LookupError(
                f"Part {parsed.element_id} has no gable_extension record"
            )
        audit_token = f"{part_token}::gable"
        audit_entries = [
            entry
            for entry in (v3_results_for_uuid.get("audit_log") or [])
            if entry.get("element_id") == audit_token
        ]
        return {
            "building_uuid": parsed.building_uuid,
            "kind": parsed.kind,
            "id": parsed.element_id,
            "json_path": f"parts[{idx}].gable_extension",
            "element": gable,
            "audit": audit_entries,
        }
    raise LookupError(
        f"v3 gable element not found for kind='{parsed.kind}' id='{parsed.element_id}'"
    )


# Maps ontology kind -> (file:line, note) list of thresholds that influenced
# surfaces of this kind. Cited locations are authoritative constants only —
# keep in sync with the source files when constants move.
KIND_THRESHOLDS: dict[str, list[tuple[str, str]]] = {
    "ontology-renderable-ceiling": [
        (
            "reconcile/roof_algorithms_py/roof_partitioning.py:22-23",
            "ROOM_TOP_MIN_CLEARANCE_M=0.15, ROOM_TOP_SHELL_TOL_M=0.08",
        ),
        (
            "reconcile/roof_algorithms_py/thermal_ceiling.py:551",
            "THRESHOLD_M=0.30 (knee-wall gap)",
        ),
        (
            "reconcile/roof_algorithms_py/oblique_clustering.py:19-20",
            "COPLANAR_TOL=0.5m, Δazimuth=30°, Δinclination=15°, MIN_CLUSTER_SIZE=2",
        ),
        (
            "reconcile/roof_algorithms_py/simple_slant.py:21",
            "_AZIMUTH_MULTI_THRESHOLD=90° (simple-slant fallback)",
        ),
    ],
    "ontology-renderable-roof": [
        (
            "reconcile/roof_algorithms_py/oblique_clustering.py:19-20",
            "COPLANAR_TOL=0.5m, Δazimuth=30°, Δinclination=15°",
        ),
        (
            "reconcile/roof_algorithms_py/roof_envelope_continuation.py:17",
            "MAX_CONTINUATION_DISTANCE_M=4.0",
        ),
        (
            "reconcile/roof_algorithms_py/roof_partitioning.py:22-23",
            "ROOM_TOP_MIN_CLEARANCE_M=0.15, ROOM_TOP_SHELL_TOL_M=0.08",
        ),
    ],
    "ontology-knee-wall": [
        (
            "reconcile/roof_algorithms_py/thermal_ceiling.py:551",
            "THRESHOLD_M=0.30",
        ),
        (
            "reconcile/roof_algorithms_py/roof_partitioning.py:22-23",
            "ROOM_TOP_* tolerances",
        ),
    ],
    "ontology-unresolved-coverage": [
        (
            "reconcile/roof_algorithms_py/roof_coverage_graph.py:15",
            "SEED_ROOM_BUFFER_M=0.75",
        ),
    ],
    "ontology-fallback-ceiling": [
        (
            "reconcile/roof_algorithms_py/simple_slant.py:21",
            "_AZIMUTH_MULTI_THRESHOLD=90° (simple-slant fallback)",
        ),
        (
            "reconcile/roof_algorithms_py/roof_partitioning.py:22-23",
            "ROOM_TOP_* tolerances",
        ),
    ],
    "ontology-base-exterior-wall": [],
    "ontology-base-interior-wall": [],
    "ontology-base-floor": [],
    "ontology-base-ceiling": [],
    "ontology-renderable-wall": [],
    "ontology-renderable-room-wall": [],
    "ontology-renderable-floor": [],
    "ontology-base-window": [],
    "ontology-base-door": [],
    "ontology-base-opening": [],
}


# Maps atom id prefix -> (file, human description). Used by --trace to point at
# the pipeline step that minted an atom given its id.
ATOM_PREFIX_TO_STEP: dict[str, tuple[str, str]] = {
    "ceiling-partition:": (
        "reconcile/roof_algorithms_py/roof_partitioning.py",
        "derive_room_ceiling_partitions / flat+oblique/simple-slant partitioning",
    ),
    "knee-wall:": (
        "reconcile/roof_algorithms_py/thermal_ceiling.py",
        "knee-wall detection",
    ),
    "implicit-flat-atom:": (
        "reconcile/roof_algorithms_py/occupied_room_cell_complex.py",
        "implicit flat attic / remainder cell synthesis",
    ),
    "occupied-cell:": (
        "reconcile/roof_algorithms_py/occupied_room_cell_complex.py",
        "occupied-room cell complex build",
    ),
    "boundary:": (
        "reconcile/roof_algorithms_py/boundary_model.py",
        "space-boundary assignment (IFC-style)",
    ),
    "face:": (
        "reconcile/roof_algorithms_py/boundary_model.py",
        "boundary face id (top shell surface)",
    ),
    "edge:occupied-atom:": (
        "reconcile/roof_algorithms_py/occupied_room_cell_complex.py",
        "occupied cell ↔ atom edge",
    ),
    "edge:atom-room:": (
        "reconcile/roof_algorithms_py/top_boundary_graph.py",
        "top-boundary atom ↔ room edge",
    ),
    "roof-atom-patch:": (
        "reconcile/viewer_server.py",
        "flat/oblique ceiling-partition atom emitted as exterior_roof patch "
        "(viewer-assembled; strip roof-atom-patch:{kind}: to get the atom id)",
    ),
    "roof-cell:": (
        "reconcile/roof_algorithms_py/roof_cell_complex.py",
        "arranged polyhedral roof cell (attic/upper_void) and its per-face "
        "arrangement (arr-face:<hash>). Composite source_id is "
        "<cell_id>[:arr-face:<face_hash>].",
    ),
}


_FACE_PREFIXES: tuple[str, ...] = ("arr-face:",)


def _split_roof_cell_composite(source_id: str) -> tuple[str, str | None] | None:
    """Parse ``roof-cell:<kind>:<hash>[:arr-face:<face_hash>]``.

    Returns ``(cell_id, face_id)`` — ``face_id`` is ``None`` for bare
    cell references. Returns ``None`` when ``source_id`` isn't a
    roof-cell composite.
    """
    if not source_id.startswith("roof-cell:"):
        return None
    for prefix in _FACE_PREFIXES:
        sep = f":{prefix}"
        idx = source_id.find(sep)
        if idx != -1:
            return source_id[:idx], source_id[idx + 1 :]
    return source_id, None


def _resolve_roof_cell_source(
    roof_results_for_uuid: dict, source_id: str
) -> dict | None:
    """Resolve a cell/face composite against ``roof_cell_complex.cells``.

    Returns a dict with ``atom`` (the face dict, or the cell when no face
    suffix is present), ``provenance_paths``, and ``parent_cell`` metadata
    — or ``None`` if ``source_id`` doesn't match the composite shape or
    isn't present in the cell complex.
    """
    split = _split_roof_cell_composite(source_id)
    if split is None:
        return None
    cell_id, face_id = split
    cells = (roof_results_for_uuid.get("roof_cell_complex") or {}).get("cells") or []
    for cell_idx, cell in enumerate(cells):
        if str(cell.get("id")) != cell_id:
            continue
        parent_cell = {
            "id": cell.get("id"),
            "cell_kind": cell.get("cell_kind"),
            "room_id": cell.get("room_id"),
            "room_index": cell.get("room_index"),
            "story": cell.get("story"),
            "part_id": cell.get("part_id"),
            "base_atom_id": cell.get("base_atom_id"),
            "roof_hypothesis_id": cell.get("roof_hypothesis_id"),
            "roof_surface_kind": cell.get("roof_surface_kind"),
            "volume_m3": cell.get("volume_m3"),
            "bbox_xyz": cell.get("bbox_xyz"),
        }
        if face_id is None:
            return {
                "atom": cell,
                "provenance_paths": [f"roof_cell_complex.cells[{cell_idx}]"],
                "parent_cell": parent_cell,
            }
        for face_idx, face in enumerate(cell.get("faces") or []):
            if str(face.get("id")) != face_id:
                continue
            return {
                "atom": face,
                "provenance_paths": [
                    f"roof_cell_complex.cells[{cell_idx}].faces[{face_idx}]"
                ],
                "parent_cell": parent_cell,
            }
        return None
    return None


def _parse_renderable_element_id(element_id: str) -> dict | None:
    """Split ``renderable:<category>:<source_id>`` into its parts.

    ``source_id`` may itself contain colons (atom IDs like
    ``ceiling-partition:<hash>``), so we only split the first two ``:``.
    """
    parts = element_id.split(":", 2)
    if len(parts) != 3 or parts[0] != "renderable":
        return None
    return {"category": parts[1], "source_id": parts[2]}


def _atom_step_for(source_id: str) -> tuple[str, str] | None:
    for prefix, step in ATOM_PREFIX_TO_STEP.items():
        if source_id.startswith(prefix):
            return step
    return None


def find_ontology_element(
    roof_results_for_uuid: dict,
    parsed: ParsedElementId,
) -> dict:
    """Resolve an ``ontology-*`` element ID against a per-building roof result.

    ``roof_results_for_uuid`` is the value from
    ``roof_algorithms_py_results.json`` indexed by building UUID.
    """
    info = _parse_renderable_element_id(parsed.element_id)
    if info is None:
        raise LookupError(
            f"Ontology element id '{parsed.element_id}' is not in "
            "'renderable:<category>:<source_id>' form"
        )
    source_id = info["source_id"]
    # viewer_server.py assembles roof-atom-patch:{kind}:{atom_id} ids at HTTP
    # time; strip the prefix to get the underlying atom id for JSON lookups.
    atom_id = source_id
    if source_id.startswith("roof-atom-patch:"):
        _, _, atom_id = source_id.split(":", 2)
    atom: dict | None = None
    provenance_paths: list[str] = []
    parent_cell: dict | None = None

    cell_resolution = _resolve_roof_cell_source(roof_results_for_uuid, atom_id)
    if cell_resolution is not None:
        atom = cell_resolution["atom"]
        provenance_paths.extend(cell_resolution["provenance_paths"])
        parent_cell = cell_resolution["parent_cell"]

    ceiling_partitions = roof_results_for_uuid.get("ceiling_partitions", {}) or {}
    for subkind in ("oblique", "flat"):
        for idx, part in enumerate(ceiling_partitions.get(subkind, []) or []):
            if str(part.get("id", "")) == atom_id:
                atom = atom or part
                provenance_paths.append(
                    f"ceiling_partitions.{subkind}[{idx}]"
                )
    for idx, rp in enumerate(ceiling_partitions.get("room_partitions", []) or []):
        for p_idx, part in enumerate(rp.get("partitions", []) or []):
            if str(part.get("id", "")) == atom_id:
                atom = atom or part
                provenance_paths.append(
                    f"ceiling_partitions.room_partitions[{idx}].partitions[{p_idx}]"
                )

    for idx, kw in enumerate(roof_results_for_uuid.get("knee_walls", []) or []):
        if str(kw.get("id", "")) == atom_id:
            atom = atom or kw
            provenance_paths.append(f"knee_walls[{idx}]")

    atom_evidence_map = (
        (roof_results_for_uuid.get("roof_evidence_graph", {}) or {}).get(
            "atom_evidence", {}
        )
        or {}
    )
    evidence = atom_evidence_map.get(atom_id)
    if evidence is not None:
        provenance_paths.append(f"roof_evidence_graph.atom_evidence[{atom_id}]")

    # Mirror viewer_server.py: build partition_by_id from room_partitions so
    # the TBG node (which carries role/roof_hypothesis_id) can be enriched with
    # the stored polygon geometry.
    _partition_by_id: dict[str, dict] = {}
    for _rp in ceiling_partitions.get("room_partitions", []) or []:
        for _part in (_rp.get("partitions") or []):
            _pid = str(_part.get("id") or "")
            if _pid:
                _partition_by_id[_pid] = _part

    top_boundary = roof_results_for_uuid.get("top_boundary_graph", {}) or {}
    for idx, node in enumerate(top_boundary.get("nodes", []) or []):
        if not isinstance(node, dict) or str(node.get("id", "")) != atom_id:
            continue
        # Use the TBG node as the authoritative atom (it carries role,
        # roof_hypothesis_id, flat_role, etc.) and fill in geometry from the
        # matching room_partition entry — exactly what viewer_server.py does
        # when assembling semantic_atoms.
        if node.get("type") == "TopBoundaryAtom":
            merged = dict(node)
            _partition = _partition_by_id.get(atom_id) or {}
            merged["poly"] = _partition.get("poly") or merged.get("poly") or []
            merged["top_y_m"] = (
                _partition.get("top_y_m")
                if "top_y_m" not in node
                else node["top_y_m"]
            )
            atom = merged
        provenance_paths.append(f"top_boundary_graph.nodes[{idx}]")

    if atom is None and not provenance_paths:
        raise LookupError(
            f"Ontology source '{source_id}' not found in roof results for "
            f"building {parsed.building_uuid}. The results file may be stale "
            f"(hash changed after the ID was captured — try rerunning the "
            f"pipeline for this building). If this is a viewer-assembled "
            "composite id not yet handled by the locator, fetch the live "
            "payload with "
            "'curl http://127.0.0.1:8080/ontology-artifacts?uuid=<uuid>&view=full-model'."
        )

    return {
        "building_uuid": parsed.building_uuid,
        "kind": parsed.kind,
        "id": parsed.element_id,
        "category": info["category"],
        "source_id": source_id,
        "atom": atom,
        "provenance_paths": provenance_paths,
        "evidence": evidence,
        "parent_cell": parent_cell,
    }


def build_trace(result: dict) -> dict:
    """Attach threshold and pipeline-step hints to an ontology resolution."""
    kind = result.get("kind", "")
    thresholds = [
        {"location": loc, "note": note}
        for loc, note in KIND_THRESHOLDS.get(kind, [])
    ]
    step_info = None
    source_id = result.get("source_id", "")
    if source_id:
        # Unwrap viewer-assembled prefix before step lookup so we point at the
        # pipeline step that minted the atom, not viewer_server.py.
        step_source_id = source_id
        if source_id.startswith("roof-atom-patch:"):
            _, _, step_source_id = source_id.split(":", 2)
        hit = _atom_step_for(step_source_id)
        if hit is not None:
            step_info = {"file": hit[0], "description": hit[1]}
    return {
        **result,
        "thresholds": thresholds,
        "pipeline_step": step_info,
    }


def find_element(
    buildings: list[dict],
    token: str,
    *,
    roof_results: dict | None = None,
    v3_results: list[dict] | None = None,
    reconstructions: dict | None = None,
) -> dict:
    """Resolve a viewer token to an element in buildings_3d-like data.

    ``roof_results`` (contents of ``roof_algorithms_py_results.json``) is
    required for ``ontology-*`` kinds. ``v3_results`` (contents of
    ``reconcile_v3_results.json``, a list of per-building dicts) is
    required for ``v3-*`` kinds. ``reconstructions`` (contents of
    ``reports/raw_ceiling_prototype/reconstructions.json``) is required
    for ``ceiling-reconstruction-*`` kinds.
    """
    parsed = parse_element_id(token)

    if is_reconstruction_kind(parsed.kind):
        if reconstructions is None:
            raise LookupError(
                f"Reconstruction kind '{parsed.kind}' requires reconstructions "
                "sidecar; pass reconstructions=... or use --reconstructions on "
                "the CLI."
            )
        return find_reconstruction_element(reconstructions, parsed)

    if is_ontology_kind(parsed.kind):
        if roof_results is None:
            raise LookupError(
                f"Ontology kind '{parsed.kind}' requires roof_algorithms_py_results.json; "
                "pass roof_results=... or use --roof-results on the CLI."
            )
        per_uuid = roof_results.get(parsed.building_uuid)
        if per_uuid is None:
            raise LookupError(
                f"Building {parsed.building_uuid} not found in roof results"
            )
        return find_ontology_element(per_uuid, parsed)

    if is_v3_kind(parsed.kind):
        if v3_results is None:
            raise LookupError(
                f"v3 kind '{parsed.kind}' requires reconcile_v3_results.json; "
                "pass v3_results=... or use --v3-results on the CLI."
            )
        per_uuid = next(
            (b for b in v3_results if b.get("building_uuid") == parsed.building_uuid),
            None,
        )
        if per_uuid is None:
            raise LookupError(
                f"Building {parsed.building_uuid} not found in v3 results"
            )
        return find_v3_element(per_uuid, parsed)

    building = next(
        (b for b in buildings if b.get("uuid") == parsed.building_uuid),
        None,
    )
    if building is None:
        raise LookupError(f"Building not found: {parsed.building_uuid}")

    room_kind_to_key = {
        "wall-merged": "walls_merged",
        "wall-computed": "walls_computed",
        "wall-extension": "walls_computed",
        "door": "doors",
        "window": "windows",
        "wall-clipped-original": "walls_computed",
    }
    building_kind_to_key = {
        "gap-cross-story": "cross_floor_gaps",
        "gap-within-story": "cross_floor_gaps",
        "wall-stitch": "stitch_walls",
        "gap-wall": "gap_walls",
        "exterior-gap-element": "exterior_gap_indicators",
        "exterior-gap-wall": "exterior_gap_indicators",
        "gap-closure": "gap_closures",
    }
    roof_kind_to_path: dict[str, tuple[str, str]] = {
        "roof-oblique": ("roof_surfaces", "oblique"),
        "roof-flat": ("roof_surfaces", "flat"),
        "ceiling-flat": ("ceiling", "flat"),
        "ceiling-simple-slant": ("ceiling", "simple_slant"),
    }

    details: dict | None = None
    if parsed.kind == "floor" or parsed.kind == "floor-overlap":
        try:
            story_str, room_index_str = parsed.element_id.split(":", 1)
            room_index = int(room_index_str)
            room = building.get("rooms", [])[room_index]
            key = (
                "floor_overlap_region"
                if parsed.kind == "floor-overlap"
                else "floor_polygon"
            )
            corners = room.get(key, [])
            details = {
                "json_path": f"rooms[{room_index}].{key}",
                "room_index": room_index,
                "story": int(story_str),
                "source": key,
                "corners_count": len(corners),
                "element": {"id": parsed.element_id, "corners": corners},
            }
        except (ValueError, IndexError, KeyError):
            details = None
    elif parsed.kind in room_kind_to_key:
        details = _find_in_room_collection(
            building, room_kind_to_key[parsed.kind], parsed.element_id
        )
    elif parsed.kind in building_kind_to_key:
        details = _find_in_building_collection(
            building, building_kind_to_key[parsed.kind], parsed.element_id
        )
    elif parsed.kind in roof_kind_to_path:
        section, subsection = roof_kind_to_path[parsed.kind]
        try:
            # ID format: "<sub_kind>:<index>" e.g. "oblique:0"
            _, idx_str = parsed.element_id.rsplit(":", 1)
            idx = int(idx_str)
            items = building.get(section, {}).get(subsection, [])
            element = items[idx]
            corners = element.get("corners") or element.get("poly", [])
            details = {
                "json_path": f"{section}.{subsection}[{idx}]",
                "room_index": None,
                "story": element.get("story") or element.get("dominant_story"),
                "source": parsed.kind,
                "corners_count": len(corners),
                "element": element,
            }
        except (ValueError, IndexError, KeyError):
            details = None

    elif parsed.kind in ("dormer-cheek", "dormer-header"):
        try:
            parts = parsed.element_id.split(":")
            dormer_idx = int(parts[1])
            dormers = building.get("dormers", [])
            dormer = dormers[dormer_idx]
            if parsed.kind == "dormer-cheek":
                cheek_idx = int(parts[2])
                element = dormer["cheeks"][cheek_idx]
            else:
                element = dormer["header"]
            corners = element.get("corners", [])
            details = {
                "json_path": f"dormers[{dormer_idx}].{parsed.kind.split('-')[1]}",
                "room_index": dormer.get("room_index"),
                "story": None,
                "source": parsed.kind,
                "corners_count": len(corners),
                "element": element,
            }
        except (ValueError, IndexError, KeyError):
            details = None

    if details is None:
        raise LookupError(
            f"Element not found for kind='{parsed.kind}' and id='{parsed.element_id}'"
        )

    return {
        "building_uuid": building.get("uuid"),
        "building_address": building.get("address"),
        "kind": parsed.kind,
        "id": parsed.element_id,
        **details,
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve shareable viewer element IDs. Legacy kinds resolve from "
            "buildings_3d.json; ontology-* kinds resolve from "
            "roof_algorithms_py_results.json."
        )
    )
    parser.add_argument(
        "--buildings-json",
        type=Path,
        default=Path("reconcile/buildings_3d.json"),
        help="Path to buildings_3d.json (default: reconcile/buildings_3d.json)",
    )
    parser.add_argument(
        "--roof-results",
        type=Path,
        default=Path("reconcile/roof_algorithms_py_results.json"),
        help="Path to roof_algorithms_py_results.json (needed for ontology kinds)",
    )
    parser.add_argument(
        "--v3-results",
        type=Path,
        default=Path("reconcile/reconcile_v3_results.json"),
        help="Path to reconcile_v3_results.json (needed for v3-* kinds)",
    )
    parser.add_argument(
        "--reconstructions",
        type=Path,
        default=Path("reports/raw_ceiling_prototype/reconstructions.json"),
        help=(
            "Path to reports/raw_ceiling_prototype/reconstructions.json "
            "(needed for ceiling-reconstruction-* kinds)"
        ),
    )
    parser.add_argument(
        "--element-id",
        required=True,
        help="Element token in format <building_uuid>::<kind>::<id>",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help=(
            "Enrich the result with threshold citations and the pipeline step "
            "that produced the atom."
        ),
    )
    args = parser.parse_args()

    parsed = parse_element_id(args.element_id)
    if is_reconstruction_kind(parsed.kind):
        reconstructions = json.loads(args.reconstructions.read_text())
        result = find_element(
            [], args.element_id, reconstructions=reconstructions
        )
    elif is_ontology_kind(parsed.kind):
        roof_results = json.loads(args.roof_results.read_text())
        result = find_element(
            [], args.element_id, roof_results=roof_results
        )
    elif is_v3_kind(parsed.kind):
        v3_results = json.loads(args.v3_results.read_text())
        result = find_element(
            [], args.element_id, v3_results=v3_results
        )
    else:
        buildings = json.loads(args.buildings_json.read_text())
        result = find_element(buildings, args.element_id)

    if args.trace and is_ontology_kind(parsed.kind):
        result = build_trace(result)

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
