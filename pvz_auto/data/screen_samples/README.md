# PVZ Hybrid v3.19 screen samples

`sample-001.png` is a user-provided 1086 × 637 screenshot showing an active lawn with plants, zombies, and gravestones. Its partial metadata is in `sample-001.json`. The screenshot includes the Windows title bar, so it is not the same crop as the current window capture output. Lawn pixel bounds and entity positions are not yet annotated; do not use it as measured ground truth.

Use these samples to develop and review screen perception. Add a sidecar annotation before using a screenshot as a measured test fixture; record the mode, level if known, window/client crop, lawn bounds, grid dimensions, resource values, and manually checked entity locations. Keep original captures unchanged so detector changes can be compared against the same input.
