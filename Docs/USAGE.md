# Using CLEAR

How to use the CLEAR web app, by role. For running it, see `LOCAL_TEST.md` (your machine) and `DEPLOY.md` (server).

CLEAR has three kinds of account. The role decides where you land after signing in.

| Role | Lands on | Can use |
|---|---|---|
| Player (`user`) | `/app` | Pairing, games, phone camera |
| Developer (`developer`) | `/dev` | Everything a player can, plus the developer tools |
| Admin (`admin`) | `/admin` | The admin dashboard only |

New accounts are players. An admin changes roles from the admin dashboard.

The public landing page is at `/`. Signed-in visitors see an **Open CLEAR** button there instead of the sign-up buttons.

---

## Players

### 1. Pair with your partner

You need to be paired before you can play together. Pairing is done once per partner.

1. Open **Pair** (the orange **+** in the tab bar).
2. One of you chooses **Share my code** and taps **Generate Pair Code**. The six-character code is valid for 10 minutes.
3. The other chooses **Enter a code**, types it and taps **Connect**.

Your partner now appears under **Connect**.

### 2. Start or schedule a game

Open your partner from **Connect**.

- **Start session now** creates a game that starts as soon as both cameras are ready.
- **Schedule for later** sets a date and time, singles or doubles, and an optional name.

Scheduled games appear under **Games** and on the home screen.

### 3. Set up your phone

Each player films one end of the court with their own phone.

1. Open the game on your phone. It must be the `https://` address: browsers block the camera on plain `http`.
2. Under **Court ends**, tap **Film this end** on End A or End B. Your partner takes the other end.
3. Mount the phone behind your baseline, high and steady, with the whole court in view. Use the main camera, not the ultra-wide.
4. Tap **Start camera** and allow camera access.

Keep the CLEAR tab open and the screen on. If you switch apps or lock the phone, the browser stops sending video.

### 4. Play

When both ends are claimed and both cameras have been on and steady for about 3 seconds, the game **starts by itself**. Each phone then:

- plays a rising chime and vibrates,
- shows **Live** with the frame rate,
- shows the resolution and quality it is sending. It shows **weak signal** if it had to lower them.

Both ends are recorded from the moment the game starts.

If the phone shows **Calibrating**, a developer is lining up the cameras. The game waits until they finish. There is no chime during calibration.

### 5. End the game

Tap **End game**. Both phones play a falling tone, and the recording is saved.

When a developer has analysed the recording, the game page shows in and out calls and the top speed for each end.

### Cancel a game

On a scheduled game, tap **Cancel game**. You cannot cancel a game after it has started.

---

## Developers

Developer tools are at `/dev`. The sidebar also links to the **Player app**, because developers can pair and play too.

### Game analysis (`/dev`)

All paired games are listed under **Live now**, **Recorded** and **Scheduled**. The A and B dots show whether each end's camera is on.

Open a game to see more.

- **Scheduled:**
  - Which player holds each end, and whether their camera is on.
  - Calibration status for each end.
- **Live:**
  - Both annotated camera feeds, with detection counts, inference time, upload rate and calibration warnings.
  - The **Fused court** beside them: the ball, its trail and the players, merged from both cameras, plus ball speed, top speed and which camera saw the ball.
  - **End game** stops the game for both players.
- **Recorded:**
  - **Analyse recording** runs the full offline pipeline on each end's recording: detection, tracking, bounce judge and faults.
  - The results show in, out and close calls, bounces, average and top speed, strokes, ball-tracking coverage, foot faults, service faults and court charts for each end.

Only one game can be live on the server at a time.

### Calibration

Calibration maps each phone's picture onto the real court. Without it, line calls are not reliable: the live feed shows **NO COURT CALIBRATION** and reports are marked **Uncalibrated**.

Calibrate both ends of every game, because phones are re-mounted each time.

1. Open the game in `/dev` and click **Calibrate** next to End A.
2. **Before the game starts:**
   1. Ask both players to tap **Start camera**.
   2. Click **Start camera preview**. The phones send video, but nothing is recorded and the game does not start.
3. **During a live game:** the video is already flowing, so you can calibrate straight away.
4. A still frame appears. The text above it names the point to click, and the court map on the right highlights it. The map is drawn as **this camera sees it**, so "near" is the baseline in front of the camera and "left" is the camera's left.
5. Click the four **corners**: near left, near right, far right, far left. Click the outside edge where the lines meet. Zoom the browser for precision.
6. Optional: add the net posts, service-line points or singles corners. More points give a better fit.
7. Click **Save calibration**. The error is shown in centimetres: up to 10 cm is good, up to 25 cm is usable, above that re-place the points.
8. Check the **Overlay check** image. The drawn court lines should sit on the real lines.
9. Switch to **End B** with the button at the top right and repeat.
10. Click **Done: stop preview**. The game then starts by itself once both cameras are steady.

Tools on the page:

- **Auto-detect** tries to find the court lines itself and saves the result. Always check the overlay after using it.
- **New frame** grabs a fresh still.
- **Clear points** starts over.

### Streaming (`/dev/streaming`)

This page controls how phones send video. Changes reach running phones within a few seconds, without restarting their cameras.

**Presets**

| Preset | Width | Quality | fps | Floors (width / quality / fps) |
|---|---|---|---|---|
| Max detail | 1920 | 80 | 10 | 1280 / 70 / 5 |
| Balanced (default) | 1280 | 75 | 8 | 960 / 65 / 4 |
| Data saver | 1280 | 65 | 5 | 960 / 60 / 3 |

**Target:** the resolution, JPEG quality and frame rate each phone aims for.

**Adapt to weak signal:** when a phone's upload falls behind, it lowers its settings in this order:

1. frame rate,
2. quality,
3. resolution.

It never goes below the **floors**, and it steps back up when the link clears. Lowering the frame rate first keeps each frame large and sharp enough to show the ball.

**Can the detector see the ball?** This panel estimates how many pixels across the ball is at the net and at the far baseline, for the target and for the floor:

- The ball detector needs about 4 px.
- Each end's camera mainly covers its own half; the far baseline is the other camera's job.
- The estimate assumes the phone is about 3 m behind its baseline. Choose **Ultra-wide** if players use that lens.

**Detector input:** the size YOLO shrinks frames to (640, 960 or 1280). Larger keeps small balls but costs more compute, so use 960 or above only on the GPU. It applies when the next game or calibration preview starts.

**Phones right now:** what each connected phone is actually sending, measured on the server: resolution, quality, frame rate, frame size and upload in Mbps, with **weak signal** when it has stepped down.

---

## Admins

The admin dashboard at `/admin` shows system statistics and the user list. From it you can:

- change a user's role,
- delete a user.

Admins cannot open the player app or the developer tools.

The Django admin is at `/django-admin/`. It is for maintenance only: games, stream settings and users can be inspected there.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Camera needs a secure connection" | Page opened over `http://` | Open the `https://` domain on the phone |
| Phone stuck on **Ready** | Game not started: partner's camera off, or a calibration preview running | Check the checklist on the game page; ask the developer to click **Done: stop preview** |
| Phone shows **Reconnecting** | Network dropped | It retries automatically; keep the tab open |
| Phone shows **weak signal** | Upload cannot keep up | Move closer to wifi, or pick **Data saver** in Streaming |
| "Another game is live right now" | The server runs one live game at a time | Wait for it to end, or end it from `/dev` |
| Live feed says **uncalibrated** | No calibration saved for that camera | Calibrate the end in `/dev` |
| Feed stats say `cpu` on the server | GPU not reachable from the container | See *GPU* in `DEPLOY.md` |
