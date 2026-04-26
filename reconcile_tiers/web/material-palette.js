// Pascal-derived palette. Source reference: .context/pascal-editor snapshot available in this workspace on 2026-04-26.

export const MATERIAL_PALETTE = {
  structure: { name: "structure", fill: 0xf2f0ed, roughness: 0.5, metalness: 0.0 },
  structureFill: { name: "structureFill", fill: 0xf2f0ed, roughness: 0.5, metalness: 0.0 },
  floor: { name: "floor", fill: 0xe5e5e5, roughness: 1.0, metalness: 0.0 },
  roof: { name: "roof", fill: 0x808080, roughness: 0.85, metalness: 0.0 },
  doorLeaf: { name: "doorLeaf", fill: 0x8b4513, roughness: 0.7, metalness: 0.0 },
  window: { name: "window", fill: 0xadd8e6, roughness: 0.05, metalness: 0.1 },
  opening: { name: "opening", fill: 0x1a1a1a, roughness: 0.6, metalness: 0.0 },
  dormer: { name: "dormer", fill: 0xf2f0ed, roughness: 0.5, metalness: 0.0 },
};

export const MATERIAL_BY_GAP_KIND = {
  gap_floor: MATERIAL_PALETTE.floor,
  gap_ceiling: MATERIAL_PALETTE.roof,
  side: MATERIAL_PALETTE.structureFill,
  stitch: MATERIAL_PALETTE.structureFill,
  stitch_floor: MATERIAL_PALETTE.floor,
  stitch_ceiling: MATERIAL_PALETTE.roof,
  exterior_side: MATERIAL_PALETTE.structureFill,
  exterior_floor: MATERIAL_PALETTE.floor,
  exterior_ceiling: MATERIAL_PALETTE.roof,
};

export function gapMaterial(kind) {
  return MATERIAL_BY_GAP_KIND[kind] ?? MATERIAL_PALETTE.structureFill;
}
