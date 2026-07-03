---
name: aiglass-pano-pipeline-decision
description: "2026-06-09 — user decided to build NEW \"Pano-Hotspot Tour Pipeline\" parallel to existing nerfstudio splat pipeline; Matterport-style 360 panorama stitching from AI-glasses spin-in-place video"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2bafa0a0-9d06-46c3-b673-40f3583cb0a4
---

User decided (2026-06-09): build a NEW Matterport-style 360-panorama-hotspot tour pipeline ALONGSIDE the existing nerfstudio Gaussian Splat pipeline. **DO NOT touch any splat code/schema.**

**Why:** user feels Gaussian Splat pipeline is "very slow and really hard" (20-min GPU training, RTX 5090 dependency, ngrok URL rotation pain). Matterport's "stand-spin-walk" capture is simpler and Korean real estate buyers see it as the de-facto tour format (refar.uz example confirmed Matterport).

**Capture UX decided:** phone screen+voice prompts FOR worker ("spin now / walk to next") AND server-side automatic spin-detection from motion analysis. Both belt-and-suspenders.

**Architecture (sibling to nerfstudio, ZERO overlap):**
- Pipeline repo: NEW `backend/pano_pipeline/` (own inbox/, stitcher.py, upload_server.py port 9200, watcher.py)
- SaaS repo: NEW DB tables `pano_tours`, `pano_scenes`, `pano_hotspots`
- SaaS repo: NEW tRPC router `panoTours.*`
- SaaS repo: NEW routes `/aiglass/capture-pano`, `/tours/pano/<id>`
- Android: NEW `CapturePanoActivity`
- Viewer: Pannellum (open-source equirectangular)

**Honest tradeoffs accepted:**
- ✅ No GPU needed (CPU-only OpenCV stitching, ~30s per tour)
- ✅ $0/mo (Pannellum is MIT licensed)
- ✅ Uses AI glasses (no Insta360 purchase needed)
- ⚠️ Top/bottom of panorama will be blurry/filled (forward-facing glasses don't see ceiling/floor cleanly when spinning)
- ⚠️ ~70-80% visual quality vs real Matterport (single-camera stitching has visible seams)
- ❌ NO measurements, NO floor plan auto-generation (no LiDAR)

**Why:** establishes a separation contract — any future Claude in this codebase should know these two pipelines must remain code-isolated. Mixing them was explicitly forbidden by user.

**How to apply:** when working in `aiglass-realestate-agent` or `realestate-3d-tour-agent`, treat pano and splat as two independent products. Don't share tables, routers, or workers. Don't refactor "common" pieces out unless explicitly asked. See [[project_healthcare_postprocessing_limits]] for similar architectural-isolation lesson.

**Decision NOT to reverse-engineer Matterport.** User briefly asked; I explained ToS violation + CoStar legal exposure + ban risk. Off the table permanently.

**Build phases:**
1. DB schema + tRPC router + Python stitcher skeleton (2-3 days)
2. Phone capture flow with prompts (2-3 days)
3. Tour page + Pannellum viewer (3-4 days)
4. Hotspot editor (broker drags arrows) (2-3 days)
5. Polish + real apartment test (3-4 days)

Total ~2 weeks one focused dev.
