---
name: feedback-simple-explicit-over-auto-detect
description: "When auto-detection from continuous input keeps failing, switch to multiple explicit uploads. User prefers manual control over unreliable smart auto-detection."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2bafa0a0-9d06-46c3-b673-40f3583cb0a4
---

**Rule:** When auto-detection from a single continuous input keeps failing across multiple algorithm tunings, STOP TUNING and switch to multiple explicit uploads (one upload per discrete event).

**Why:** 2026-06-09 pano pipeline incident. The first Phase 1 test (single 360° spin uploaded as one mp4) produced a CLEAN panorama. I then "improved" the pipeline by adding auto-spin-detection in Phase 3 so the user could record everything in one continuous video. We spent 6+ iterations tuning the spin detector (smoothing windows, sign-reversal, frame counts, inpaint strategies, Stitcher configs) — each iteration improved one thing and regressed another. The V-wedge failures the user kept seeing were structurally caused by the auto-detection splitting clean spins into segments where loop-closure failed. The user said: "in our 1st test everything was good. So take rotation video of each place separately and connect them." We had ALREADY built Phase 2 multi-upload (panoTours.startNextScene + appendSceneFromPipeline + finalize) before going down the Phase 3 detour. The correct answer was always: **one upload = one spin = one scene, broker uploads N times for N rooms, server connects them with auto-hotspots**.

**How to apply:**
- If the first single-explicit-input test produces good output, DON'T try to make a clever multi-input pipeline that auto-detects boundaries. Just have the user upload N times.
- Multi-upload UX is fine on browser/phone — sequential N-step forms are well-understood.
- Auto-detection is technically interesting but operationally fragile when the detection signal (camera motion, voice, audio, etc.) doesn't have a hard boundary.
- Lesson generalizes: same applies to other "single big input + auto-detection" patterns. If detection is < 99% reliable on the user's actual data, ship explicit-multi instead.

**Related memory:** [[project_aiglass_pano_pipeline_decision]] — the architectural pivot to pano pipeline alongside (not replacing) the splat pipeline.
