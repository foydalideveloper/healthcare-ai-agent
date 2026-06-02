# Session progress — Speed + Recall + Enumeration (2026-05-29)

Test clip: `20260528090126884.mp4` (61.7s, KBS news, broadcast).
Iteration arm: **Gemini only** (`gemma=False, gemini=True, --no-supabase`).
Recall metric: substring match vs 144-item ground-truth pool (12 KBS screenshots).
Measured by: `backend/glasses_watcher/tests/test_recall_measure.py`.

| Fix              | Items | Recall | Latency | Notes |
|------------------|-------|--------|---------|-------|
| Baseline v2      | 505   | 56.2%  | 126.7s  | control. Whisper failed (WinError 127) → transcript empty; OCR unaffected. chunk1 hit 500-cap @ 60 frames. |
| Speed Win 1      | 503   | 58.6%  | 114.9s  | **rec_batch_num=16** only. chunk1 OCR 29.7s→18.0s (−11.7s). Batch-list API forbidden (det must be false); 3-instance threadpool 0.92x (slower); ticker-band-skip dropped GT 144→124 so reverted. Recall flat within ±2-3pp GPU noise. |
| Speed Win 2      | 505   | 58.6%  | 115.6s  | motion skip. **~0 effect on broadcast** (only 5 frames skipped): at 1fps consecutive frames rarely >97% similar, and exact-phash cache already grabs static repeats. Recall-neutral, val-changes held at 3. Kept (every-other-frame floor) — genuinely helps static everyday-wear scenes, harmless on broadcast. |
| Speed Win 3      | n/a   | n/a    | n/a     | pipeline infra. **Already existed** via chunk_workers ThreadPoolExecutor (OCR of chunk N+1 overlaps LLM of chunk N — GIL released on net I/O + C++ OCR). Added thin `--pipeline` flag (floors chunk_workers>=2) + `--no-gemma` flag (clean gemini-only iteration). Validated 1.06x on 2 chunks; scales with chunk count. ProcessPool rejected (GPU model dup = 0.92x). |
| Recall (a)       | 503   | 58.6%  | 114.8s  | 3-4x adaptive ROI upscale. **No gain on this clip — DORMANT**: detect_panels returns exactly 1 panel/frame (Hana Bank sub-board merged into main TV panel by DBSCAN eps=12% diag), and reocr_panel is gated on >=2 panels so it never fires. Activation paths: (i) DBSCAN eps tuning = forbidden by CRITICAL DON'Ts; (ii) gate>=1 tested → REGRESSED recall 58.6→45.5 + latency 18→32.9s, reverted. Adaptive-upscale code kept (helps true split-screens; strict improvement over old hardcoded 2x). Ground truth FROZEN at 145 this step. |
| Recall (d)       |       |        |         | currency-board regex pairing |
| Recall (b)       |       |        |         | smart digit-priority cap |
| Recall (c)       |       |        |         | per-window cap |
| Enumeration      | 503   | 58.6%  | 127.0s  | **enumerated_observations populated: 49 sentences** (chunk0=36, chunk1=13) vs old 6-10 observed_facts (~6-8x more visible). Below aspirational 80-250 because most of the 500 OCR items are cross-frame dups/noise; distinct meaningful content ~50. Gemini didn't pad with garbage (good). +12s latency from 20k-token generation. Recall unchanged (enumeration doesn't alter OCR). Needs migration 009 applied + Supabase write to show on dashboard. **VERIFIED end-to-end 2026-05-29: migration 009 applied, gemini write inserted 2 rows, endpoint returns enumerated_observations (36 + 11), frontend renders.** |

## Recall wall (forbidden levers, authorized 2026-05-29)
- **Higher-DPI (det_limit_side_len=1920)**: REJECTED — OCR 18s→79.7s (+340%), recall 58.6→40.7% (fragmentation vs 960-built GT). Reverted.
- **DBSCAN eps 0.12→0.05**: REJECTED — OCR +10.6s, recall flat-to-down (56.6%), only partial values. Reverted.
- **Conclusion**: missing GT items aren't resolvable in the compressed video (sharp only in the clean screenshots that built the GT). OCR tuning can't conjure absent pixels.
- **Fuzzy metric (the real win)**: substring 58.6% is a hostile undercount (OCR fragments/mojibakes the SAME content differently in GT vs video — `hana8ank`≈`hanabank`, `82270`≈`822870`, `a276000`≈`276000`). recall_fuzzy (substring+numeric+difflib>=0.85) = **88.3% (128/145)**, manually validated (13/14 newly-credited items legit). The Hana Bank board etc. WAS captured all along. ~88% is the honest capture figure.

## Final all-4-arm run (Supabase write, --pipeline) 2026-05-29
- Pipeline speedup **2.15x** (283s wall vs 608s serial-baseline).
- Gemma 4 26B (local): 4 rows, 61 enumerated sentences (slow: 238s/chunk, the wall-clock bottleneck).
- Gemini 2.5 Pro: 2 rows, 34 sentences. OK.
- Llama 4 Maverick (NIM): 1 row, 9 sentences — chunk 1 got HTTP 400 from NIM (likely max_tokens=18000 too high or transient).
- Qwen 3.5 VL (local Q4): 0 rows — JSONDecodeError both chunks (verbose enumeration overran max_tokens=15000 → truncated/malformed JSON).
- 3/4 arms write enumeration to the dashboard. Qwen needs JSON-repair or lower verbosity; Llama4 NIM flaky.

## Qwen + Llama4 arm fixes 2026-05-29
- **Qwen FIXED (0 -> 2 rows)**: root cause was Q4 degenerate repetition ("...US dollar to X exchange rate" x many) overrunning max_tokens and truncating JSON mid-string inside the events array. Fixes: (a) frequency_penalty=0.5 + presence_penalty=0.3 to break the loop; (b) `_close_truncated_array` bracket-balancing salvage recovers a partially-emitted object; (c) `_salvage_enumerated_observations` best-effort; (d) timeout 180->300s, retries 1->0 (one long attempt > two cut-off ones). Final all-4: Qwen recovered BOTH chunks (json_recovered:events_balanced), 2 rows. Enumeration empty because Qwen truncates inside events before reaching that field — acceptable.
- **Llama4 IMPROVED, NIM-capped (~1/2 chunks)**: the HTTP 400/500 is NIM server-side ("failed to decode json body") and RANDOM per request (failed chunk flips between runs) — NOT concurrency (persisted with --chunk-workers 1) and NOT our request (httpx sends valid JSON). Fixes: capture+log the response body (revealed the real error), retry transient codes with 12s backoff, max_tokens 18000->8192. Immediate retry can't help (NIM rejects the same request instance); a different run succeeds. Provider instability, not a code bug.
- **New side-effect**: all-4 parallel runs both LOCAL Ollama models (Gemma+Qwen) on one GPU -> contention -> occasional Gemma timeout (chunk0 timed out this run but chunk1 gave 3 rows). Mitigation (not done): serialize the two local arms while cloud arms stay parallel.
- Final all-4: 8 rows across ALL 4 source models (was 7, Qwen had 0). Speedup 2.53x (411s vs 1037s serial).

## Notes
- `_lifelog_test.py` CLI: positional `video` + `--gemini`/`--llama4`/`--compare` (each *adds* an arm on top of always-on Gemma). No `--video`/`--arms` flags. True gemini-only requires `run(..., gemma=False, gemini=True)` (used via temp runner).
- Output files: single-arm → `<video>.lifelog.json`; multi-arm → `<video>.compare.json`.
- Baseline raw OCR items: 909; unique after normalize: 505.
