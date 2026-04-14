export const STORY_COLORS = [
  0xff6b6b, 0x4ecdc4, 0xf7dc6f, 0xbb8fce, 0x82e0aa, 0x45b7d1,
];

export const STORY_WALL_COLORS = [
  0xcc4444, 0x339999, 0xccaa33, 0x8855aa, 0x559966, 0x338899,
];

export const ROOM_COLORS = [
  0xff6b6b, 0x4ecdc4, 0x45b7d1, 0xf7dc6f, 0xbb8fce,
  0x82e0aa, 0xf0b27a, 0xaed6f1, 0xd7bde2, 0xa3e4d7,
  0xf5b7b1, 0x85c1e9, 0xfad7a0, 0xd5f5e3, 0xe8daef,
];

export const DOOR_COLOR = 0xcc7733;
export const DOOR_EDGE = 0xff9944;
export const WINDOW_COLOR = 0x33aadd;
export const WINDOW_EDGE = 0x55ccff;
export const MERGED_COLOR = 0x4488ff;
export const MERGED_EDGE = 0x6699ff;

export const ROOF_CLUSTER_COLORS = [
  0xff4444, 0x44bbff, 0x44dd44, 0xffaa22, 0xcc44ff,
  0xff66aa, 0x22ddcc, 0xdddd22, 0x8888ff, 0xff8844,
];

export const SOURCE_COLORS = {
  'scan-cache':       { fill: 0x33cc66, edge: 0x44ee77 },
  'hybrid':           { fill: 0xccaa33, edge: 0xeebb44 },
  'merged-room':      { fill: 0x4488ff, edge: 0x6699ff },
  'scan-cache-dedup': { fill: 0x44cccc, edge: 0x55eedd },
};

export const SOURCE_LABELS = {
  'scan-cache':       'Scan (SVD)',
  'hybrid':           'Hybrid',
  'merged-room':      'Merged fallback',
  'scan-cache-dedup': 'Scan (dedup)',
};

export const LAYER_CONTROL_IDS = {
  merged: 'show-merged',
  computed: 'show-computed',
  doors: 'show-doors',
  windows: 'show-windows',
  floors: 'show-floors',
  gaps: 'show-gaps',
  crossStory: 'show-cross-story',
  extensions: 'show-extensions',
  overlaps: 'show-overlaps',
  wallClips: 'show-wall-clips',
  extGaps: 'show-ext-gaps',
  ceilings: 'show-ceilings',
  thermalCeilings: 'show-thermal-ceilings',
  roofClusters: 'show-roof-clusters',
  ontologySemantics: 'show-ontology-semantics',
  ontologyCells: 'show-ontology-cells',
  fullModel: 'show-full-model',
};

export const LAYER_KEYS = Object.keys(LAYER_CONTROL_IDS);

export const PIPELINE_STEPS = [
  { id: 'apple-merged', label: 'Apple merged', adds: ['merged'] },
  { id: 'room-segments', label: 'Room segments', adds: ['computed'] },
  { id: 'reconciliation', label: 'Reconcile geometry', adds: ['extensions', 'gaps', 'crossStory', 'extGaps', 'overlaps', 'wallClips'] },
  { id: 'openings-surfaces', label: 'Openings and slabs', adds: ['doors', 'windows', 'floors', 'ceilings', 'thermalCeilings', 'roofClusters'] },
  { id: 'full-model', label: 'Final full model', exclusive: ['fullModel', 'ceilings', 'thermalCeilings', 'ontologyCells'] },
];

export const EMPTY_MAP_STYLE = { version: 8, sources: {}, layers: [] };
