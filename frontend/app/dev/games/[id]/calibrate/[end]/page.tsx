'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { toast } from 'sonner';
import {
  autoCalibrate,
  cameraSnapshotUrl,
  getCalibration,
  getDevGame,
  saveCalibration,
  startCalibrationPreview,
  stopCalibrationPreview,
  AnchorsPx,
  DevGame,
  GameEnd,
} from '@/lib/api';
import { fromAbsolute, toAbsolute, VIEW_ANCHORS } from '@/lib/anchors';
import { END_LABEL } from '@/lib/game-format';
import CourtDiagram from '@/components/CourtDiagram';

type Points = Record<string, [number, number]>; // camera-view key -> pixel

function quality(cm: number) {
  if (cm <= 10) return { label: 'Good', cls: 'good' };
  if (cm <= 25) return { label: 'Usable', cls: 'ok' };
  return { label: 'Poor: re-place the points', cls: 'poor' };
}

export default function CalibratePage() {
  const { id, end: endParam } = useParams<{ id: string; end: string }>();
  const end = (endParam === 'end_b' ? 'end_b' : 'end_a') as GameEnd;
  const other: GameEnd = end === 'end_a' ? 'end_b' : 'end_a';

  const [game, setGame] = useState<DevGame | null>(null);
  const [frame, setFrame] = useState<{ url: string; w: number; h: number } | null>(null);
  const [frameError, setFrameError] = useState<string | null>(null);
  const [points, setPoints] = useState<Points>({});
  const [current, setCurrent] = useState(VIEW_ANCHORS[0].key);
  const [saved, setSaved] = useState<{ method: string; cm: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [overlayTick, setOverlayTick] = useState(0);
  const imgRef = useRef<HTMLImageElement>(null);

  const cam = game?.ends[end].camera ?? null;
  const camId = cam?.id;
  const streaming = !!cam?.active;

  const loadGame = useCallback(async () => {
    try {
      setGame(await getDevGame(id));
    } catch (err) {
      toast.error('Could not load game', { description: err instanceof Error ? err.message : undefined });
    }
  }, [id]);

  useEffect(() => {
    loadGame();
    const t = window.setInterval(loadGame, 3000);
    return () => window.clearInterval(t);
  }, [loadGame]);

  // Existing calibration for this camera, mapped into the camera's own view.
  useEffect(() => {
    if (!camId) return;
    getCalibration(camId)
      .then(({ calibration }) => {
        if (!calibration) return;
        const pts: Points = {};
        Object.entries(calibration.anchors_px).forEach(([abs, px]) => {
          pts[fromAbsolute(abs, end)] = px;
        });
        setPoints(pts);
        setSaved({ method: calibration.method, cm: calibration.reproj_error_cm });
      })
      .catch(() => {});
  }, [camId, end]);

  const captureFrame = useCallback(async () => {
    if (!camId) return;
    try {
      const res = await fetch(cameraSnapshotUrl(camId, true), { credentials: 'include' });
      if (!res.ok) {
        setFrameError(res.status === 404 ? 'No frame yet. Make sure the camera is streaming.' : `Snapshot failed (${res.status})`);
        return;
      }
      const url = URL.createObjectURL(await res.blob());
      const img = new Image();
      img.onload = () => {
        setFrame((old) => {
          if (old) URL.revokeObjectURL(old.url);
          return { url, w: img.naturalWidth, h: img.naturalHeight };
        });
        setFrameError(null);
      };
      img.src = url;
    } catch {
      setFrameError('Snapshot failed. Check the connection.');
    }
  }, [camId]);

  // Grab a first still as soon as frames flow.
  useEffect(() => {
    if (streaming && !frame) captureFrame();
  }, [streaming, frame, captureFrame]);

  // The preview is NOT stopped on unmount: moving to the other end's page would stop it
  // and let the game auto-start mid-calibration. "Done" stops it explicitly.

  // Live overlay check refreshes once per second after a save.
  useEffect(() => {
    if (!saved || !streaming) return;
    const t = window.setInterval(() => setOverlayTick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, [saved, streaming]);

  const advance = (pts: Points) => {
    const next = VIEW_ANCHORS.find((a) => !pts[a.key]);
    if (next) setCurrent(next.key);
  };

  const handleClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!frame) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * frame.w;
    const y = ((e.clientY - rect.top) / rect.height) * frame.h;
    const pts = { ...points, [current]: [Math.round(x * 10) / 10, Math.round(y * 10) / 10] as [number, number] };
    setPoints(pts);
    advance(pts);
  };

  const removePoint = (key: string) => {
    const pts = { ...points };
    delete pts[key];
    setPoints(pts);
    setCurrent(key);
  };

  const handleSave = async () => {
    if (!camId) return;
    const anchors: AnchorsPx = {};
    Object.entries(points).forEach(([view, px]) => {
      anchors[toAbsolute(view, end)] = px;
    });
    setBusy(true);
    try {
      const res = await saveCalibration(camId, anchors, 'manual');
      setSaved({ method: res.method, cm: res.reproj_error_cm });
      const q = quality(res.reproj_error_cm);
      toast.success(`Calibration saved · ${res.reproj_error_cm} cm error`, { description: q.label });
      loadGame();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save calibration');
    } finally {
      setBusy(false);
    }
  };

  const handleAuto = async () => {
    if (!camId) return;
    setBusy(true);
    try {
      const res = await autoCalibrate(camId);
      const pts: Points = {};
      Object.entries(res.anchors_px).forEach(([abs, px]) => {
        pts[fromAbsolute(abs, end)] = px;
      });
      setPoints(pts);
      if (res.reproj_error_cm != null) setSaved({ method: 'auto', cm: res.reproj_error_cm });
      await captureFrame();
      toast.success('Court detected and saved', {
        description: `${Math.round(res.confidence * 100)}% confidence. Check the overlay, adjust points if needed.`,
      });
      loadGame();
    } catch (err) {
      toast.error('Auto-detect failed', { description: err instanceof Error ? err.message : undefined });
    } finally {
      setBusy(false);
    }
  };

  const handlePreview = async (on: boolean) => {
    setBusy(true);
    try {
      setGame(await (on ? startCalibrationPreview(id) : stopCalibrationPreview(id)));
      if (on) {
        setFrame(null);
        toast.success('Cameras on for calibration', { description: 'Nothing is recorded. Players hear no start chime.' });
      } else {
        toast.success('Preview stopped', { description: 'The game starts once both cameras are steady.' });
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  };

  if (!game) {
    return (
      <div className="loader" style={{ padding: '60px 0' }}>
        <i></i>
        <i></i>
        <i></i>
      </div>
    );
  }

  const pair = game.players.map((p) => p?.name ?? '?').join(' vs ');
  const player = game.ends[end].user?.name;
  const placed = VIEW_ANCHORS.filter((a) => points[a.key]).length;
  const requiredPlaced = VIEW_ANCHORS.filter((a) => a.required && points[a.key]).length;
  const currentAnchor = VIEW_ANCHORS.find((a) => a.key === current)!;
  const inPreview = !!cam?.preview;
  const canPreview = game.status === 'scheduled' && !!game.ends.end_a.camera && !!game.ends.end_b.camera;
  const q = saved ? quality(saved.cm) : null;

  return (
    <>
      <div className="admin-topbar dev-game-top">
        <div>
          <Link href={`/dev/games/${id}`} className="back-link">
            <svg className="icon" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><polyline points="15 18 9 12 15 6" /></svg>
            {pair}
          </Link>
          <h3>Calibrate {END_LABEL[end]}</h3>
          <p className="muted">
            {player ? `${player}'s phone` : 'No player on this end'} ·{' '}
            {cam?.online ? (streaming ? 'streaming' : 'camera on, not streaming') : 'camera off'}
            {saved && q && (
              <>
                {' '}· saved ({saved.method}) <b className={`calib-q ${q.cls}`}>{saved.cm} cm</b>
              </>
            )}
          </p>
        </div>
        <Link href={`/dev/games/${id}/calibrate/${other}`} className="btn btn-secondary">
          {END_LABEL[other]}
        </Link>
      </div>

      {!cam ? (
        <div className="panel">
          <p className="muted">No player has picked {END_LABEL[end]} yet. Calibration needs that phone&apos;s camera.</p>
        </div>
      ) : !streaming ? (
        <div className="panel calib-start">
          <div>
            <h3>Turn on the cameras</h3>
            <p className="muted">
              {game.status === 'scheduled'
                ? 'Both players tap Start camera on their phones, then start a preview. Frames flow without starting or recording the game.'
                : 'This camera is not streaming. Ask the player to start their camera.'}
            </p>
          </div>
          {canPreview && (
            <button type="button" className="btn btn-primary" disabled={busy || !cam.online} onClick={() => handlePreview(true)}>
              {cam.online ? 'Start camera preview' : 'Waiting for the phone…'}
            </button>
          )}
        </div>
      ) : null}

      {cam && (
        <div className="calib-layout">
          <section className="panel calib-frame-panel">
            <div className="calib-toolbar">
              <div className="calib-current" aria-live="polite">
                <span className="eyebrow">CLICK</span>
                <b>{currentAnchor.label}</b>
                <span className="muted">{currentAnchor.hint}</span>
              </div>
              <div className="calib-actions">
                <button type="button" className="btn btn-secondary" disabled={!streaming || busy} onClick={captureFrame}>New frame</button>
                <button type="button" className="btn btn-secondary" disabled={!streaming || busy} onClick={handleAuto}>Auto-detect</button>
              </div>
            </div>

            <div className="calib-frame">
              {frame ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img ref={imgRef} src={frame.url} alt={`Still from ${END_LABEL[end]} camera`} />
                  <svg viewBox={`0 0 ${frame.w} ${frame.h}`} onClick={handleClick} role="presentation">
                    {VIEW_ANCHORS.map((a, i) => {
                      const pt = points[a.key];
                      if (!pt) return null;
                      const r = Math.max(frame.w, frame.h) / 90;
                      return (
                        <g key={a.key} className={`calib-pin ${a.key === current ? 'is-current' : ''}`}>
                          <circle cx={pt[0]} cy={pt[1]} r={r} />
                          <line x1={pt[0] - r * 2.2} y1={pt[1]} x2={pt[0] + r * 2.2} y2={pt[1]} />
                          <line x1={pt[0]} y1={pt[1] - r * 2.2} x2={pt[0]} y2={pt[1] + r * 2.2} />
                          <text x={pt[0] + r * 1.6} y={pt[1] - r * 1.6} fontSize={r * 2.2}>{i + 1}</text>
                        </g>
                      );
                    })}
                  </svg>
                </>
              ) : (
                <span className="muted">{frameError ?? (streaming ? 'Grabbing a frame…' : 'No video yet')}</span>
              )}
            </div>
            <p className="muted calib-tip">
              Click exactly on the outside edge where the lines meet. Zoom the browser for precision. Re-click a point in the list to move it.
            </p>
          </section>

          <aside className="panel calib-steps">
            <div className="calib-map">
              <CourtDiagram
                label={`Court as seen from the ${END_LABEL[end]} camera`}
                topLabel="FAR"
                bottomLabel="▲ CAMERA"
                marks={VIEW_ANCHORS.map((a) => ({
                  key: a.key,
                  x: a.x,
                  y: a.y,
                  state: a.key === current ? 'current' : points[a.key] ? 'done' : 'todo',
                }))}
                onMarkClick={setCurrent}
              />
            </div>
            <div className="calib-count">
              <b>{requiredPlaced}/4</b> corners · {placed} points
            </div>
            <ol className="calib-list">
              {VIEW_ANCHORS.map((a, i) => (
                <li key={a.key} className={`${a.key === current ? 'is-current' : ''} ${points[a.key] ? 'is-done' : ''}`}>
                  <button type="button" onClick={() => setCurrent(a.key)}>
                    <span className="calib-n">{i + 1}</span>
                    {a.label}
                    {a.required && <em>required</em>}
                  </button>
                  {points[a.key] && (
                    <button type="button" className="calib-x" aria-label={`Remove ${a.label}`} onClick={() => removePoint(a.key)}>
                      ×
                    </button>
                  )}
                </li>
              ))}
            </ol>
            <button type="button" className="btn btn-primary" disabled={busy || placed < 4} onClick={handleSave}>
              Save calibration
            </button>
            {placed > 0 && (
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => { setPoints({}); setCurrent(VIEW_ANCHORS[0].key); }}>
                Clear points
              </button>
            )}
            {inPreview && (
              <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => handlePreview(false)}>
                Done: stop preview
              </button>
            )}
          </aside>

          {saved && streaming && camId && (
            <section className="panel calib-check">
              <div className="section-heading">
                <h3>Overlay check</h3>
                {q && <b className={`calib-q ${q.cls}`}>{q.label}</b>}
              </div>
              <p className="muted">The detector&apos;s live view with your calibration. Court lines should sit on the real lines.</p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="calib-overlay" src={`${cameraSnapshotUrl(camId, false)}&n=${overlayTick}`} alt="Live view with calibrated court overlay" />
            </section>
          )}
        </div>
      )}
    </>
  );
}
