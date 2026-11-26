# CLEAR: Exam Finalisation Guide

**Course:** CSC3118 / CSC3218 Computer Vision and Deep Learning, Advent 2026
**Exam type:** 100% project-based (source: `Exam/CSC3118 Computer Vision  Deep learning - Exam.pdf`)
**Group 1:** Andrea Nabuuma, Robert Wanyama, Blair Tonny, Nathaniel Mugenyi
**Written:** Thursday 26 November 2026
**Internal deadline:** everything submittable by **Sunday 29 November 2026, 20:00**

---

## 1. What the exam actually asks for

The exam is not "build something new". It is: take the semester prototype and turn it into a **functional, evaluated, deployed, defensible** system. Two rules shape everything:

- **"Claims unsupported by evidence shall not earn marks."** Every number in the report needs a script, a file in `results/`, and a figure or table that is interpreted in the text.
- **"High predictive accuracy alone does not establish methodological validity."** A clean split on real footage with honest, modest numbers beats perfect numbers on easy data.

### Marks at a glance

| Milestone | What | Marks | Where we stand |
|---|---|---|---|
| M1 | Finalisation plan and data integrity | 15 | Weak. Raw footage and metadata exist; no split manifests, no leakage checks, metadata half-filled |
| M2 | Model refinement, evaluation, failure analysis | 20 | **Weakest.** All reported metrics come from a synthetic video. No fine-tuned model. No real test set |
| M3 | System engineering and deployment | 30 | **Strongest.** Web platform deployed, two-camera live mode, recording, analysis. Needs benchmarks, tests, pinned deps, upload path |
| M4 | Live demo and individual oral defence | 20 | Depends on rehearsal and each person owning a component |
| M5 | Report, slides, documentation | 15 | Not started. Lots of raw material in `README.md`, `MILESTONE.md`, `Docs/` |

M3 + M4 = 50 marks. Protect the working system first, then fix the evidence gap in M2.

### Submission checklist (all via Moodle only)

- [ ] **(a) Deployed app:** URL `https://clear.ucu-dct.org` that examiners can reach **plus** local launch instructions (`LOCAL_TEST.md`), **plus** a 3–5 min backup demo video on unseen realistic inputs
- [ ] **(b) Technical report:** 10–15 page PDF, Trebuchet MS 12 pt, 1.5 spacing, justified, IEEE references
- [ ] **(c) Slides:** 10–15 slides, PDF or PPTX
- [ ] **(d) Source code:** Git repo link (or archive) with pinned deps, inference and evaluation code, automated tests
- [ ] **(e) Dataset documentation and split manifests:** licences, locally collected data description, exact train/val/test file lists
- [ ] **(f) Live demo and oral defence:** every member present, each defends their own part

---

## 2. Honest gap analysis (read this first)

These are the issues an examiner will find in the first ten minutes. Fixing them is worth more than any new feature.

### 2.1 The headline metrics are from synthetic data

`results/eval/comparison_table.md` reports Ball F1 0.984, bounce error 2.2 cm and 100% call agreement. `scripts/evaluate.py` produces these from `src/data/synthetic_rally.py`, a rendered rally with perfect ground truth. The baseline also scores 0.984 F1 and 100% agreement, which shows the test is too easy to separate methods.

**What to do:** keep the synthetic benchmark, but relabel it honestly as a *controlled simulation / unit benchmark*. Do **not** present it as test-set performance. Add a real held-out evaluation (section 4, M2). If the real numbers are much lower, that is fine: report them and analyse why.

### 2.2 No trained model

README §7 says the detector and temporal model are "Not yet trained". The deployed system runs pretrained COCO `yolov8n.pt` plus the HSV/motion fallback. The exam expects a "finalised and justified architecture" compared to a baseline.

