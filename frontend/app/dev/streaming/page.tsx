'use client';

import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { getLiveStreams, getStreamSettings, saveStreamSettings, LiveStreamStat, StreamSettings } from '@/lib/api';
import { END_LABEL } from '@/lib/game-format';

type Editable = Omit<StreamSettings, 'updated_at' | 'updated_by'>;

const PRESETS: { key: string; label: string; note: string; values: Partial<Editable> }[] = [
  {
    key: 'detail',
    label: 'Max detail',
    note: 'Fast wifi or 5G at the court. Best ball visibility.',
    values: { width: 1920, quality: 0.8, fps: 10, min_width: 1280, min_quality: 0.7, min_fps: 5 },
  },
  {
    key: 'balanced',
    label: 'Balanced',
    note: 'Good 4G. Ball stays visible up to the net.',
    values: { width: 1280, quality: 0.75, fps: 8, min_width: 960, min_quality: 0.65, min_fps: 4 },
  },
  {
    key: 'saver',
    label: 'Data saver',
    note: 'Weak signal. Fewer frames, ball still kept large.',
    values: { width: 1280, quality: 0.65, fps: 5, min_width: 960, min_quality: 0.6, min_fps: 3 },
  },
];

// Phone frames are sent 16:9. JPEG size depends on the scene, so this is only a starting
// model (bits per pixel vs quality, typical of denoised phone video). It is NOT validated on
// court footage: once phones stream, estimates are rescaled by their measured frame sizes.
const bitsPerPixel = (q: number) => 0.15 + 1.2 * q * q;
const kbpsAt = (scale: number) => (w: number, q: number, fps: number) =>
  (w * ((w * 9) / 16) * bitsPerPixel(q) * scale * fps) / 1000;
const mbps = (kbps: number) => (kbps / 1000).toFixed(kbps < 1000 ? 2 : 1);

// Ball (6.7 cm) size in pixels for a phone mounted ~3 m behind the baseline.
const BALL_M = 0.067;
const DIST = { net: 15, far: 27 } as const;
const ballPx = (width: number, fovDeg: number, d: number) => (BALL_M * width) / (2 * d * Math.tan((fovDeg * Math.PI) / 360));
// The colour/motion ball detector ignores blobs under 2 px radius (src/detect/detector.py).
const MIN_BALL_PX = 4;

function Slider({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
  hint,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
  hint?: string;
}) {
  return (
    <label className="ss-slider">
      <span className="ss-slider-top">
        <span>{label}</span>
        <b>{format(value)}</b>
      </span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      {hint && <span className="muted">{hint}</span>}
    </label>
  );
}

function BallMeter({ px, label }: { px: number; label: string }) {
  const ok = px >= MIN_BALL_PX;
  const marginal = !ok && px >= MIN_BALL_PX * 0.75;
  return (
    <div className={`ball-meter ${ok ? 'ok' : marginal ? 'marginal' : 'lost'}`}>
      <span className="ball-dot" style={{ width: Math.max(2, px * 3), height: Math.max(2, px * 3) }} aria-hidden="true" />
      <div>
        <b>{px.toFixed(1)} px</b>
        <span>{label}</span>
      </div>
      <em>{ok ? 'Detectable' : marginal ? 'Borderline' : 'Too small'}</em>
    </div>
  );
}

