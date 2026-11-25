'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  analyzeDevGame,
  devGameExportUrl,
  devGameVideoUrl,
  prepareDevGameVideo,
  saveDevGameSegments,
  AnalysisReport,
  DevGame,
  GameEnd,
  VideoKind,
  VideoPrepare,
  VideoSegment,
} from '@/lib/api';
import { END_LABEL } from '@/lib/game-format';

const ENDS: GameEnd[] = ['end_a', 'end_b'];
const SPEEDS = [0.25, 0.5, 1, 2];
const SEG_COLORS = ['#f28a24', '#bed95b', '#5aa9e6', '#e35d8f', '#9b7ede', '#2fb39a'];

type Marker = { t: number; kind: 'in' | 'out' | 'doubt' | 'fault'; title: string };

function fmtTime(t: number) {
  if (!Number.isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
}

function newId() {
  return Math.random().toString(36).slice(2, 10);
}

function isTyping(el: EventTarget | null) {
  const t = el as HTMLElement | null;
  return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
}

function markersFrom(report: AnalysisReport | undefined, out: Map<string, Marker>) {
  if (!report || report.error) return;
  const fps = report.fps || 30;
  for (const b of report.line_calling?.bounces ?? []) {
    const kind = b.in_doubt_zone ? 'doubt' : b.is_in ? 'in' : 'out';
    out.set(`b${b.frame_idx}`, {
      t: b.frame_idx / fps,
      kind,
      title: `${b.call} · ${b.abs_margin_cm} cm from line · ${b.speed_kmh} km/h${b.in_doubt_zone ? ' · close call' : ''}`,
    });
  }
  for (const f of report.fault_events ?? []) {
    out.set(`f${f.frame_idx}${f.fault_type}`, {
      t: f.frame_idx / fps,
      kind: 'fault',
      title: `${f.fault_type.replace('_', ' ')}: ${f.status}${f.reason ? ` · ${f.reason}` : ''}`,
    });
  }
}

export default function VideoTrimmer({ game, onGameChange }: { game: DevGame; onGameChange: (g: DevGame) => void }) {
  const ends = ENDS.filter((e) => game.videos?.[e]?.raw || game.videos?.[e]?.annotated);
  const [end, setEnd] = useState<GameEnd>(ends[0] ?? 'end_a');
  const [kind, setKind] = useState<VideoKind>('raw');
  const [prep, setPrep] = useState<VideoPrepare | null>(null);
  const [prepError, setPrepError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);
  const stopAtRef = useRef<number | null>(null);

  const [segments, setSegments] = useState<VideoSegment[]>(game.segments ?? []);
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'error'>('saved');
  const saveTimer = useRef<number | null>(null);
  const pendingSave = useRef<VideoSegment[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [inPoint, setInPoint] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const available = game.videos?.[end] ?? { raw: false, annotated: false };
  const effectiveKind: VideoKind = available[kind] ? kind : available.raw ? 'raw' : 'annotated';
  const fps = prep?.fps || 30;
  const totalFrames = prep?.frames || Math.round(duration * fps);
  const frame = Math.min(Math.max(0, totalFrames - 1), Math.floor(time * fps + 1e-4));
  const len = duration || prep?.duration_s || 0;

  // ------------------------------------------------------------- conversion
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    setPrep(null);
    setPrepError(null);
    setTime(0);
    setDuration(0);
    setPlaying(false);
    const poll = async () => {
      try {
        const res = await prepareDevGameVideo(game.id, end, effectiveKind);
        if (cancelled) return;
        if (res.state === 'error') {
          setPrepError(res.error ?? 'Could not prepare the video.');
          return;
        }
        setPrep(res);
        if (res.state === 'converting') timer = window.setTimeout(poll, 2000);
      } catch (err) {
        if (!cancelled) setPrepError(err instanceof Error ? err.message : 'Could not prepare the video.');
      }
    };
    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [game.id, end, effectiveKind]);

  // ------------------------------------------------------------- playback
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      const v = videoRef.current;
      if (v) {
        if (stopAtRef.current != null && v.currentTime >= stopAtRef.current) {
          v.pause();
          v.currentTime = stopAtRef.current - 0.5 / fps;
          stopAtRef.current = null;
        }
        setTime(v.currentTime);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, fps]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = rate;
  }, [rate, prep?.state]);

  const seek = useCallback(
    (t: number) => {
      const v = videoRef.current;
      if (!v) return;
      const clamped = Math.min(Math.max(0, t), Math.max(0, (v.duration || len) - 0.5 / fps));
      v.currentTime = clamped;
      setTime(clamped);
    },
    [fps, len]
  );

  const seekFrame = useCallback(
    (f: number) => {
      videoRef.current?.pause();
      // Aim at the middle of the frame so the browser shows exactly frame f.
      seek((Math.max(0, f) + 0.5) / fps);
    },
    [fps, seek]
  );

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      stopAtRef.current = null;
      v.play().catch(() => undefined);
    } else v.pause();
  }, []);

  // ------------------------------------------------------------- segments
  const flushSave = useCallback(async () => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = null;
    const next = pendingSave.current;
    if (!next) return true;
    pendingSave.current = null;
    setSaveState('saving');
    try {
      onGameChange(await saveDevGameSegments(game.id, next));
      setSaveState('saved');
      return true;
    } catch (err) {
      setSaveState('error');
      toast.error('Could not save segments', { description: err instanceof Error ? err.message : undefined });
      return false;
    }
  }, [game.id, onGameChange]);

  const commit = useCallback(
    (next: VideoSegment[]) => {
      setSegments(next);
      pendingSave.current = next;
      setSaveState('saving');
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(flushSave, 600);
    },
    [flushSave]
  );

  useEffect(() => () => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
  }, []);

  const frameStart = useCallback((f: number) => Math.round((f / fps) * 1000) / 1000, [fps]);

  const markIn = useCallback(() => setInPoint(frame), [frame]);

  const markOut = useCallback(() => {
    if (inPoint == null) {
      toast.message('Press I at the first frame of the segment first.');
      return;
    }
    const a = Math.min(inPoint, frame);
    const b = Math.max(inPoint, frame);
    const seg: VideoSegment = {
      id: newId(),
      end,
      label: `Segment ${segments.filter((s) => s.end === end).length + 1}`,
      start_s: frameStart(a),
      end_s: frameStart(b + 1), // end is exclusive: the out frame is included
    };
    commit([...segments, seg].sort((x, y) => (x.end === y.end ? x.start_s - y.start_s : x.end < y.end ? -1 : 1)));
    setSelected((s) => new Set(s).add(seg.id));
    setInPoint(null);
  }, [inPoint, frame, end, segments, commit, frameStart]);

  const updateSeg = (id: string, patch: Partial<VideoSegment>) =>
    commit(segments.map((s) => (s.id === id ? { ...s, ...patch } : s)));

  const removeSeg = (id: string) => {
    commit(segments.filter((s) => s.id !== id));
    setSelected((s) => {
      const n = new Set(s);
      n.delete(id);
      return n;
    });
  };

  const playSeg = (s: VideoSegment) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = s.start_s + 0.5 / fps;
    stopAtRef.current = s.end_s;
    v.play().catch(() => undefined);
  };

  // ------------------------------------------------------------- keyboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key;
      if (k === ' ') togglePlay();
      else if (k === ',') seekFrame(frame - 1);
      else if (k === '.') seekFrame(frame + 1);
      else if (k === 'ArrowLeft') seek(time - (e.shiftKey ? 5 : 1));
      else if (k === 'ArrowRight') seek(time + (e.shiftKey ? 5 : 1));
      else if (k === 'i' || k === 'I') markIn();
      else if (k === 'o' || k === 'O') markOut();
      else if (k === 'Escape') setInPoint(null);
      else return;
      e.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [togglePlay, seekFrame, seek, frame, time, markIn, markOut]);

  // ------------------------------------------------------------- timeline
  const timeAt = (clientX: number) => {
    const el = trackRef.current;
    if (!el || !len) return 0;
    const r = el.getBoundingClientRect();
    return (Math.min(Math.max(clientX - r.left, 0), r.width) / r.width) * len;
  };
  const onTrackDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!len) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    videoRef.current?.pause();
    seek(timeAt(e.clientX));
  };
  const onTrackMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) seek(timeAt(e.clientX));
  };

  const segReports = game.analysis?.segments ?? {};
  const markers = useMemo(() => {
    const m = new Map<string, Marker>();
    markersFrom(game.analysis?.cameras?.[end], m);
    for (const r of Object.values(segReports)) if (r.end === end) markersFrom(r, m);
    return Array.from(m.values());
  }, [game.analysis, end, segReports]);

  const endSegs = segments.filter((s) => s.end === end);
  const colorOf = (id: string) => SEG_COLORS[segments.findIndex((s) => s.id === id) % SEG_COLORS.length];
  const pct = (t: number) => `${len ? Math.min(100, Math.max(0, (t / len) * 100)) : 0}%`;

  // ------------------------------------------------------------- actions
  const selectedIds = segments.filter((s) => selected.has(s.id)).map((s) => s.id);
  const running = game.analysis_status === 'running';

  const analyse = async () => {
    if (!selectedIds.length) return;
    setBusy(true);
    try {
      if (!(await flushSave())) return;
      onGameChange(await analyzeDevGame(game.id, selectedIds));
      toast.success(`Analysing ${selectedIds.length} segment${selectedIds.length > 1 ? 's' : ''}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not start analysis');
    } finally {
      setBusy(false);
    }
  };

  const exportZip = async (ids?: string[]) => {
    setBusy(true);
    try {
      if (!(await flushSave())) return;
      const res = await fetch(devGameExportUrl(game.id, ids), { credentials: 'include' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || 'Export failed');
      }
      const blob = await res.blob();
      const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? `clear-${game.id}.zip`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setBusy(false);
    }
  };

  if (!ends.length) return null;

  const ready = prep?.state === 'ready';
  const analysedSelected = selectedIds.filter((id) => segReports[id] && !segReports[id].error);

  return (
    <section className="panel trimmer" aria-label="Recording preview and segments">
      <div className="trimmer-head">
        <div>
          <h3>Recording preview</h3>
          <p className="muted">Scrub the recording, mark segments with I and O, then analyse or export them.</p>
        </div>
        <div className="trimmer-switches">
          {ends.length > 1 && (
            <div className="segmented" role="group" aria-label="Camera end">
              {ends.map((e) => (
                <button key={e} type="button" className={e === end ? 'active' : ''} onClick={() => setEnd(e)}>
                  {END_LABEL[e]}
                </button>
              ))}
            </div>
          )}
          <div className="segmented" role="group" aria-label="Video">
            {(['raw', 'annotated'] as VideoKind[]).map((k) => (
              <button
                key={k}
                type="button"
                className={k === effectiveKind ? 'active' : ''}
                disabled={!available[k]}
                onClick={() => setKind(k)}
              >
                {k === 'raw' ? 'Raw' : 'Live overlay'}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="trimmer-stage">
        {ready ? (
          <video
            key={`${end}-${effectiveKind}`}
            ref={videoRef}
            src={devGameVideoUrl(game.id, end, effectiveKind)}
            preload="auto"
            playsInline
            muted
            onClick={togglePlay}
            onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || 0)}
            onPlay={() => setPlaying(true)}
            onPause={(e) => {
              setPlaying(false);
              setTime(e.currentTarget.currentTime);
            }}
            onSeeked={(e) => setTime(e.currentTarget.currentTime)}
          />
        ) : (
          <div className="trimmer-placeholder">
            {prepError ? (
              <p className="form-error">{prepError}</p>
            ) : (
              <>
                <div className="loader">
                  <i></i>
                  <i></i>
                  <i></i>
                </div>
                <p className="muted">
                  {prep?.state === 'converting'
                    ? `Preparing ${END_LABEL[end]} for the browser (first time only, ${fmtTime(prep.duration_s)} of video)…`
                    : 'Loading recording…'}
                </p>
              </>
            )}
          </div>
        )}
      </div>

      <div className="trimmer-controls">
        <button type="button" className="btn btn-primary trimmer-play" onClick={togglePlay} disabled={!ready} aria-label={playing ? 'Pause' : 'Play'}>
          {playing ? (
            <svg className="icon" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" /><rect x="14" y="5" width="4" height="14" /></svg>
          ) : (
            <svg className="icon" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><polygon points="7 4 20 12 7 20 7 4" /></svg>
          )}
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => seekFrame(frame - 1)} disabled={!ready} title="Previous frame (,)">
          −1f
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => seekFrame(frame + 1)} disabled={!ready} title="Next frame (.)">
          +1f
        </button>
        <div className="trimmer-readout" aria-live="off">
          <b>{fmtTime(time)}</b>
          <span>
            / {fmtTime(len)} · frame {ready ? frame : '–'}
            {totalFrames ? ` of ${totalFrames}` : ''} · {fps} fps
          </span>
        </div>
        <label className="trimmer-rate">
          <span className="sr-only">Playback speed</span>
          <select value={rate} onChange={(e) => setRate(Number(e.target.value))} disabled={!ready}>
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </label>
        <div className="trimmer-mark">
          <button type="button" className={`btn ${inPoint != null ? 'btn-primary' : 'btn-secondary'}`} onClick={markIn} disabled={!ready} title="Mark segment start (I)">
            {inPoint != null ? `In ${fmtTime(inPoint / fps)}` : 'Mark in'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={markOut} disabled={!ready || inPoint == null} title="Mark segment end (O)">
            Mark out
          </button>
        </div>
      </div>

      <div
        className={`trimmer-track ${ready ? '' : 'disabled'}`}
        ref={trackRef}
        onPointerDown={onTrackDown}
        onPointerMove={onTrackMove}
        role="slider"
        aria-label="Timeline"
        aria-valuemin={0}
        aria-valuemax={Math.round(len)}
        aria-valuenow={Math.round(time)}
        aria-valuetext={fmtTime(time)}
        tabIndex={0}
      >
        {endSegs.map((s) => (
          <div
            key={s.id}
            className={`trimmer-band ${selected.has(s.id) ? 'selected' : ''}`}
            style={{ left: pct(s.start_s), width: `calc(${pct(s.end_s)} - ${pct(s.start_s)})`, background: colorOf(s.id) }}
            title={`${s.label}: ${fmtTime(s.start_s)} – ${fmtTime(s.end_s)}`}
          />
        ))}
        {inPoint != null && (
          <div
            className="trimmer-band pending"
            style={{
              left: pct(Math.min(inPoint, frame) / fps),
              width: `calc(${pct((Math.max(inPoint, frame) + 1) / fps)} - ${pct(Math.min(inPoint, frame) / fps)})`,
            }}
          />
        )}
        {markers.map((m, i) => (
          <i key={i} className={`trimmer-marker ${m.kind}`} style={{ left: pct(m.t) }} title={`${fmtTime(m.t)} · ${m.title}`} />
        ))}
        <div className="trimmer-playhead" style={{ left: pct(time) }} />
      </div>
      <div className="trimmer-legend muted">
        <span><i className="trimmer-marker in" /> In</span>
        <span><i className="trimmer-marker out" /> Out</span>
        <span><i className="trimmer-marker doubt" /> Close call</span>
        <span><i className="trimmer-marker fault" /> Fault</span>
        <span className="trimmer-keys">
          <kbd>Space</kbd> play · <kbd>,</kbd>/<kbd>.</kbd> frame · <kbd>←</kbd>/<kbd>→</kbd> 1 s (<kbd>Shift</kbd> 5 s) · <kbd>I</kbd>/<kbd>O</kbd> in/out
        </span>
      </div>

      <div className="trimmer-segs">
        <div className="section-heading">
          <h4>
            Segments · {END_LABEL[end]} <small className="muted">({endSegs.length})</small>
          </h4>
          <span className={`trimmer-save ${saveState}`}>
            {saveState === 'saving' ? 'Saving…' : saveState === 'error' ? 'Not saved' : 'Saved'}
          </span>
        </div>
        {endSegs.length === 0 ? (
          <p className="muted">No segments yet. Pause on the first frame of a rally, press I, move to its last frame, press O.</p>
        ) : (
          <ul className="trimmer-seg-list">
            {endSegs.map((s) => {
              const rep = segReports[s.id];
              const stale = rep && (rep.start_s !== s.start_s || rep.end_s !== s.end_s);
              return (
                <li key={s.id} className={selected.has(s.id) ? 'selected' : ''}>
                  <input
                    type="checkbox"
                    aria-label={`Select ${s.label}`}
                    checked={selected.has(s.id)}
                    onChange={(e) =>
                      setSelected((prev) => {
                        const n = new Set(prev);
                        if (e.target.checked) n.add(s.id);
                        else n.delete(s.id);
                        return n;
                      })
                    }
                  />
                  <i className="trimmer-swatch" style={{ background: colorOf(s.id) }} aria-hidden="true" />
                  <input
                    className="trimmer-label"
                    value={s.label}
                    maxLength={80}
                    aria-label="Segment name"
                    onChange={(e) => updateSeg(s.id, { label: e.target.value })}
                  />
                  <button type="button" className="trimmer-time" onClick={() => seek(s.start_s + 0.5 / fps)} title="Jump to start">
                    {fmtTime(s.start_s)} – {fmtTime(s.end_s)} <small>({(s.end_s - s.start_s).toFixed(2)} s)</small>
                  </button>
                  <div className="trimmer-seg-actions">
                    <button type="button" className="btn btn-ghost" onClick={() => playSeg(s)} disabled={!ready}>
                      Play
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      disabled={!ready || frameStart(frame) >= s.end_s}
                      onClick={() => updateSeg(s.id, { start_s: frameStart(frame) })}
                      title="Set start to the current frame"
                    >
                      Start here
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      disabled={!ready || frameStart(frame + 1) <= s.start_s}
                      onClick={() => updateSeg(s.id, { end_s: frameStart(frame + 1) })}
                      title="Set end to the current frame (inclusive)"
                    >
                      End here
                    </button>
                    <button type="button" className="btn btn-ghost danger" onClick={() => removeSeg(s.id)} aria-label={`Delete ${s.label}`}>
                      Delete
                    </button>
                  </div>
                  <span className="trimmer-seg-status">
                    {running && selected.has(s.id) ? (
                      <span className="status-chip analysis-running">Analysing</span>
                    ) : !rep ? (
                      <span className="status-chip analysis-none">Not analysed</span>
                    ) : rep.error ? (
                      <span className="status-chip analysis-failed" title={rep.error}>Failed</span>
                    ) : (
                      <>
                        <span className={`status-chip ${stale ? 'analysis-running' : 'analysis-done'}`} title={stale ? 'Times changed since this analysis: run it again' : undefined}>
                          {stale ? 'Outdated' : 'Analysed'}
                        </span>
                        <small className="muted">
                          {rep.line_calling?.in_calls ?? 0} in · {rep.line_calling?.out_calls ?? 0} out · {rep.ball_tracking?.coverage_pct ?? 0}% tracked
                        </small>
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="trimmer-actions">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => setSelected(selectedIds.length === segments.length ? new Set() : new Set(segments.map((s) => s.id)))}
          disabled={!segments.length}
        >
          {selectedIds.length === segments.length && segments.length ? 'Select none' : 'Select all'}
        </button>
        <span className="muted">
          {selectedIds.length} of {segments.length} selected
          {segments.length !== endSegs.length ? ' (both ends)' : ''}
        </span>
        <div className="trimmer-actions-main">
          <button type="button" className="btn btn-primary" disabled={busy || running || !selectedIds.length} onClick={analyse}>
            {running ? 'Analysing…' : `Analyse selected${selectedIds.length ? ` (${selectedIds.length})` : ''}`}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy || !analysedSelected.length}
            onClick={() => exportZip(analysedSelected)}
            title="ZIP with summary, bounces, per-frame tracks and faults for the selected analysed segments"
          >
            Export selected
          </button>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => exportZip()} title="Every analysed run: full recordings and segments">
            Export all
          </button>
        </div>
      </div>
    </section>
  );
}
