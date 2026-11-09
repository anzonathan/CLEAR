# PER-15 data preparation pipeline: how to run it

## 1. Put the notebook in the repo
Unzip `data_pipeline.zip` at the root of the CLEAR repo, which gives you `data_pipeline/` (the notebook, this README and `metadata/`). Stage 4 imports the PER-6 code from `src/calibration`. All data paths are relative to the repo root.

## 2. Get the footage
Download the team Drive folder into `data/raw/`, keeping its subfolders so `Night` is detected:
```
pip install gdown
gdown --folder https://drive.google.com/drive/folders/1mpN9RGYKGtV5kYiGkrbEDbaTSKlPzTbF -O data/raw
```
(Or download it from the Drive website and unzip it into `data/raw/`.) Add `data/` to `.gitignore`, because videos don't belong in git.

## 3. Install and run
```
sudo apt install ffmpeg            # or: brew install ffmpeg / choco install ffmpeg
pip install -r data_pipeline/requirements.txt
mkdir -p data/clear_dataset && cp data_pipeline/metadata/clip_metadata.csv data/clear_dataset/
jupyter notebook data_pipeline/data_preparation.ipynb
```
Run all cells.

## 4. Fill in the metadata, then run again
Open `data/clear_dataset/clip_metadata.csv` and fill in the blanks: `court`, `camera_position` (near / far / near_left ...), `lens`, `court_condition`, and so on. `metadata/DATASET_CARD.md` explains each column. Set `include` to False for junk clips. Then Run All again. Clips that are already compressed are skipped.

### Cutting out unneeded parts
Don't trim the videos in a video editor. It re-encodes the file and strips the recording time. Instead, write the parts to **keep** in the `keep_segments` column of `clip_metadata.csv`, for example `0:10-1:35; 2:40-4:05`. The notebook cuts them from the original, and each part becomes its own clip (`_s1`, `_s2`). Set `include` to False to drop a whole clip.

### Photos for lines
Put court photos in `data/raw/Photos/` (JPG or HEIC). They come out in `data/clear_dataset/line_images/`, resized to 1080p, with an automatic line mask for each one in `line_images/masks/`. Upload them to a separate Roboflow project for line annotation. You can use the mask as a starting point and just correct it.

## 5. Calibrate (PER-6)
For each clip, open `camera_calibration/<session>/<video_id>/reference.jpg` and note the pixel positions of at least 4 anchors (net post bases first). Save them as `data/taps/<session>/<video_id>.json`:
```json
{"net_post_left": [484, 415], "net_post_right": [1441, 415], "far_service_center": [963, 300], "near_service_center": [963, 620]}
```
Run again: `calib.json` changes from `needs_taps` to `anchors+lines` (or `anchors_only`), and you get a `preview.jpg` to check it.

## 6. Annotate in Roboflow, then augment
Upload `data/clear_dataset/frames/` to Roboflow and annotate. Export in YOLO format to `data/roboflow_export/train/` and rerun stage 6. Augmentation then moves the labels along with the images.

## 7. Upload
Upload `data/clear_dataset_<date>.zip` to the Drive under `Processed/`.
