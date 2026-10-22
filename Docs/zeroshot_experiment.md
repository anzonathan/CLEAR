# CLEAR Zero-Shot Experiment Documentation

**Project:** CLEAR — Clay-court Line Evaluation and Automated Refereeing  
**Course:** Computer Vision and Deep Learning, Six-Week Capstone Project (Advent 2026, UCU)  
**Group 1:** Andrea NABUUMA (B28112), Robert WANYAMA, Blair TONNY (B30009), Nathaniel MUGENYI (B28313)

---

## 1. Objective

Before fine-tuning deep detectors on manually annotated Uganda Christian University (UCU) clay-court footage, the **Zero-Shot Experiment** establishes our end-to-end refereeing pipeline and evaluates **Baselines B1–B3** against our **Anchor-Calibrated Hybrid Architecture** (**Experiments C2 & C3**):

1. **Ball & Player Tracking without Custom Training:** Combine pretrained COCO YOLOv8 (`sports ball`, `person`) with a **3-frame temporal motion + optic-yellow HSV segmentation** branch and MOG2 silhouette recovery.
2. **Virtual Court Reconstruction (`H`, `H^-1`):** Reconstruct all ITF singles and doubles lines from **4 to 6 fixed physical anchors** (corner pegs and net posts) rather than relying on painted lines that fade under clay dust or rain.
3. **Automated Line Judge (`IN` / `OUT` + Doubt Zone):** Detect ground bounces on both Near and Far courts, project the contact patch to court metres, compute signed margin ($\text{cm}$) to the closest line, and flag calls within $\pm 15\text{ cm}$ for Hawk-Eye review.
4. **Match Analytics & Score Engine:** Track ball speed ($\text{km/h}$), rally stroke count, player distance covered ($\text{m}$), sprint speed, court-zone occupancy, 2D top-down court radar, and live tennis score (`0/15/30/40/Deuce/Ad`).

---

## 2. Pipeline Architecture & Mathematical Formulation

### 2.1 Anchor-Calibrated Planar Homography (`src/calibration/`)

We define the canonical ITF court coordinate frame in metres with origin $(0, 0)$ at the **Far-Left Doubles Corner**:
- $X \in [0.00, 10.97]\text{ m}$ (Left Doubles Sideline $\to$ Right Doubles Sideline; Singles Sidelines at $X = 1.37\text{ m}$ and $X = 9.60\text{ m}$).
- $Y \in [0.00, 23.77]\text{ m}$ (Far Baseline $\to$ Near Baseline; Net at $Y = 11.885\text{ m}$; Service Lines at $Y = 5.485\text{ m}$ and $Y = 18.285\text{ m}$).

Given $N \ge 4$ physical anchor taps $\{(X_i, Y_i) \leftrightarrow (u_i, v_i)\}$, we estimate the planar homography $H_{\text{court}\to\text{img}} \in \mathbb{R}^{3\times 3}$ via RANSAC (`cv2.findHomography`) and invert it for court projection:
$$
\begin{bmatrix} X' \\ Y' \\ w \end{bmatrix} = H_{\text{img}\to\text{court}} \begin{bmatrix} u \\ v \\ 1 \end{bmatrix}, \quad (X_m, Y_m) = \left(\frac{X'}{w}, \frac{Y'}{w}\right)
$$

* **Baseline B2 Comparison:** `CourtCalibrator.from_painted_lines_baseline()` uses Canny edge detection + Probabilistic Hough Transform (`cv2.HoughLinesP`) to locate painted lines. On worn or rain-wiped clay surfaces, missing line segments cause corner drift ($\sim 16.4\text{ cm}$ reprojection error vs. $< 2.5\text{ cm}$ with physical anchors).

---

### 2.2 Zero-Shot Hybrid Detector (`src/detect/detector.py`)

Single-frame pretrained detectors (**B1**) frequently miss a tennis ball at $60\text{ fps}$ when its diameter drops to $4\text{–}9\text{ px}$ in the far court or suffers motion blur. Our zero-shot `HybridTennisDetector` fuses two complementary streams:

