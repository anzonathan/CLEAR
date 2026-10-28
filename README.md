# CLEAR: Clay-court Line Evaluation and Automated Refereeing

Single-camera, anchor-calibrated computer vision for automated line calling and match analytics on outdoor clay tennis courts at Uganda Christian University (UCU).

**Course:** Computer Vision and Deep Learning, Six-Week Capstone Project (Advent 2026)
**Group 1:** Andrea NABUUMA (B28112), Robert WANYAMA, Blair TONNY (B30009), Nathaniel MUGENYI (B28313)

> **Project status: proposal stage.** The sections marked *(planned)* describe the interface we intend to deliver. Commands, file names and results will be filled in and verified as each week's work lands, and the final version of this file must be checked against a clean clone before submission.

## 1. Problem summary

Tennis at UCU is played on outdoor clay courts without line judges, so close in/out calls turn into arguments. CLEAR turns a single phone video into an assistive line-calling and scoring tool.

Three conditions shape the design:

- **Clay surface:** low ball-to-court contrast, dust at bounce.
- **Outdoor lighting:** glare, hard shadows, dusk, tripod shake.
- **Rain and play wipe the lines:** so the court is rebuilt as a *virtual* court from fixed physical anchors (corner pegs and net posts), not from painted lines.

| | |
|---|---|
| **Input** | Video (1080p, 60 fps) from one phone on a tripod, plus 4 to 6 anchor taps per session |
| **Output** | Ball and player tracks; bounce points in court metres; IN/OUT call with margin (cm) and confidence; running score; player statistics |
| **Primary CV task** | Small-object detection and multi-object tracking in video, with a homography to the court plane |
| **Intended use** | Help players settle close calls and keep score. Calls inside the doubt zone near a line are flagged for replay and challenge |
| **Will not** | Replace umpires in official matches, call lets or foot faults, identify players by face, work on other surfaces without retraining |

The full written proposal is in `docs/CVDL_Group01_ProjectProposal.pdf` (source: `.tex`).

## 2. Pipeline

```
phone video -> preprocessing (court crop, stabilise, letterbox, frame stack)
            -> detection (fine-tuned YOLO: ball, players)
            -> tracking (Kalman + ByteTrack)
            -> bounce detection (trajectory intersection)
            -> court mapping (homography from anchors) -> line judge (IN/OUT, margin, confidence)
            -> score engine, replay, statistics
anchor taps -> homography      static landmarks -> camera-drift check
```

Two modes: **Review** (full resolution, post-point, accuracy reference) and **Live** (quantized on-phone model, attempted once Review works).

## 3. Repository layout *(planned)*

```
clear/
  README.md
  requirements.txt
  configs/            # training, inference and calibration settings (no personal paths)
  data/               # not committed; see Data notes
    raw/  labels/  splits/
  src/
    data/             # extraction, cropping, augmentation, split builder
    calibration/      # anchors -> homography, drift check
    detect/           # YOLO fine-tuning and inference
    track/            # Kalman, ByteTrack, trajectory fitting
    judge/            # bounce estimation, IN/OUT with confidence
    score/            # tennis scoring state machine
    export/           # FP16/INT8 export for Android
  scripts/            # train.py, evaluate.py, infer.py
  results/            # metrics, plots, experiment tables, saved failure cases
  models/             # final weights, or download instructions
  docs/               # proposal, final report, system card
```

## 4. Setup *(planned)*

Requirements: Python 3.10 or newer, a CUDA GPU for training (CPU is enough for inference on short clips), `ffmpeg`.

```bash
git clone <repository-url> clear && cd clear
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Main dependencies (versions pinned in `requirements.txt` at the end of Week 1): PyTorch, Ultralytics YOLO, OpenCV, NumPy, SciPy, a Kalman/tracking library, TensorFlow Lite or ONNX Runtime for export.

## 5. Data notes

| Source | Role | Status / licence |
|---|---|---|
| UCU clay-court recordings (collected by the group) | Main training data and, above all, the test set | Group-owned; written player consent; not publicly released |
| TrackNet tennis dataset | Pretraining for ball detection | Academic-use licence, to be verified |
| WASB-SBDT | Multi-sport ball detection benchmark including tennis | Licence to be verified |
| Roboflow Universe tennis sets | Supplementary | Per-dataset licence, quality audit required |
| COCO (`person`, `sports ball`) | Pretrained detector weights | Annotations CC BY 4.0; images under Flickr terms |

- **Annotation:** CVAT; small boxes for the ball, boxes for players, a flag on each bounce frame. Pre-labelled with a pretrained detector, then corrected by hand; a second member checks 10% of the labels.
- **Ground truth for line calls:** a second phone at 240 fps on one line, plus two human umpires judging independently.
- **Split:** about 60/20/20 train/validation/test, **by session, never by frame**. The test set includes at least one time of day and one court condition (for example, rain-worn lines) unseen in training. The split files live in `data/splits/`.
- **Target size:** about 2,000 labelled ball frames, 500 player frames, 150 labelled bounces (50 within 20 cm of a line).
- **Known limits:** one court and few phones; the ball is tiny; near-line bounces are rare.
- **Not committed:** raw video and labels stay out of git. Put them under `data/` as described in `data/README.md` *(to be written in Week 1)*.

## 6. Usage *(planned interface)*

```bash
# 1. Calibrate: tap anchors on a reference frame, saves a homography file
python scripts/calibrate.py --video path/to/session.mp4 --out calib/session.json