**What to do:** fine-tune YOLOv8n (or YOLOv8s) on a small set of labelled UCU frames. Even 300–500 labelled frames give a real B1 (zero-shot) vs fine-tuned comparison. If time runs out, the fallback is to justify the zero-shot hybrid as the final architecture and run the controlled ablations on real footage (YOLO-only vs HSV-only vs hybrid). Either way, the comparison must be on real frames.

### 2.3 No split manifests or leakage evidence (5 marks on one line)

M1(d) "appropriate partitioning and verifiable leakage prevention" is the single biggest data criterion. We have 8 clips. Frames from the same clip are highly correlated, so **split by clip, never by frame**.

### 2.4 Repo hygiene that costs M3(f) and M5(d) marks

- `requirements.txt` and `backend/requirements.txt` use ranges (`>=`), not pins. `uv.lock` exists for the root project only.
- Two copies of the vision code: `src/` and `backend/src/`. Tests import `src/`, the app runs `backend/src/`.
- `App/` (retired FastAPI console) is still in the repo, and its test `test_field_password_auth_gate` fails (17 passed, 1 failed on 2026-11-24).
- README still has sections marked *(planned)* and an empty results table.
- **Security:** seed accounts with public passwords are created on every start (`DEPLOY.md` §7). Disable or change them before the examiners get the URL.

### 2.5 Examiner-provided inputs (M4b, 4 marks)

Examiners will hand over their own clip or image. The current flow is "two phones film a live game". Check that `backend/apps/videos` gives a working **upload a video → run `ClearPipeline` → see calls** path in the UI. If it does not, this is the most important engineering task of the weekend.

---

## 3. Scope statement (M1a, copy into report)

- **User:** student players on the UCU outdoor clay courts, and the developer/operator who calibrates cameras.
- **Task:** detect and track the ball and players from phone video, map bounces to court metres via an anchor homography, and give an IN/OUT call with margin and confidence. Calls within ±15 cm are flagged as uncertain.
- **Operating environment:** one or two phones on tripods, 1080p, main lens, daylight and floodlit night, clay with faint or missing lines.
- **Does not claim to:** replace an umpire in official matches; identify players; work on other surfaces without retraining; judge balls in the air (only bounces); judge foot faults or service faults reliably (experimental, unvalidated).

---

## 4. Improvements, by milestone

Priority: **P0** = must do by Sunday, **P1** = do if time allows, **P2** = mention as future work.

### M1: Finalisation plan and data integrity (15)

| Pri | Task | Evidence produced |
|---|---|---|
| P0 | Finish `data_pipeline/metadata/clip_metadata.csv`: court, camera position, lighting, court condition, include flag for all 8 clips | Completed CSV, `DATASET_CARD.md` |
| P0 | Write `data/splits/train.txt`, `val.txt`, `test.txt` **by clip**. Suggested: test = 1 day clip + 1 night clip, val = 1 clip, train = the rest. Record the rule and the seed | Split manifests (deliverable e) |
| P0 | Leakage check script: perceptual hash (pHash/dHash) of every extracted frame; report cross-split near-duplicates (should be 0) and within-split duplicate rate | `results/integrity/leakage_report.json` + one table in report |
| P0 | Class/condition balance table: frames per split × day/night × court condition; ball-present vs ball-absent frames | Table + bar chart |
| P0 | Licence table: COCO (CC BY 4.0 annotations), yolov8n (AGPL-3.0, Ultralytics), any Roboflow/TrackNet data actually used. Remove sources we did not use | Table in report |
| P0 | Bias and shortcut notes: one court, two phones, few players, night floodlight colour shift, ball colour vs clay, player clothing colours | Half page in report |
| P1 | Consent record for filmed players (already claimed in README §10; make sure it exists) | Statement in report |

### M2: Model refinement, evaluation and failure analysis (20)