1. **Pretrained YOLO Branch (`yolov8n.pt`):** Extracts COCO `class 32` (`sports ball`) and `class 0` (`person`) bounding boxes when available.
2. **3-Frame Temporal + Clay HSV Branch (**C2**):**
   - Maintains a rolling 3-frame grayscale buffer $(I_{t-2}, I_{t-1}, I_t)$ and computes temporal motion energy:
     $$M_t = \mathbb{I}\left(|I_t - I_{t-1}| > \tau\right) \cup \mathbb{I}\left(|I_t - I_{t-2}| > \tau\right)$$
   - Segments optic-yellow ball candidates in HSV space ($H \in [24, 46], S \in [95, 255], V \in [140, 255]$), filters contours by radius ($2 \le r \le 18\text{ px}$) and circularity ($4\pi A / P^2 \ge 0.35$), and boosts confidence when temporal motion $M_t(u, v) > 0$.
   - Recovers Far-court and Near-court players via non-clay chromatic masking fused with `MOG2` foreground subtraction.

---

### 2.3 Multi-Object Tracking (`src/track/`)

- **Kalman Ball Tracker (`src/track/ball_tracker.py`):**
  - State vector $\mathbf{x}_t = [u, v, v_u, v_v]^T$ with constant-velocity transition matrix $F$, gated candidate association ($d \le 95\text{ px}$), and coasting up to $8$ frames across player occlusions.
  - Preserves raw detector observations $(u_{\text{raw}}, v_{\text{raw}})$ alongside filtered states so sharp bounce cusps are not rounded off by Kalman smoothing.
- **ByteTrack-Lite Player Tracker (`src/track/player_tracker.py`):**
  - Associates detections into persistent Near (`P1`) and Far (`P2`) slots using foot-point distance and confidence.
  - Projects bottom-center foot coordinates $(u_{\text{foot}}, v_{\text{foot}})$ through $H_{\text{img}\to\text{court}}$ to compute cumulative distance ($\text{m}$), smoothed sprint speed ($\text{km/h}$), and tactical zone percentages (Baseline / Transition / Net).

---

### 2.4 Perspective-Invariant Bounce Judge (`src/judge/bounce_judge.py`)

A naive vertical-velocity sign check ($v_{y,\text{in}} > 0 \to v_{y,\text{out}} < 0$, **Baseline B3**) fails on shots travelling from the Near court to the Far court because camera perspective causes the ball's ground shadow $v_{\text{shadow}}(t)$ to move steadily upward on screen ($c_v = \dot{v}_{\text{shadow}} < 0$).

Writing the image vertical coordinate as $v(t) = v_{\text{shadow}}(t) - k \cdot z(t)$ where $z(t) \ge 0$ is height above clay:
- Over a 5-frame window $[t-2, t+2]$, $v_{\text{shadow}}(t) \approx v_0 + c_v t$ is locally linear.
- The second-order **vertical bounce impulse**:
  $$\kappa(t) = v(t) - \frac{v(t-2) + v(t+2)}{2} = \frac{v(t) - v(t-2)}{2} - \frac{v(t+2) - v(t)}{2} \approx k \frac{z(t-2) + z(t+2)}{2}$$
  **cancels the perspective slope $c_v$ identically**, yielding a sharp positive peak ($\kappa(t) \ge 1.6\text{ px}$) at ground bounces in both court halves!
- **Sub-Pixel Parabolic/Ray Refinement:** Fitting incoming ($t \in [-3, 0]$) and outgoing ($t \in [0, +3]$) rays around the impulse peak refines the exact contact vertex $(u_b, v_b)$ before projecting to $(X_m, Y_m)$.
- **Line Margin & Doubt Zone:** Accounting for ball compression radius ($r_{\text{contact}} = 3.8\text{ cm}$) and half line-width ($2.5\text{ cm}$), a ball is called **IN** if its signed margin to the active boundary satisfies:
  $$\text{margin}_{\text{cm}} = d_{\text{signed}} + r_{\text{contact}} + \frac{w_{\text{line}}}{2} \ge 0$$
  Calls with $|\text{margin}_{\text{cm}}| \le 15.0\text{ cm}$ are flagged as **DOUBT ZONE** and trigger an automatic Hawk-Eye magnified crop on the HUD.

---

## 3. Experimental Results (Zero-Shot Benchmark)

