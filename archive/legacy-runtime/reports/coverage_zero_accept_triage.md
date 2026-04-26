# Zero-accept triage — coverage audit follow-up

Generated from `reports/coverage_audit.csv` (141 labeled buildings).

**TL;DR.** 16 labeled buildings have zero accepted proposals — the human
rejected every one of the 6–60 segments they were shown. These account
for a chunk of the 40 % "failed coverage" tail and need a diagnostic
pass before more modelling: is the proposer emitting garbage, or did
the labeler give up?

Paste each UUID into the viewer (left sidebar building browser or
`http://localhost:8080/viewer.html?uuid=<uuid>`) to inspect.

## Diagnostic order

Work these 3 first — they're the clearest signal because the heuristic
label *disagreed* with the human. If the proposals look visually
reasonable → labeler bailed; if they look wrong → the heuristic has a
systematic blind spot.

| UUID | footprint m² | n_segs | n_rej | heur:acc | heur:rej | address |
|---|---|---|---|---|---|---|
| `8e7e69b2-e1db-4482-8f21-93be6904a5f1` | 110 | 12 | 12 | 12 | 0 | Tårnvej 1, 5492 Vissenbjerg |
| `98472f6b-45bc-4814-a4b8-914f8f6976dd` | 74 | 9 | 9 | 9 | 0 | Berildsvej 57, 5610 Assens |
| `c2800052-b0e7-4c30-a881-f813cb0b2043` | 71 | 16 | 15 | 8 | 0 | Kikkenborgvej 58, 6000 Kolding |

Then the 13 consensus-failure buildings (both human and heuristic
saw nothing worth keeping — likely proposer-side bugs):

| UUID | footprint m² | n_segs | n_rej | address |
|---|---|---|---|---|
| `37e9355f-29a7-4303-abae-240c55df13e4` | 137 | 60 | 56 | Humlebiv nget 50, 5260 Odense S |
| `938d6ed6-d916-462b-ba37-f421feb2af21` | 234 | 15 | 15 | Bakkevej 2, 8783 Hornsyld |
| `aa047931-2b45-497d-a093-f637a2934699` | 121 | 14 | 14 | Nellikevej 1, 5250 Odense SV |
| `b4b6f3ed-7bfd-43a8-aeed-520b558bfa2b` | 149 | 14 | 14 | Lucernevej 23, 8700 Horsens |
| `0f911051-6084-4f0d-8f9a-24fc5b20f6ff` | 258 | 12 | 12 | Villumstrupvej 7, 5853, rb k |
| `f16973df-10b9-4369-9f0d-dd295a34d970` | 116 | 12 | 12 |  stervang 5, 7160 T rring |
| `e4fe9821-2270-4d23-bc74-703743b5d282` | 178 | 11 | 10 | Hj llundvej 24, 7361 Ejstrupholm |
| `2d80b27f-ca29-4b3e-9197-ad3c4af7cbfb` | 87 | 8 | 8 | Majsvej 79, 5800 Nyborg |
| `c001b1ca-ea07-472d-b888-6ab457d4e7d9` | 73 | 8 | 8 | Hesteh jvej 56, 5260 Odense S |
| `60fa343a-d19a-4d18-b939-33b80e790be6` | 67 | 7 | 7 | S husvej 28, 5270 Odense N |
| `8ab161a4-c958-49c9-8ca8-7a997292d52f` | 67 | 6 | 6 | N sbyhave 48, 5270 Odense N |
| `9829323a-4939-45bf-ae66-b950b18ddf52` | 69 | 6 | 6 | Tom Knudsensvej 45, 5953 Tranek r |
| `d7f1aa19-5ca9-4e1b-ac1a-c86d63f9ede7` | 53 | 6 | 6 | A sumvej 279, st, tv, 5240 Odense N |

## Questions to answer from the viewer

For each of the 3 disagreement buildings:
1. Does the roof, as scanned, look like a reconstructable real-world
   roof (i.e., the scan is usable)?
2. Do any of the 9–15 rejected proposals overlay the visible roof surfaces
   plausibly? If yes, those are labeler false-negatives.
3. Is there a systematic pattern to the heuristic's false-accepts (e.g.,
   wall-extension artefacts it classifies as roof)?

For the 13 consensus-failure buildings:
1. Do the rejected proposals sit on the scanned roof at all, or are they
   floating / tilted / incomplete?
2. Is there a common class of roof that keeps failing (L-shape? dormered?
   half-hipped? partial scan)?

## Next steps after triage

- **If disagreement cohort is labeler fatigue**: drop those 3 from
  training labels (or re-label) and retrain.
- **If consensus-failure cohort has a recognizable common failure mode**:
  that identifies the proposer gap worth closing (likely via a new
  candidate generator or a clustering-parameter fix).
- **If both look like genuinely unreconstructable scans**: deprioritize
  these in the evaluation set and define "addressable coverage" as the
  metric to optimize — coverage on the buildings the proposer is
  capable of serving.
