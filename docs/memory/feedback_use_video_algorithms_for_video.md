---
name: feedback-use-video-algorithms-for-video
description: "When the input is video, use a video-domain algorithm — don't downsample to photos and run a photo algorithm. The wrong paradigm cannot be tuned into the right one."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2bafa0a0-9d06-46c3-b673-40f3583cb0a4
---

**Rule:** When the input is continuous video, use an algorithm designed for sequential video. Do NOT extract sparse keyframes and feed them to a wide-baseline photo algorithm — that throws away temporal continuity, the single most valuable property of the input.

**Why:** 2026-06-09/10, pano pipeline incident. I spent 10 iterations tuning cv2.Stitcher_PANORAMA (which is designed for sparse photos with unknown ordering and uses RANSAC for feature matching across wide baselines) on 12 keyframes sampled from a 15-second handheld phone spin. Each failure mode I fought (RANSAC non-determinism producing different output from identical input, V-wedges from loop closure failure, repeating-texture ambiguity in corridors, parallax from handheld orbit, direction reversals) was a downstream symptom of that one architectural decision. A stronger model (Opus 5 or equivalent) diagnosed it in one read: "You're using a photo stitcher on a video."

The correct algorithm for the same input is rotational video mosaicking with center-strip compositing — what Apple's iPhone panorama mode and Google Photo Sphere use:
1. Cylindrical-warp each densely-decoded frame at focal length f
2. Track frame-to-frame yaw with cv2.phaseCorrelate (deterministic, no RANSAC)
3. Per-frame yaw accumulates into a yaw track — directly handles reversals, partial spins, loop closure
4. Composite only the center 10-20% strip of each frame at its tracked yaw — kills parallax because the strip is what the camera actually saw at that exact direction
5. Self-calibrate f via loop-closure residual minimization
6. Per-strip gain compensation handles auto-exposure drift

**How to apply:**
- Before choosing an algorithm, name the input shape: sparse photos, continuous video, depth map, etc. Match the algorithm to the shape.
- If the input is video, look for terms like "mosaicking", "tracking", "phase correlation", "optical flow" — NOT "Stitcher", "homography", "feature matching", "RANSAC across keyframes."
- "Use the algorithm Apple/Google actually use for this product" is a valid heuristic — phone vendors solved the same problem.
- Tuning the wrong paradigm has a ceiling. No amount of seed-shopping, inpaint radius, or quality scoring fixes the wrong front-end.

**Related lessons:**
- [[feedback_simple_explicit_over_auto_detect]] — when auto-detection of segments keeps failing, try explicit user input. (Different lesson but same theme: stop tuning when the architecture is wrong.)

**Related project:** [[project_aiglass_pano_pipeline_decision]]
