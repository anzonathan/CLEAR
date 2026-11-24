# CLEAR platform experiments (Milestone 4)

**Project:** CLEAR, Clay-court Line Evaluation and Automated Refereeing
**Scope:** the two-phone web platform: roles, games, phone ingest, calibration and streaming. The vision-model experiments are in `zeroshot_experiment.md`.

All runs below used the full Docker stack locally (`LOCAL_TEST.md`) on a MacBook with **CPU-only** inference. Phones were simulated with Chrome's fake camera (`--use-fake-device-for-media-stream`). The fake camera shows flat coloured shapes, not a court. Results about **flow and correctness** carry over to real phones. Results about **bandwidth, frame size or detection** do not. Each section says which kind it is.

---

## E1. Two-phone game, end to end

**Question:** can two paired players run a game entirely from their phones, and can a developer watch it live and analyse the recording?

**Setup:**

- Three browser sessions: two phones (390×844) and one developer desktop (1440×900).
- The phones started a session from the connection page, claimed opposite ends and started their cameras.
- The developer then watched live, the players ended the game, and the developer ran the analysis.

**Result: 21 of 21 checks passed.**

| Check | Result |
|---|---|
| Admin lands on `/admin` and is kept out of `/app` and `/dev` | pass |
| Player lands on `/app`, kept out of `/dev`, gets 403 from the field console API | pass |
| Developer lands on `/dev` and can also use `/app` | pass |
| Each player gets their own camera and only their own camera token | pass |
| Game auto-starts once both cameras are online and steady for 3 s | pass |
| Both phones switch to **Live** (8 fps each) | pass |
| Developer receives both annotated feeds | pass |
| Ending the game saves one raw recording per camera (2) | pass |
| Offline analysis of both recordings completes (`done`) | pass |

**Bug found and fixed while building this flow:**

- **The bug:** the WebSocket consumers built a new `FieldManager` for every connection. Phone frames went to a manager with no running match and were dropped. Live viewers never saw the real runtime.
- **The fix:** the consumers now share the process-wide manager used by the REST views (`backend/websockets/field.py`).
- **Impact:** before the fix, live two-camera analysis of phone video could not have worked.

**Not covered:** the start chime and vibration. The test confirms the browser exposes the Web Audio API, but nobody listened. Check it by ear on a real phone.

---

## E2. Calibration from the developer tools

**Question:**

- Can a developer calibrate both ends of a scheduled game before it starts, without the game starting underneath them?
- Are the clicked points stored in the right court coordinates for each end?

**Setup:**

- Scheduled game, both ends claimed.
- The developer opened the End A calibration page and started a **camera preview**.
- The developer clicked four corners on each end and saved.
- The developer switched to End B, repeated, then clicked **Done**.

**Result: 15 of 15 checks passed.**

| Check | Result |
|---|---|
| Game stays `scheduled` while the preview runs, although both cameras are online | pass |
| Phones show **Calibrating** (no start chime); the player page says a referee is calibrating | pass |
| Saved anchors use the backend's absolute names (`far_left_doubles` …) | pass |
| End A: camera-view "near left" is stored as absolute `far_right_doubles` (left/right and near/far swapped) | pass |
| End B: camera-view names map directly to absolute names | pass |
| Saving applies the calibration to the **running** camera, not only on the next start | pass |
| After **Done**, the game auto-starts and both phones go live | pass |

**Reprojection error:** 1.5 cm on End A. The clicks were placed on a synthetic frame, so this only shows that the calibration round-trips cleanly. It says nothing about accuracy on a real court; that needs real footage (protocol P2 below).

**Bugs found and fixed:**

1. **Calibration did not reach live games.** `save_calibration` only updated the single-channel runtime, so a calibration saved during a live two-camera game had no effect until restart. It now updates whichever runtime owns the camera. `auto_calibrate` likewise accepts match runtimes.
2. **The game could start mid-calibration.** Leaving the End A page stopped the preview. With both cameras online and no preview, the game started itself while the developer was moving to End B. The preview now stops only when the developer clicks **Done**.

---

## E3. Streaming settings and adaptive quality

**Question:**

- Do settings changed in `/dev/streaming` reach running phones?
- Does the server measure what phones actually send?
- Does adaptive mode step down in the intended order and respect the floors?

**Setup:**

- Two fake-camera phones in a live game.
- Settings were changed through the API while the game ran.
- To simulate a congested uplink, the phone's `WebSocket.bufferedAmount` was forced high. Chrome DevTools network throttling does **not** apply to WebSockets, so it could not be used.

**Result: 14 of 15 checks passed on the final run.** The remaining miss is explained under *Frame-rate measurement* below.

| Check | Result |
|---|---|
| Players get 403 from the settings API | pass |
| A floor above its target is rejected (400) | pass |
| Server measures upload per phone | pass |
| Phone sends the target width (1280) | pass |
| Running phone adopts new settings (960 px, q70, 5 fps) without restarting its camera | pass |
| Under congestion, the phone reports **weak signal** | pass |
| Step-down order: frame rate 8→4, then quality 0.75→0.65, then width 1280→960 | pass |
| Never below the floors (960 px, q65, 4 fps) | pass |
| Recovers upward when the link clears (960→1120 px within 14 s) | pass |

