from __future__ import annotations

from collections import defaultdict
from typing import Any

from .graph_utils import room_key as _room_key
from .graph_utils import stable_hash as _stable_hash


def build_top_boundary_graph(
    *,
    room_records: list[dict[str, Any]],
    room_partitions: list[dict[str, Any]],
    building_part_graph: dict[str, Any],
    roof_coverage_graph: dict[str, Any] | None = None,
    roof_cell_complex: dict[str, Any] | None = None,
    roof_evidence_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    room_data_by_id = {
        _room_key(int(room["room_index"])): room
        for room in room_records
    }
    part_nodes = {
        node["id"]: node
        for node in (building_part_graph.get("nodes") or [])
    }
    room_membership = building_part_graph.get("room_membership") or {}
    coverage_room_subparts = (roof_coverage_graph or {}).get("room_subpart_membership") or {}
    coverage_atom_subparts = (roof_coverage_graph or {}).get("atom_subpart_membership") or {}
    evidence_by_atom = (roof_evidence_graph or {}).get("atom_evidence") or {}
    evidence_by_room = (roof_evidence_graph or {}).get("room_evidence") or {}

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    room_summaries: dict[str, dict[str, Any]] = {}
    node_ids: set[str] = set()
    exact_cells = (roof_cell_complex or {}).get("cells") or []
    exact_edges = (roof_cell_complex or {}).get("edges") or []
    exact_cells_by_id = {
        str(cell["id"]): cell
        for cell in exact_cells
        if isinstance(cell, dict)
    }
    coverage_by_atom = (roof_coverage_graph or {}).get("atom_coverage") or {}
    exact_cells_by_atom = defaultdict(list)
    for edge in exact_edges:
        if edge.get("type") != "BOUNDS_CELL":
            continue
        atom_id = str(edge.get("from"))
        cell_id = str(edge.get("to"))
        cell = exact_cells_by_id.get(cell_id)
        if cell is not None:
            exact_cells_by_atom[atom_id].append(cell)

    for room_partition in room_partitions:
        room_id = _room_key(int(room_partition["room_index"]))
        room_data = room_data_by_id.get(room_id) or {}
        slant_delta = float(room_data.get("wallTopY", 0.0) - room_data.get("wallTopMin", 0.0))
        room_part_ids = room_membership.get(room_id, [])
        part = part_nodes.get(room_part_ids[0]) if room_part_ids else None
        part_family = str((part or {}).get("roof_family_guess", "unknown"))
        room_part_families = {
            str((part_nodes.get(part_id) or {}).get("roof_family_guess", "unknown"))
            for part_id in room_part_ids
            if part_id in part_nodes
        }
        room_evidence = evidence_by_room.get(room_id) or {}
        atom_roles: list[str] = []
        has_oblique_atom = any(partition.get("kind") == "oblique" for partition in room_partition.get("partitions") or [])

        for partition in room_partition.get("partitions") or []:
            atom_id = str(partition["id"])
            kind = str(partition.get("kind", "flat"))
            flat_role = str(partition.get("flat_role") or "")
            flat_role_reason = str(partition.get("flat_role_reason") or "")
            coverage = coverage_by_atom.get(atom_id) or {}
            atom_evidence = evidence_by_atom.get(atom_id) or {}
            sloped_state = str(coverage.get("sloped_state", "none"))
            cell_kinds = {
                str(cell.get("cell_kind"))
                for cell in exact_cells_by_atom.get(atom_id, [])
            }
            if kind == "oblique":
                role = "sloped_ceiling"
                reason = "oblique_partition_atom"
            else:
                if "attic" in cell_kinds:
                    role = "attic_floor"
                    reason = "exact_attic_cell_above_flat_atom"
                elif "upper_void" in cell_kinds:
                    role = "flat_transition_cap"
                    reason = "exact_upper_void_cell_above_flat_atom"
                elif (
                    str(sloped_state) in {"confirmed", "partial"}
                    and bool(room_evidence.get("strong_upper_void_context"))
                    and (
                        bool(atom_evidence.get("flat_cap_under_slope"))
                        or bool(room_evidence.get("knee_wall_count", 0))
                        or bool(room_evidence.get("upper_void_cell_count", 0))
                    )
                ):
                    role = "flat_transition_cap_inferred"
                    reason = "evidence_supported_upper_void_without_exact_cell"
                elif (
                    str(sloped_state) in {"confirmed", "partial"}
                    and not has_oblique_atom
                    and (
                        bool(room_evidence.get("strong_attic_context"))
                        or (
                            bool(atom_evidence.get("flat_cap_under_slope"))
                            and not bool(room_evidence.get("strong_upper_void_context"))
                        )
                    )
                ):
                    role = "attic_floor_inferred"
                    reason = "evidence_supported_attic_without_exact_cell"
                elif sloped_state in {"confirmed", "partial"}:
                    if has_oblique_atom:
                        role = "flat_transition_cap_candidate"
                        reason = "flat_atom_covered_by_sloped_roof_without_exact_upper_cell"
                    else:
                        role = "attic_floor_candidate"
                        reason = "flat_atom_covered_by_sloped_roof_without_exact_upper_cell"
                elif flat_role == "ceiling_cap":
                    if has_oblique_atom:
                        role = "flat_transition_cap"
                        reason = "flat_cap_within_mixed_room"
                    elif bool(room_evidence.get("strong_attic_context")):
                        role = "attic_floor_candidate"
                        reason = "flat_cap_without_exact_upper_cell"
                    else:
                        role = "flat_ceiling"
                        reason = "unsupported_flat_cap_retained_as_ceiling"
                elif (
                    flat_role == "roof_flat"
                    and flat_role_reason == "selected_flat_hypothesis"
                    and sloped_state not in {"confirmed", "partial"}
                    and not has_oblique_atom
                    and not bool(room_evidence.get("strong_attic_context"))
                    and not bool(room_evidence.get("strong_upper_void_context"))
                    and not bool(room_evidence.get("strong_perimeter_sloped"))
                    and not bool(room_evidence.get("strong_knee_wall_signal"))
                ):
                    role = "flat_ceiling"
                    reason = "selected_flat_hypothesis_without_sloped_context"
                elif flat_role == "ambiguous_flat_over_sloped_part":
                    if (
                        sloped_state not in {"confirmed", "partial"}
                        and not has_oblique_atom
                        and not bool(room_evidence.get("strong_attic_context"))
                        and not bool(room_evidence.get("strong_upper_void_context"))
                        and not bool(room_evidence.get("strong_perimeter_sloped"))
                        and not bool(room_evidence.get("strong_knee_wall_signal"))
                        and not coverage_atom_subparts.get(atom_id)
                        and not atom_evidence.get("sloped_context")
                        and not atom_evidence.get("flat_cap_under_slope")
                        and not cell_kinds
                    ):
                        role = "flat_ceiling"
                        reason = "ambiguous_flat_without_local_sloped_support"
                    elif slant_delta >= 0.6 and not has_oblique_atom:
                        role = "attic_floor_candidate"
                        reason = "flat_atom_in_sloped_part_without_local_oblique_atom"
                    else:
                        role = "flat_ceiling"
                        reason = "ambiguous_flat_atom_retained_as_ceiling"
                elif (
                    part_family == "gable_or_multi_slope"
                    and slant_delta >= 0.6
                    and not has_oblique_atom
                    and bool(room_evidence.get("strong_upper_void_context"))
                    and not bool(room_evidence.get("strong_attic_context"))
                ):
                    role = "flat_transition_cap_inferred"
                    reason = "strong_upper_void_room_in_sloped_part"
                elif part_family == "gable_or_multi_slope" and slant_delta >= 0.6 and not has_oblique_atom:
                    role = "attic_floor_candidate"
                    reason = "strong_slant_room_in_sloped_part"
                else:
                    role = "flat_ceiling"
                    reason = "flat_partition_atom"

            atom_roles.append(role)
            node = {
                "id": atom_id,
                "type": "TopBoundaryAtom",
                "room_id": room_id,
                "room_index": partition["room_index"],
                "story": partition["story"],
                "part_id": part["id"] if part else None,
                "roof_hypothesis_id": partition.get("roof_hypothesis_id"),
                "kind": kind,
                "role": role,
                "reason": reason,
                "area_m2": partition.get("area_m2", 0.0),
                "flat_role": partition.get("flat_role"),
                "sloped_coverage_state": sloped_state,
                "sloped_overlap_ratio": coverage.get("sloped_overlap_ratio", 0.0),
                "sloped_vertical_clearance_m": coverage.get("sloped_vertical_clearance_m"),
                "sloped_hypothesis_id": coverage.get("sloped_hypothesis_id"),
                "coverage_subpart_ids": coverage_atom_subparts.get(atom_id, []),
                "support_evidence_score": atom_evidence.get("upper_void_cell_count", 0)
                + atom_evidence.get("attic_cell_count", 0)
                + (1 if atom_evidence.get("sloped_context") else 0)
                + (1 if atom_evidence.get("flat_cap_under_slope") else 0),
            }
            nodes.append(node)
            node_ids.add(node["id"])
            edges.append(
                {
                    "id": f"edge:atom-room:{_stable_hash([atom_id, room_id], 20)}",
                    "type": "BELONGS_TO_ROOM",
                    "from": atom_id,
                    "to": room_id,
                }
            )
            if part is not None:
                edges.append(
                    {
                        "id": f"edge:atom-part:{_stable_hash([atom_id, part['id']], 20)}",
                        "type": "PART_OF",
                        "from": atom_id,
                        "to": part["id"],
                    }
                )
            hypothesis_id = partition.get("roof_hypothesis_id")
            if hypothesis_id:
                edges.append(
                    {
                        "id": f"edge:atom-hypothesis:{_stable_hash([atom_id, str(hypothesis_id)], 20)}",
                        "type": "SUPPORTED_BY",
                        "from": atom_id,
                        "to": hypothesis_id,
                    }
                )

            for cell in exact_cells_by_atom.get(atom_id, []):
                cell_id = str(cell["id"])
                if cell_id not in node_ids:
                    nodes.append(
                        {
                            "id": cell_id,
                            "type": "Cell",
                            "cell_kind": cell.get("cell_kind"),
                            "part_id": cell.get("part_id"),
                            "story": cell.get("story"),
                            "room_id": cell.get("room_id"),
                            "room_index": cell.get("room_index"),
                            "base_atom_id": cell.get("base_atom_id"),
                            "roof_hypothesis_id": cell.get("roof_hypothesis_id"),
                            "roof_surface_kind": cell.get("roof_surface_kind"),
                            "volume_m3": cell.get("volume_m3"),
                        }
                    )
                    node_ids.add(cell_id)
                edges.append(
                    {
                        "id": f"edge:atom-cell:{_stable_hash([atom_id, cell_id], 20)}",
                        "type": "BOUNDS_CELL",
                        "from": atom_id,
                        "to": cell_id,
                    }
                )
                edges.append(
                    {
                        "id": f"edge:cell-room:{_stable_hash([cell_id, room_id], 20)}",
                        "type": "ABOVE_ROOM",
                        "from": cell_id,
                        "to": room_id,
                    }
                )

        room_summaries[room_id] = {
            "room_index": room_partition["room_index"],
            "story": room_partition["story"],
            "part_ids": list(room_part_ids),
            "slant_delta_m": round(slant_delta, 6),
            "roles": sorted(set(atom_roles)),
            "has_attic_relation": any(role in {"attic_floor", "attic_floor_inferred"} for role in atom_roles),
            "has_candidate_attic_relation": any(role == "attic_floor_candidate" for role in atom_roles),
            "has_upper_void_relation": any(role in {"flat_transition_cap", "flat_transition_cap_inferred"} for role in atom_roles),
            "has_candidate_upper_void_relation": any(role == "flat_transition_cap_candidate" for role in atom_roles),
            "has_inferred_attic_relation": any(role == "attic_floor_inferred" for role in atom_roles),
            "has_inferred_upper_void_relation": any(role == "flat_transition_cap_inferred" for role in atom_roles),
            "covered_by_sloped_roof": any(
                str((coverage_by_atom.get(str(partition.get("id"))) or {}).get("sloped_state", "none")) == "confirmed"
                for partition in (room_partition.get("partitions") or [])
            ),
            "partially_covered_by_sloped_roof": any(
                str((coverage_by_atom.get(str(partition.get("id"))) or {}).get("sloped_state", "none")) in {"confirmed", "partial"}
                for partition in (room_partition.get("partitions") or [])
            ),
            "coverage_subpart_ids": list(coverage_room_subparts.get(room_id, [])),
            "has_oblique_atom": has_oblique_atom,
            "mixed": room_partition.get("mixed", False),
            "strong_perimeter_sloped": bool(room_evidence.get("strong_perimeter_sloped")),
            "strong_knee_wall_signal": bool(room_evidence.get("strong_knee_wall_signal")),
            "strong_gable_context": bool(room_evidence.get("strong_gable_context")),
            "roof_evidence_score": int(room_evidence.get("evidence_score", 0) or 0),
        }
        room_summaries[room_id]["has_resolved_roof_relation"] = bool(
            room_summaries[room_id]["has_attic_relation"]
            or room_summaries[room_id]["has_upper_void_relation"]
            or room_summaries[room_id]["has_oblique_atom"]
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "room_summaries": room_summaries,
        "metadata": {
            "atom_count": sum(1 for node in nodes if node.get("type") == "TopBoundaryAtom"),
            "exact_attic_cell_count": sum(
                1
                for node in nodes
                if node.get("type") == "Cell" and node.get("cell_kind") == "attic"
            ),
            "exact_upper_void_cell_count": sum(
                1
                for node in nodes
                if node.get("type") == "Cell" and node.get("cell_kind") == "upper_void"
            ),
        },
    }