Evaluated on the 280-frame ($60\text{ fps}$, $1280\times 720$) worn-clay rally benchmark (`scripts/evaluate.py`) containing 4 ground-truth bounces across both court halves (including a $+8.0\text{ cm}$ Doubt-Zone sideline bounce and a $-16.0\text{ cm}$ baseline `OUT` bounce):

| Metric | Capstone Target (`README.md`) | Baseline (`B2` Painted Hough + `B3` Raw Vertex) | CLEAR Zero-Shot (`6-Anchor` + `3-Frame Hybrid` + `Ray Fit`) |
|---|---|---|---|
| **Ball Detection F1** (`5px` tol) | $\ge 0.800$ | $0.984$ | **$0.984$** |
| **Ball Mean Pixel Error** | $\le 5.00\text{ px}$ | $0.81\text{ px}$ | **$0.81\text{ px}$** |
| **Median Bounce Error** | $\le 15.00\text{ cm}$ | $36.71\text{ cm}$ | **$1.47\text{ cm}$** |
| **Line Call Agreement** | $\ge 80.0\%$ | $50.0\%$ | **$100.0\%$** |

### Per-Bounce Breakdown (`results/rally1/bounces.json`)

| Bounce # | Frame | Court Half | Ground Truth $(X, Y)\text{ m}$ | Predicted $(X, Y)\text{ m}$ | Call | Signed Margin | Closest Line | Doubt Zone (`<15cm`) |
|---|---|---|---|---|---|---|---|---|
| **1** | `46` | Far | `(3.100, 3.400)` | `(3.101, 3.389)` | **IN** | `+179.4 cm` | `left_singles_sideline` | No (`99.0%` conf) |
| **2** | `110` | Near | `(9.590, 19.650)` | `(9.580, 19.682)` | **IN** | `+8.3 cm` | `right_singles_sideline` | **YES** (`59.3%` conf) |
| **3** | `176` | Far | `(8.100, 0.450)` | `(8.098, 0.465)` | **IN** | `+52.8 cm` | `far_baseline` | No (`91.2%` conf) |
| **4** | `242` | Near | `(3.200, 23.980)` | `(3.206, 23.993)` | **OUT** | `-16.0 cm` | `near_baseline` | No (`67.4%` conf) |

---

## 4. Reproducing & Tweaking the Experiment

### 4.1 Local CLI via `uv`

```bash
cd CLEAR

# 1. Sync environment
uv sync --python 3.12

# 2. Calibrate virtual court from anchors (or --mode interactive / painted_b2)
uv run python scripts/calibrate.py --video data/demo/ucu_clay_rally.mp4 --out calib/session.json --preview results/calib_preview.png

# 3. Run full inference (writes annotated_rally.mp4, bounces.json, summary.json, court_analytics.png)
uv run python scripts/infer.py --video data/demo/ucu_clay_rally.mp4 --calib calib/session.json --out results/rally1

# 4. Run quantitative evaluation (Baseline B1-B3 vs CLEAR Final)
uv run python scripts/evaluate.py --config configs/detector.yaml --split test
```

### 4.2 Google Colab Notebook (`Model/zeroshot.ipynb`)

Open `Model/zeroshot.ipynb` in Google Colab or Jupyter. Use **Cell 2 (Hyperparameter Control Panel)** to tweak:
- `BALL_HSV_LOWER` / `BALL_HSV_UPPER`: Adjust for wet/dark clay vs. dry/bright clay or dusk lighting.
- `DETECTOR_MODE`: Switch between `"hybrid"` (YOLO + 3-frame HSV), `"yolo"`, and `"classical"`.
- `MIN_BOUNCE_IMPULSE_PX`: Lower (`1.0–1.4`) for low-skidding slice shots; raise (`1.8–2.5`) for noisy handheld cameras.
- `DOUBT_ZONE_CM`: Adjust uncertainty challenge threshold around virtual lines.

### 4.3 Interactive Broadcast Web Studio (`App/server.py`)

```bash
uv run python App/server.py
```
Opens the interactive CLEAR Referee Studio in your browser where you can click court anchors directly on the video frame, toggle virtual lines & doubt zones, scrub bounce replays, and inspect the 2D Hawk-Eye radar live.