**Adaptive timing:**

- **Step-down:** one step per 2 s window that had congestion. Reaching the floors from the Balanced target takes 8 steps, about 16–20 s.
- **Step-up:** one step after 3 calm windows, about 6 s per step. Recovery is deliberately slower than step-down, so the quality doesn't oscillate on a marginal link.

**Measured upload (fake camera, flow only):**

| Settings | Frame size | Upload per phone |
|---|---|---|
| 1280×720, q75, 8 fps | 10.5 KB | 0.58 Mbps |
| 960×540, q70, 5 fps | 7.2 KB | 0.29 Mbps |

These numbers are **not representative**: the fake camera's flat shapes compress far better than real court video. Bandwidth for real footage is unmeasured (protocol P1). The Streaming page therefore labels its Mbps estimates as rough until real phones stream, then rescales them from the phones' measured frame sizes.

**Frame-rate measurement:**

- The measured frame rate varied between runs (7, 3.8, 1.4 fps against a target of 8).
- Two things in the test setup cause this:
  - headless Chrome throttles timers on pages that are not in the foreground;
  - three browser contexts were sharing a laptop CPU with two detection workers.
- A real phone keeps the page in the foreground with a wake lock.
- The server now averages over 3 s windows, so one late frame doesn't swing the reading.

**Bug found and fixed:**

- **The bug:** the server sometimes reported 0 kbps for a phone that was streaming. Redis channel-layer timeouts dropped WebSocket consumers without a clean disconnect, and their status loops kept overwriting the stats with zeros.
- **The fix:** bytes are now counted per camera, not per connection. A phone counts as connected only when traffic arrives from it.

---

## E4. Will the detector see the ball? (analytical)

**Question:** what resolution must phones send so the ball stays detectable?

**Two facts from the code:**

- The colour and motion ball detector (`src/detect/detector.py`) rejects blobs with a radius under 2 px, so the ball must be at least about **4 px across**.
- YOLO resizes every frame to `imgsz` (default 640 px) before detection.

**Model:**

- Ball diameter 6.7 cm.
- Phone 3 m behind its baseline, so the net is about 15 m away and the far baseline about 27 m.
- Ball width in pixels = 0.067 · W / (2 · d · tan(FOV/2)).

| Sent width | Main lens (~70°): at net | far baseline | Ultra-wide (~100°): at net | far baseline |
|---|---|---|---|---|
| 640 px | 2.0 px | 1.1 px | 1.2 px | 0.7 px |
| 960 px | 3.1 px | 1.7 px | 1.8 px | 1.0 px |
| 1280 px | 4.1 px | 2.3 px | 2.4 px | 1.3 px |
| 1920 px | 6.1 px | 3.4 px | 3.6 px | 2.0 px |

**Consequences:**

1. **The old setting was too small.** The original phone page sent 640 px frames, where the ball is about 2 px at the net: below the detector's threshold. The defaults are now 1280 px (target) and 960 px (floor).
2. **Each camera covers its own half.** Even at 1920 px, the far baseline is under 4 px. The two-camera design relies on the other end's camera for that half.
3. **Use the main lens.** The ultra-wide lens roughly halves the ball's size.
4. **Raise YOLO's input size on the GPU.** At `imgsz` 640, YOLO sees a 1280 px frame at half resolution. With the GPU, set **Detector input** to 960 or 1280.

The Streaming page shows this estimate live for the current target and floor. It is a geometric model only, and has not yet been checked against real detections (protocol P3).

---

## E5. CPU inference cost (observation)

During E1, each camera's runtime reported **53–101 ms per frame** on the laptop CPU, at 8 fps per phone. That just keeps up with two phones at 640–1280 px. Offline analysis time was not measured.

On the deployment server (RTX A4000, CUDA 13.2, matching the image's `torch 2.15.0+cu132`), YOLOv8n is expected to run in a few milliseconds per frame. This is not yet measured on `dct1` (protocol P4).

---

## Open protocols (real footage needed)

| ID | Measures | How |
|---|---|---|
| P1 | Real upload per phone | Two phones on the UCU court, each preset. Read **Phones right now** in `/dev/streaming` for 2 minutes per preset; record median Mbps and KB per frame |
| P2 | Calibration accuracy | Calibrate both ends; mark 10 known court points (service T, singles corners) on a frame; report the error in cm between projected and true positions |
| P3 | Ball detectability vs resolution | Record a rally at 1920 px; replay the raw recordings downscaled to 1280 / 960 / 640 through `ClearPipeline`; compare ball-tracking coverage and bounce counts |
| P4 | GPU speed-up | Same recording through the analysis on CPU and on the A4000 (`CLEAR_DEVICE=cpu` / `cuda`); report ms per frame and live fps headroom at `imgsz` 640 / 960 / 1280 |