export default function StreamingPage() {
  const [saved, setSaved] = useState<StreamSettings | null>(null);
  const [form, setForm] = useState<Editable | null>(null);
  const [live, setLive] = useState<LiveStreamStat[]>([]);
  const [fov, setFov] = useState(70);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getStreamSettings()
      .then((s) => {
        setSaved(s);
        setForm(s);
      })
      .catch((err) => toast.error('Could not load settings', { description: err.message }));
    const loadLive = () => getLiveStreams().then((r) => setLive(r.cameras)).catch(() => {});
    loadLive();
    const t = window.setInterval(loadLive, 2000);
    return () => window.clearInterval(t);
  }, []);

  // Measured/modelled ratio from phones streaming right now (median), else 1.
  const scale = useMemo(() => {
    const ratios = live
      .filter((c) => c.avg_kb && c.width && c.height && c.quality)
      .map((c) => (c.avg_kb! * 8000) / (c.width! * c.height!) / bitsPerPixel(c.quality!))
      .sort((a, b) => a - b);
    return ratios.length ? ratios[Math.floor(ratios.length / 2)] : null;
  }, [live]);
  const kbpsFor = kbpsAt(scale ?? 1);

  const dirty = useMemo(
    () => !!(form && saved && (Object.keys(form) as (keyof Editable)[]).some((k) => form[k] !== saved[k])),
    [form, saved]
  );

  if (!form) {
    return (
      <div className="loader" style={{ padding: '60px 0' }}>
        <i></i>
        <i></i>
        <i></i>
      </div>
    );
  }

  const set = (patch: Partial<Editable>) => {
    const next = { ...form, ...patch };
    // Keep floors at or below their targets as the targets move.
    next.min_width = Math.min(next.min_width, next.width);
    next.min_quality = Math.min(next.min_quality, next.quality);
    next.min_fps = Math.min(next.min_fps, next.fps);
    setForm(next);
  };

  const save = async () => {
    setBusy(true);
    try {
      const s = await saveStreamSettings(form);
      setSaved(s);
      setForm(s);
      toast.success('Streaming settings saved', { description: 'Phones pick them up within a few seconds.' });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save');
    } finally {
      setBusy(false);
    }
  };

  const activePreset = PRESETS.find((p) => (Object.keys(p.values) as (keyof Editable)[]).every((k) => p.values[k] === form[k]));
  const target = kbpsFor(form.width, form.quality, form.fps);
  const floor = kbpsFor(form.min_width, form.min_quality, form.min_fps);
  const worstWidth = form.adaptive ? form.min_width : form.width;

  return (
    <>
      <div className="admin-topbar">
        <div>
          <h3>Streaming</h3>
          <p className="muted">
            How phones send video to the referee. Changes reach running cameras within a few seconds.
            {saved?.updated_by && ` Last changed by ${saved.updated_by}.`}
          </p>
        </div>
        <button type="button" className="btn btn-primary" disabled={!dirty || busy} onClick={save}>
          {busy ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
        </button>
      </div>

      <section className="panel">
        <div className="section-heading">
          <h3>Presets</h3>
          <span className="ss-figure">
            {scale ? 'Mbps estimates scaled to the phones streaming now' : 'Mbps estimates are rough until a phone streams'}
          </span>
        </div>
        <div className="ss-presets" role="radiogroup" aria-label="Presets">
          {PRESETS.map((p) => (
            <button
              key={p.key}
              type="button"
              role="radio"
              aria-checked={activePreset?.key === p.key}
              className={`ss-preset ${activePreset?.key === p.key ? 'active' : ''}`}
              onClick={() => set(p.values)}
            >
              <b>{p.label}</b>
              <span>{p.note}</span>
              <em>
                {p.values.width}px · q{Math.round((p.values.quality ?? 0) * 100)} · {p.values.fps} fps · ~
                {mbps(kbpsFor(p.values.width!, p.values.quality!, p.values.fps!))} Mbps
              </em>
            </button>
          ))}
        </div>
      </section>

      <div className="ss-grid">
        <section className="panel">
          <div className="section-heading">
            <h3>Target</h3>
            <span className="ss-figure">~{mbps(target)} Mbps per phone</span>
          </div>
          <Slider
            label="Resolution (width)"
            value={form.width}
            min={480}
            max={1920}
            step={160}
            format={(v) => `${v} × ${Math.round((v * 9) / 16)}`}
            onChange={(v) => set({ width: v })}
            hint="The biggest lever for seeing the ball. Phones capture 1080p and scale down to this."
          />
          <Slider
            label="JPEG quality"
            value={form.quality}
            min={0.4}
            max={0.95}
            step={0.05}
            format={(v) => `${Math.round(v * 100)}`}
            onChange={(v) => set({ quality: +v.toFixed(2) })}
            hint="Below ~65 compression smears a small yellow ball into the court colour."
          />
          <Slider
            label="Frame rate"
            value={form.fps}
            min={2}
            max={15}
            step={1}
            format={(v) => `${v} fps`}
            onChange={(v) => set({ fps: v })}
            hint="More frames track the ball's flight better; costs bandwidth linearly."
          />

          <label className="ss-toggle">
            <input type="checkbox" checked={form.adaptive} onChange={(e) => set({ adaptive: e.target.checked })} />
            <span>
              <b>Adapt to weak signal</b>
              <span className="muted">
                When a phone&apos;s upload falls behind it lowers frame rate first, then quality, then resolution,
                never below the floors.
              </span>
            </span>
          </label>
        </section>

        <section className={`panel ${form.adaptive ? '' : 'ss-disabled'}`} aria-disabled={!form.adaptive}>
          <div className="section-heading">
            <h3>Floors</h3>
            <span className="ss-figure">~{mbps(floor)} Mbps minimum</span>
          </div>
          <Slider
            label="Lowest resolution"
            value={form.min_width}
            min={480}
            max={form.width}
            step={160}
            format={(v) => `${v}px`}
            onChange={(v) => set({ min_width: v })}
          />
          <Slider
            label="Lowest quality"
            value={form.min_quality}
            min={0.4}
            max={form.quality}
            step={0.05}
            format={(v) => `${Math.round(v * 100)}`}
            onChange={(v) => set({ min_quality: +v.toFixed(2) })}
          />
          <Slider
            label="Lowest frame rate"
            value={form.min_fps}
            min={1}
            max={form.fps}
            step={1}
            format={(v) => `${v} fps`}
            onChange={(v) => set({ min_fps: v })}
          />
          <p className="muted">A phone that cannot sustain the floors drops frames instead of blurring the ball.</p>
        </section>

        <section className="panel ss-ball">
          <div className="section-heading">
            <h3>Can the detector see the ball?</h3>
          </div>
          <label className="field ss-fov">
            PHONE LENS
            <div className="segmented" role="radiogroup" aria-label="Lens">
              {[
                { v: 70, l: 'Main (~70°)' },
                { v: 100, l: 'Ultra-wide (~100°)' },
              ].map((o) => (
                <button key={o.v} type="button" role="radio" aria-checked={fov === o.v} className={fov === o.v ? 'active' : ''} onClick={() => setFov(o.v)}>
                  {o.l}
                </button>
              ))}
            </div>
          </label>
          <div className="ss-ball-cols">
            <div>
              <span className="eyebrow">AT TARGET · {form.width}px</span>
              <BallMeter px={ballPx(form.width, fov, DIST.net)} label="ball at the net" />
              <BallMeter px={ballPx(form.width, fov, DIST.far)} label="ball at the far baseline" />
            </div>
            {form.adaptive && form.min_width !== form.width && (
              <div>
                <span className="eyebrow">AT FLOOR · {worstWidth}px</span>
                <BallMeter px={ballPx(worstWidth, fov, DIST.net)} label="ball at the net" />
                <BallMeter px={ballPx(worstWidth, fov, DIST.far)} label="ball at the far baseline" />
              </div>
            )}
          </div>
          <p className="muted">
            The ball detector needs about {MIN_BALL_PX} px across. Estimates assume the phone sits ~3 m behind its baseline.
            Each end&apos;s camera covers its own half best; the far baseline is the other camera&apos;s job.
          </p>
        </section>

        <section className="panel">
          <div className="section-heading">
            <h3>Detector input</h3>
          </div>
          <div className="segmented" role="radiogroup" aria-label="Detector input size">
            {[640, 960, 1280].map((v) => (
              <button key={v} type="button" role="radio" aria-checked={form.yolo_imgsz === v} className={form.yolo_imgsz === v ? 'active' : ''} onClick={() => set({ yolo_imgsz: v })}>
                {v}px
              </button>
            ))}
          </div>
          <p className="muted">
            YOLO shrinks every frame to this size to find players, rackets and the ball. Larger keeps small balls but
            costs ~2–4× more compute: use 960+ only on the GPU. Applies when the next game or calibration preview starts.
          </p>
        </section>
      </div>

      <section className="panel">
        <div className="section-heading">
          <h3>Phones right now</h3>
          {live.length > 0 && <span className="ss-figure">{mbps(live.reduce((a, c) => a + (c.kbps ?? 0), 0))} Mbps total</span>}
        </div>
        {live.length === 0 ? (
          <p className="muted list-empty">No phone is connected.</p>
        ) : (
          <div className="ss-table" role="table">
            <div className="ss-row ss-head" role="row">
              <span role="columnheader">Phone</span>
              <span role="columnheader">Sending</span>
              <span role="columnheader">Frame rate</span>
              <span role="columnheader">Frame size</span>
              <span role="columnheader">Upload</span>
            </div>
            {live.map((c) => (
              <div key={c.camera_id} className="ss-row" role="row">
                <span role="cell">
                  <b>{c.player ?? c.camera_id}</b>
                  <span className="muted">{c.pair ? `${c.pair} · ${c.end ? END_LABEL[c.end] : ''}` : 'No game'}</span>
                </span>
                <span role="cell">
                  {c.width ? `${c.width}×${c.height} · q${Math.round((c.quality ?? 0) * 100)}` : 'Standby'}
                  {c.throttled && <em className="ss-weak">weak signal</em>}
                </span>
                <span role="cell">
                  {c.fps ?? 0}
                  {c.target_fps ? ` / ${c.target_fps}` : ''} fps
                </span>
                <span role="cell">{c.avg_kb ? `${c.avg_kb} KB` : '—'}</span>
                <span role="cell">
                  <b>{c.kbps ? `${mbps(c.kbps)} Mbps` : '—'}</b>
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