# 2. Train the detector (transfer learning from COCO weights)
python scripts/train.py --config configs/detector.yaml

# 3. Evaluate on the held-out test split
python scripts/evaluate.py --config configs/detector.yaml --split test

# 4. Run inference on a new rally (Review mode)
python scripts/infer.py --video path/to/rally.mp4 --calib calib/session.json --out results/rally1/
```

Inference writes an annotated video, a JSON file of bounce events (court coordinates, call, margin, confidence) and the running score.

## 6b. Field-test console *(implemented)*

`/field` is a separate live-testing console for player, racket, ball and court
overlays. It is designed for a Coolify deployment on a GPU machine.

- **Channels:** add phone-browser cameras or RTSP streams. Only one channel is
  decoded and inferred at a time. Activating another channel stops the previous
  worker.
- **Phone camera:** open `/camera/<token>` on a phone over HTTPS, start the
  camera, then activate that channel. The phone tab must stay open and awake.
- **Detections:** COCO `person`, `sports ball`, `tennis racket` plus the
  clay HSV/3-frame ball fallback.
- **Court calibration:** per-camera manual 4-corner tap, auto painted-line
  suggestion, or optional segmentation weights via
  `CLEAR_COURT_SEG_WEIGHTS`.
- **Outputs:** annotated live view, snapshots, and per-session JSONL detection
  events under `/data/sessions/`.

Deployment files: `Dockerfile`, `docker-compose.yml`, `docker-compose.cpu.yml`, `DEPLOY.md`, `deploy/coolify.md`.

## 7. Models

| Model | Approach | Status |
|---|---|---|
| Ball and player detector | Pretrained COCO YOLO (nano or small), backbone frozen first, then unfrozen at a lower learning rate | Not yet trained |
| Temporal ball model | TrackNet-style network on 3 stacked frames, pretrained on public tennis data, fine-tuned on UCU clay data | Not yet trained |
| Phone export | FP16 and INT8 versions | Not yet exported |

Final weights: `models/` or download link *(to be added in Week 6)*.

## 8. Baselines and planned experiments

- **B1** Pretrained COCO YOLO without fine-tuning. **B2** Painted-line detection (edges and Hough) for calibration. **B3** Simple vertical-velocity sign change for bounces.
- **C1** Baseline vs fine-tuned detector. **C2** Single-frame vs 3-frame temporal model. **C3** Anchor calibration vs painted-line detection on fresh, worn and wiped lines. **C4** FP32 vs FP16 vs INT8. **C5** Same model across times of day and surface conditions.

Each comparison uses the same split and input size and changes one factor. Results go in `results/` with the configuration that produced them.

## 9. Evaluation and success criteria

| Category | Target (may be revised after the baseline, with the reason recorded) |
|---|---|
| Model quality | Ball F1 at least 0.80 (5 px tolerance) on the unseen-condition test set; median bounce error at most 15 cm; at least 80% call agreement with the umpires, with every call in the doubt zone flagged as uncertain |
| Engineering | Final model runs from a clean inference script on an unseen video; at least 15 FPS on the phone, or Review mode runs reliably |
| Practical | Output understood and usable by at least five student players; SUS of 70 or higher |

Results table *(to be filled in)*:

| Metric | Baseline | Final |
|---|---|---|
| Ball F1 | | |
| Median bounce error (cm) | | |
| Call agreement with umpires | | |
| FPS on phone | | |

## 10. Limitations and responsible use

- CLEAR is an **assistant**, not an official umpire. A human has the final say, and players can challenge any call.
- A single phone cannot recover the ball's 3D position in the air, so only the bounce is judged. The bounce point is estimated from fitted trajectories and carries an uncertainty margin.
- Results from one court and a small number of phones may not carry over to other courts.
- **Privacy:** written consent from players; no face recognition; videos on access-controlled UCU storage; faces blurred in report figures; deletion on request, in line with the Uganda Data Protection and Privacy Act, 2019.

## 11. Project timeline

| Week | Target |
|---|---|
| 1 | Place anchors, record sessions, label, inspect, preprocess, finalise task definition |
| 2 | Baselines B1 to B3, anchor calibration, scoring engine |
| 3 | Fine-tune the detector, evaluate, analyse errors |
| 4 | Controlled experiments C1 to C3, temporal model, bounce estimation |
| 5 | Tracking, robustness tests, quantization and phone export (C4, C5) |
| 6 | Final integration, unseen-data testing, usability test, demonstration |

## 12. AI assistance statement

*(To be completed for the final report: the main AI tools used, what they were used for, and how important outputs were checked.)*

## 13. References

1. Y.-C. Huang et al., "TrackNet: A deep learning network for tracking high-speed and tiny objects in sports applications," IEEE AVSS, 2019.
2. Y. Zhang et al., "ByteTrack: Multi-object tracking by associating every detection box," ECCV, 2022.
3. T. Tarashima et al., "Widely applicable strong baseline for sports ball detection and tracking," BMVC, 2023.
4. T.-Y. Lin et al., "Microsoft COCO: Common objects in context," ECCV, 2014.
5. B. Jacob et al., "Quantization and training of neural networks for efficient integer-arithmetic-only inference," CVPR, 2018.

## 14. Licence

*(To be decided by the group. Code licence and dataset licences are separate; see Data notes.)*
