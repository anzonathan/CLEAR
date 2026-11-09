# CLEAR court footage dataset: metadata

This is the metadata for the raw footage in the team Drive (`Videos/Day`, `Videos/Night` and `Photos`). It is modelled on the caltennis dataset on Hugging Face.

## Files

| File | One row per | Who fills it |
|------|-------------|--------------|
| `clip_metadata.csv` | raw video | Pre-filled from the Drive. **Robert fills the empty columns.** |
| `photo_metadata.csv` | raw photo | Pre-filled from the Drive. **Robert fills the empty columns.** |
| `manifest.csv` (made by the notebook) | processed clip | Generated. It joins this metadata with measured values (codec, fps, length, calibration status, split). |

## `clip_metadata.csv` columns

| Column | Meaning | Example |
|--------|---------|---------|
| `file` | Original file name on the Drive | `IMG_0313.mov` |
| `drive_folder` | Where it sits on the Drive | `Videos/Day` |
| `lighting` | `day` or `night` (floodlights) | `night` |
| `device` | Phone model, if known. Otherwise `iPhone` or `Android`. | `iPhone 13` |
| `lens` | Which lens was used: `main`, `ultrawide` or `telephoto`. The notebook fills this from the file when it can. | `main` |
| `uploaded_by` | Who recorded or uploaded it | `Nathaniel` |
| `recorded_date` | When it was filmed. The notebook reads this from the video file, so leave it blank if unknown. | `2026-11-04 19:42` |
| `court` | Court number at UCU | `2` |
| `camera_position` | Where the phone stood: `near`, `far`, `near_left`, `near_right` or `side` | `near_left` |
| `camera_height_m` | Approximate height of the phone above the court | `1.5` |
| `include` | `False` drops the clip, for example if it's junk or a duplicate | `True` |
| `keep_segments` | The parts of the clip to keep, in min:sec. Empty keeps the whole clip. | `0:10-1:35; 2:40-4:05` |
| `players` | How many players are in shot | `2` |
| `weather` | `sunny`, `overcast`, `after_rain`, etc. | `overcast` |
| `court_condition` | How visible the lines are: `clear`, `faint`, `none`, `wet` | `faint` |
| `notes` | Anything unusual: camera bumped, ultra-wide lens, people walking past | `phone moved at 2:10` |
| `drive_file_id` | Drive file ID, so the clip can always be found | (pre-filled) |
| `drive_size_mb` | Size on the Drive | (pre-filled) |

## `photo_metadata.csv` columns

| Column | Meaning |
|--------|---------|
| `taken_at` | Read from the file name |
| `court`, `lighting` | Same as for clips |
| `view` | `full_court`, `baseline`, `service_box`, `net_post`, `close_up` |
| `lines_visible` | `clear`, `faint` or `none` |
| `use_for` | `lines` (default), `calibration` or `both` |
| `include`, `notes`, `drive_file_id` | Same as for clips |

## `camera_specs.csv`: the recording phones

This file has one row per phone lens, taken from the spec sheets: focal length, aperture, sensor size, field of view, stabilization and video modes. The phones are a Samsung Galaxy S20 FE (confirmed by Robert) and an iPhone (likely an iPhone 13, going by its dual camera specs; please confirm). The notebook reads the exact phone and lens from each video file where the phone stores it. iPhones do; Android phones often don't.

`approx_focal_px_1080p` is a rough starting point for the camera's focal length in pixels at 1920x1080: (35 mm-equivalent focal length / 36) x 1920. It's only approximate, because video stabilization crops the frame. A checkerboard calibration per phone gives the real value and the lens distortion.

**Use the main lens (26 mm) for recording.** The 13 mm ultrawide bends straight lines, which hurts calibration (PER-6). The notebook prints a warning for any clip recorded on the ultrawide lens.

## What we know so far (from the Drive, 9 Nov 2026)

- 8 videos. 6 iPhone `.mov` files (3 day, 3 night) were uploaded on 5 Nov. 2 Android `.mp4` files (night) were recorded on 21 Oct at 19:48 and 19:50.
- 11 photos (`.heic`, day) taken on 21 Oct between 13:50 and 13:52.
- The recording time of the iPhone clips is stored inside each file, and the notebook reads it out (stage 1).
