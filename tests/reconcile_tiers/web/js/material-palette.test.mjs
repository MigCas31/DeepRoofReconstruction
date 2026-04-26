import test from "node:test";
import assert from "node:assert/strict";

import { MATERIAL_PALETTE, gapMaterial } from "../../../../reconcile_tiers/web/material-palette.js";

test("gapMaterial uses typed gap kinds", () => {
  assert.equal(gapMaterial("gap_ceiling"), MATERIAL_PALETTE.roof);
  assert.equal(gapMaterial("gap_floor"), MATERIAL_PALETTE.floor);
  assert.equal(gapMaterial("exterior_side"), MATERIAL_PALETTE.structureFill);
});

test("unknown gap kind falls back to structure fill", () => {
  assert.equal(gapMaterial("unknown"), MATERIAL_PALETTE.structureFill);
});