| Pri | Task | Evidence produced |
|---|---|---|
| P0 | Label ball (and player) boxes on frames from the 8 clips in Roboflow or CVAT. Target about 300–500 frames total, sampled every N frames, more from the test clips. Two members label the test clips; record agreement | YOLO-format labels, label counts |
| P0 | Hand-label bounce frames and IN/OUT for the test clips. Two members independently; report agreement (Cohen's kappa). This becomes ground truth for call agreement | `data/labels/test_bounces.json` |
| P0 | **Baseline B1:** zero-shot `yolov8n.pt` on the real test split. **Final:** hybrid detector and/or fine-tuned YOLO. Same split, same image size, one factor changed per run | `results/eval_real/*.json`, comparison table |
| P0 | Fine-tune YOLOv8n, two phases (frozen then unfrozen), `scripts/train.py` already has the plan. Select on **val**, test **once** | Training curves, `best.pt`, config |
| P0 | Metrics on real test: ball precision/recall/F1 at 5 px and 10 px, mAP@50 for ball and person, bounce detection recall, call agreement. Bootstrap 95% confidence intervals (few samples, so CIs matter) | Table with CIs |
| P0 | Ablations: YOLO-only vs HSV/motion-only vs hybrid; `imgsz` 640 vs 960 vs 1280 (this also closes open protocol P3) | Ablation table |
| P0 | Robustness: run the test split with degradations (JPEG quality 30, Gaussian blur / motion blur, gamma darkening, downscale to 640) and report F1 drop per condition. Also day vs night as natural domain shift | Robustness chart |
| P0 | Explainability: EigenCAM / Grad-CAM on YOLO for a few hits and misses (the `pytorch-grad-cam` package supports YOLOv8 via EigenCAM). Also the classic CV diagnostics: HSV mask and motion mask overlays | 4–6 overlay images |
| P0 | Failure gallery: 6–10 annotated failures, each with a cause (ball < 4 px at far court, motion blur, occlusion by player, yellow clothing, floodlight glare, line-call near doubt zone) | Figure grid + table |
| P1 | Calibration accuracy on real footage (open protocol P2): 10 known court points, error in cm | Table |
| P1 | Threshold calibration: sweep `ball_conf_thresh` on val, pick by F1, report reliability/calibration curve | PR curve |
| P2 | Temporal TrackNet-style model, INT8 phone export | Future work |

Keep the synthetic benchmark as a separate "controlled simulation" subsection. It is still useful to show that bounce estimation and the line judge are correct **when detection is correct**.

### M3: System engineering and deployment (30)

| Pri | Task | Evidence produced |
|---|---|---|
| P0 | Confirm the **upload clip → analyse → view calls** path works in the web UI, end to end, with a clip not used in training. Build it if missing | Screenshot, demo video |
| P0 | Input validation: wrong file type, empty/corrupt video, video with no court, uncalibrated camera, huge file. Each should give a clear message, not a 500 | Test cases + screenshots |
| P0 | Uncertain predictions visible in UI: doubt-zone calls shown as "uncertain, review", confidence shown | Screenshot |
| P0 | Benchmark script `scripts/benchmark.py`: ms per frame and FPS for detection, tracking and full pipeline at `imgsz` 640/960/1280, CPU vs GPU (closes P4). Report RAM/VRAM and model size | `results/benchmark.json` + table |
| P0 | Pin dependencies: `uv pip compile` / `pip freeze` into exact `==` versions for root and `backend/`. Docker images already give reproducibility; say so | Pinned files |
| P0 | Tests: delete `App/` and its failing test, or fix it. Point tests at `backend/src` and remove the duplicate `src/`, or add a CI check that they match. Add 3–5 sanity tests: homography round trip, line judge on known points, score engine, detector returns empty on a blank frame, API rejects bad upload | `pytest` all green, output saved |
| P0 | Disable public seed accounts in production; create examiner accounts with private passwords given in the Moodle submission | `DEPLOY.md` updated |
| P0 | Update `README.md`: remove *(planned)* labels, real results table, one launch path | README |
| P1 | GitHub Actions running `pytest` on push | Green badge |
| P1 | Architecture diagram (proxy → Next.js / Django+Channels → capture engine → GPU; Postgres, Redis) | Figure for report and slides |

### M4: Live demo and individual oral defence (20)

| Pri | Task |
|---|---|
| P0 | Demo script, 5 minutes: login → pair → two phones claim ends → auto-start → live fused court → stop → recorded analysis with calls. Then: upload an unseen clip |
| P0 | Edge-case drill: phone disconnects mid-game, wrong file uploaded, uncalibrated camera, dark clip, clip with no ball. Know what the app does in each |
| P0 | Offline fallback: the full stack runs locally with `docker compose --env-file .env.local up -d --build`. Test it on the demo laptop on venue Wi-Fi or a hotspot. Keep the backup video on the laptop and a USB stick |
| P0 | Each member owns one component and can explain it without notes (see section 6). Each member can also answer the shared questions below |
| P0 | Two full rehearsals with someone playing examiner and giving a surprise clip |

**Questions every member must answer:**
1. How was the data split, and why by clip and not by frame?
2. What is the baseline, what changed in the final model, and what was the gain on the real test set?
3. What does F1 at 5 px mean? Why not accuracy?
4. How does the homography work, and why anchors instead of painted lines?
5. What is the doubt zone and how is confidence computed?
6. Name two failure cases and their causes.
7. Why are the synthetic results not the test result?
8. What does the system not do?

### M5: Report and documentation (15)

Report structure (follows exam §5, target 13 pages):

| § | Section | Pages | Main sources |
|---|---|---|---|
| 0 | Title page + team contribution matrix | 1 | section 6 below |
| 1 | Executive summary, access/launch, key numbers | 1 | README, `DEPLOY.md` |
| 2 | Problem, scope, local relevance, data provenance, licences, integrity audit | 2.5 | M1 outputs, `DATASET_CARD.md` |
| 3 | Architecture, baseline, experiments, ablations | 2.5 | `Docs/zeroshot_experiment.md`, M2 outputs |
| 4 | Evaluation, explainability, robustness, failure analysis | 2.5 | M2 outputs |
| 5 | System architecture, workflow, benchmarks, error handling, testing | 2 | `MILESTONE.md`, `Docs/platform_experiments.md`, M3 outputs |
| 6 | Conclusion, limitations, ethics/privacy, future work, AI-use statement | 1 | README §10, §12 |
| | IEEE references | 0.5 | README §13 + new |

Format: **Trebuchet MS, 12 pt, 1.5 line spacing, justified, IEEE references.** Every figure and table gets a caption and at least one sentence of interpretation in the text.

Slides (12): title + team; problem and users; scope and non-goals; data and split; architecture; baseline vs final; robustness; explainability and failures; system and benchmarks; demo; limitations and ethics; contributions.

---

## 5. Timeline: Thursday 26 → Sunday 29 November

Owners are proposals. Change them in the first meeting, then do not change them again.

### Thursday 26 Nov (evening): lock scope and data

| Time | Task | Owner |
|---|---|---|
| 18:00–18:30 | Team call: agree on this guide, owners, split rule | All |
| 18:30–21:00 | Finish clip metadata; extract frames; write split manifests by clip | Robert |
| 18:30–21:00 | Set up labelling project (Roboflow/CVAT); start labelling train clips | Andrea, Blair |
| 18:30–21:00 | Check the upload-and-analyse path; fix seed accounts; start pinning deps | Nathaniel |

**End of day:** split manifests committed; labelling under way; list of engineering bugs known.

### Friday 27 Nov: labels, baselines, engineering fixes

| Time | Task | Owner |
|---|---|---|
| Morning | Finish labels for test clips (two labellers) and bounce/IN-OUT ground truth | Andrea, Blair |
| Morning | Leakage (pHash) script, balance table, licence table | Robert |
| Morning | Upload path, input validation, error messages | Nathaniel |
| Afternoon | Run **B1 zero-shot** and the HSV/hybrid ablations on the real test split; write `scripts/evaluate_real.py` | Blair |
| Afternoon | Finish train/val labels; start YOLO fine-tune on GPU | Andrea |
| Afternoon | Tests: remove `App/`, de-duplicate `src/`, add sanity tests, `pytest` green | Nathaniel |
| Evening | Benchmark script (CPU/GPU × imgsz) | Robert |

**End of day:** baseline numbers on real data exist; fine-tune running; `pytest` green.

### Saturday 28 Nov: final model, evaluation, writing starts

| Time | Task | Owner |
|---|---|---|
| Morning | Fine-tuned model on val → pick best → **single** test run; bootstrap CIs | Andrea |
| Morning | Robustness degradations; imgsz ablation | Blair |
| Morning | Explainability overlays (EigenCAM + masks); failure gallery | Robert |
| Morning | Deploy final model to the server; update README; architecture diagram | Nathaniel |
| Afternoon | Each member writes their report sections (section 6 ownership) | All |
| 16:00–17:00 | **Rehearsal 1:** full demo with a surprise clip; note every hiccup | All |
| Evening | Fix rehearsal issues; record backup demo video (3–5 min, unseen clip) | Nathaniel, Blair |

**End of day:** all numbers final; report draft 70%; backup video recorded.

### Sunday 29 Nov: finish, rehearse, submit

| Time | Task | Owner |
|---|---|---|
| Morning | Finish report; one person does formatting (font, spacing, IEEE, captions) | Robert (format), all (content) |
| Morning | Slides (12) | Andrea |
| Midday | Freeze code; tag release `v1.0-exam`; confirm URL and examiner logins work from a phone on mobile data | Nathaniel |
| 14:00–15:00 | **Rehearsal 2:** demo + oral Q&A, each member answers the 8 questions | All |
| 15:00–18:00 | Final read-through; cross-check every number in the report against `results/` | All |
| 18:00–20:00 | Export PDFs; package dataset docs and manifests; upload everything to Moodle; screenshot the submission receipt | Robert + Nathaniel |

**Cut-off rule:** if fine-tuning is not done by Saturday 12:00, stop it. Present the zero-shot hybrid as the final model, with the real-data ablations as the controlled experiments, and list fine-tuning as future work.

---

## 6. Ownership and contribution matrix (proposal)

Marks are individual. Each person must have code commits and report sections in their name.

| Member | Owns (builds and defends) | Report sections |
|---|---|---|
| Andrea Nabuuma | Labelling, YOLO fine-tuning, model selection | §3 Architecture and experiments |
| Robert Wanyama | Dataset, metadata, split manifests, leakage checks, explainability | §2 Data and integrity |
| Blair Tonny | Real-data evaluation, ablations, robustness, failure analysis | §4 Evaluation and failures |
| Nathaniel Mugenyi | Web platform, deployment, calibration, benchmarks, tests | §5 System, §1 Summary |

Shared: §6 Conclusion and ethics, slides, demo.

---

## 7. Notes and risks

- **Data volume is the main risk.** Eight clips is small. Say so in the report; it is a limitation, not a hidden flaw. Split by clip and report confidence intervals.
- **Test once.** Tune on val. If the test set is used for tuning, that is leakage, and an examiner will ask.
- **Do not break the deployed system.** Work on branches; deploy only after `pytest` passes and a local run works. Freeze code on Sunday midday.
- **Synthetic results:** keep them, label them clearly, and explain what they do and do not prove.
- **Privacy:** blur faces in report figures; keep raw footage off public Git; state consent and the Uganda Data Protection and Privacy Act, 2019.
- **AI-use statement:** required in spirit by exam §6. List the tools used and how outputs were checked. Every member must be able to trace the code they present.
- **Network on exam day:** the hosted URL depends on the server and Cloudflare tunnel. Always have the local Docker fallback and the backup video ready.
- **Examiner access:** test the URL and logins from outside the UCU network before submitting.
