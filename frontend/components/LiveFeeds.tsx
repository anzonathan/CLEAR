'use client';

import { useEffect, useRef, useState } from 'react';
import { resolveWsUrl } from '@/lib/webrtc';
import CourtDiagram from './CourtDiagram';

interface CamMeta {
  online?: boolean;
  fps?: number;
  inference_ms?: number;
  device?: string;
  detections?: Record<string, number>;
  calibration?: { ready?: boolean };
}

/** One camera's annotated stream: JPEG frames as binary messages, stats as JSON. */
export function CameraFeed({ cameraId, label, who }: { cameraId: string; label: string; who?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [meta, setMeta] = useState<CamMeta | null>(null);
  const [state, setState] = useState<'connecting' | 'live' | 'waiting' | 'denied'>('connecting');
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    let closed = false;
    let ws: WebSocket;
    const open = () => {
      ws = new WebSocket(`${resolveWsUrl()}/ws/field/view/${encodeURIComponent(cameraId)}/`);
      ws.binaryType = 'blob';
      ws.onmessage = (ev) => {
        if (typeof ev.data === 'string') {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === 'meta') setMeta(msg.camera);
            if (msg.type === 'state') setState('waiting');
          } catch {
            /* ignore */
          }
          return;
        }
        const next = URL.createObjectURL(ev.data as Blob);
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = next;
        setSrc(next);
        setState('live');
      };
      ws.onclose = (ev) => {
        if (closed) return;
        if (ev.code === 1008) setState('denied');
        else window.setTimeout(open, 2000);
      };
    };
    open();
    return () => {
      closed = true;
      ws?.close();
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, [cameraId]);

  const det = meta?.detections ?? {};
  return (
    <figure className="feed">
      <div className="feed-frame">
        {src ? <img src={src} alt={`${label} live view`} /> : <span className="muted">{state === 'denied' ? 'Not allowed' : 'Waiting for frames…'}</span>}
        <span className={`link-chip link-${state === 'live' && meta?.online ? 'live' : 'standby'}`}>
          <i aria-hidden="true" />
          {label}
        </span>
      </div>
      <figcaption>
        <span>{who ?? '—'}</span>
        <span className="feed-stats">
          {meta?.fps != null && <>{Number(meta.fps).toFixed(1)} fps</>}
          {meta?.inference_ms != null && <> · {Math.round(meta.inference_ms)} ms</>}
          {meta?.device && <> · {meta.device}</>}
          {Object.keys(det).length > 0 && <> · {Object.entries(det).map(([k, v]) => `${k} ${v}`).join(', ')}</>}
          {meta?.calibration && !meta.calibration.ready && <> · <b className="warn">uncalibrated</b></>}
        </span>
      </figcaption>
    </figure>
  );
}

interface Fused {
  frame_index: number;
  ball: { x_m: number; y_m: number; speed_kmh: number; conf: number; is_predicted: boolean; source_camera: string } | null;
  players: Record<string, { label: string; court_half: string; x_m: number; y_m: number; speed_kmh: number }>;
  ball_trail: number[][];
}

/** Fused two-camera state from /ws/field/match/, drawn on a court. */
export function LiveCourt({ cameraNames }: { cameraNames: Record<string, string> }) {
  const [fused, setFused] = useState<Fused | null>(null);
  const [topSpeed, setTopSpeed] = useState(0);

  useEffect(() => {
    let closed = false;
    let ws: WebSocket;
    const open = () => {
      ws = new WebSocket(`${resolveWsUrl()}/ws/field/match/`);
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'fused' && msg.fused) {
            setFused(msg.fused);
            const s = msg.fused.ball?.speed_kmh ?? 0;
            setTopSpeed((t) => (s > t && s < 300 ? s : t));
          }
        } catch {
          /* ignore */
        }
      };
      ws.onclose = (ev) => {
        if (!closed && ev.code !== 1008) window.setTimeout(open, 2000);
      };
    };
    open();
    return () => {
      closed = true;
      ws?.close();
    };
  }, []);

  const ball = fused?.ball;
  const players = Object.entries(fused?.players ?? {}).map(([id, p]) => ({ id: p.label || id, x: p.x_m, y: p.y_m }));
  return (
    <div className="live-court">
      <CourtDiagram
        label="Fused live court"
        ball={ball ? { x: ball.x_m, y: ball.y_m, predicted: ball.is_predicted } : null}
        trail={(fused?.ball_trail ?? []).map(([x, y]) => ({ x, y }))}
        players={players}
      />
      <dl className="live-readout">
        <div><dt>Ball speed</dt><dd>{ball ? Math.round(ball.speed_kmh) : '—'}<small> km/h</small></dd></div>
        <div><dt>Top speed</dt><dd>{topSpeed ? Math.round(topSpeed) : '—'}<small> km/h</small></dd></div>
        <div><dt>Seen by</dt><dd className="small">{ball ? cameraNames[ball.source_camera] ?? ball.source_camera : '—'}{ball?.is_predicted ? ' (predicted)' : ''}</dd></div>
        <div><dt>Players</dt><dd>{players.length}</dd></div>
        <div><dt>Frame</dt><dd className="small">{fused?.frame_index ?? '—'}</dd></div>
      </dl>
    </div>
  );
}
