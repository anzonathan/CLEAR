'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { resolveWsUrl } from '@/lib/webrtc';

/** Encoding settings, set by developers in Dev tools > Streaming and pushed over the ingest socket. */
interface StreamConfig {
  width: number;
  quality: number;
  fps: number;
  adaptive: boolean;
  min_width: number;
  min_quality: number;
  min_fps: number;
}

// Used until the server sends its settings (first status message, within ~2 s).
const FALLBACK: StreamConfig = {
  width: 1280,
  quality: 0.75,
  fps: 8,
  adaptive: true,
  min_width: 960,
  min_quality: 0.65,
  min_fps: 4,
};

/** Short tone sequence through the phone speaker. The AudioContext is created on the
 *  "Start camera" tap, because mobile browsers only allow sound after a user gesture. */
function playTones(ctx: AudioContext | null, notes: number[], step = 0.16) {
  if (!ctx) return;
  ctx.resume().catch(() => {});
  const t0 = ctx.currentTime + 0.02;
  notes.forEach((freq, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    const at = t0 + i * step;
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(0.6, at + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + step * 0.95);
    osc.connect(gain).connect(ctx.destination);
    osc.start(at);
    osc.stop(at + step);
  });
}

const START_CHIME = [660, 880, 1320]; // rising: recording has started
const END_CHIME = [880, 520]; // falling: game over

type LinkState = 'idle' | 'connecting' | 'standby' | 'preview' | 'live' | 'offline' | 'rejected';

const LINK_COPY: Record<LinkState, { title: string; detail: string }> = {
  idle: { title: 'Camera off', detail: 'Start your camera, then mount the phone behind your end of the court.' },
  connecting: { title: 'Connecting', detail: 'Linking your camera to CLEAR…' },
  standby: { title: 'Ready', detail: 'Your camera is linked. Frames are sent once the game starts.' },
  preview: { title: 'Calibrating', detail: 'The referee is lining up your camera with the court. Keep the phone still.' },
  live: { title: 'Live', detail: 'Streaming to the referee. Keep this screen open and awake.' },
  offline: { title: 'Reconnecting', detail: 'Connection dropped. Retrying…' },
  rejected: { title: 'Link rejected', detail: 'This camera slot changed. Reload the page.' },
};

/**
 * Adaptive step-down when the uplink cannot keep up (frames pile up in the socket buffer).
 * Order: frame rate first, then JPEG quality, then resolution, because fewer but sharper
 * frames keep the ball detectable; never below the developer's floors.
 */
function stepDown(eff: StreamConfig, cfg: StreamConfig): StreamConfig | null {
  if (eff.fps > cfg.min_fps) return { ...eff, fps: Math.max(cfg.min_fps, eff.fps - 1) };
  if (eff.quality > cfg.min_quality + 0.001) return { ...eff, quality: Math.max(cfg.min_quality, +(eff.quality - 0.05).toFixed(2)) };
  if (eff.width > cfg.min_width) return { ...eff, width: Math.max(cfg.min_width, eff.width - 160) };
  return null;
}

function stepUp(eff: StreamConfig, cfg: StreamConfig): StreamConfig | null {
  if (eff.width < cfg.width) return { ...eff, width: Math.min(cfg.width, eff.width + 160) };
  if (eff.quality < cfg.quality - 0.001) return { ...eff, quality: Math.min(cfg.quality, +(eff.quality + 0.05).toFixed(2)) };
  if (eff.fps < cfg.fps) return { ...eff, fps: Math.min(cfg.fps, eff.fps + 1) };
  return null;
}

function sameTarget(a: StreamConfig, b: StreamConfig) {
  return (Object.keys(a) as (keyof StreamConfig)[]).every((k) => a[k] === b[k]);
}

export default function CameraStreamer({ cameraId, token }: { cameraId: string; token: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const timersRef = useRef<number[]>([]);
  const loopRef = useRef<number | null>(null);
  const runningRef = useRef(false);
  const activeRef = useRef(false);
  const inFlightRef = useRef(false);
  const wakeRef = useRef<{ release: () => Promise<void> } | null>(null);
  const sentRef = useRef(0);
  const audioRef = useRef<AudioContext | null>(null);
  const wasLiveRef = useRef(false);

  // Target settings from the server, and what is actually used after adaptive step-downs.
  const cfgRef = useRef<StreamConfig>(FALLBACK);
  const effRef = useRef<StreamConfig>(FALLBACK);
  const congestedRef = useRef(0);
  const calmWindowsRef = useRef(0);
  const lastFrameBytesRef = useRef(40_000);
  const frameSizeRef = useRef<[number, number]>([0, 0]);

  const [link, setLink] = useState<LinkState>('idle');
  const [running, setRunning] = useState(false);
  const [fps, setFps] = useState(0);
  const [eff, setEff] = useState<StreamConfig>(FALLBACK);

  const setEffective = (next: StreamConfig) => {
    effRef.current = next;
    setEff(next);
  };

  const requestWakeLock = async () => {
    try {
      const nav = navigator as Navigator & { wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> } };
      if (nav.wakeLock && !wakeRef.current) wakeRef.current = await nav.wakeLock.request('screen');
    } catch {
      /* Wake lock is best effort; the copy already asks to keep the screen on. */
    }
  };

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= 1) return;
    setLink('connecting');
    const ws = new WebSocket(
      `${resolveWsUrl()}/ws/field/ingest/${encodeURIComponent(cameraId)}/?token=${encodeURIComponent(token)}`
    );
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;
    ws.onopen = () => {
      setLink('standby');
      ws.send('ping');
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== 'string') return;
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type !== 'status') return;

      if (msg.stream && !sameTarget(msg.stream, cfgRef.current)) {
        // New target from Dev tools: jump straight to it; adaptive works down from there.
        cfgRef.current = msg.stream;
        setEffective(msg.stream);
        calmWindowsRef.current = 0;
      }

      // Frames flow whenever the server wants them, game or calibration preview.
      activeRef.current = !!msg.active;
      const live = !!msg.active && msg.mode !== 'preview';
      setLink(live ? 'live' : msg.active ? 'preview' : 'standby');
      // Signal the start (and end) of the game on the phone itself: players are on court,
      // not looking at the screen. Calibration previews stay silent.
      if (live && !wasLiveRef.current) {
        playTones(audioRef.current, START_CHIME);
        navigator.vibrate?.([120, 60, 120]);
      } else if (!live && wasLiveRef.current) {
        playTones(audioRef.current, END_CHIME, 0.22);
        navigator.vibrate?.(300);
      }
      wasLiveRef.current = live;
    };
    ws.onclose = (ev) => {
      activeRef.current = false;
      if (ev.code === 1008) {
        setLink('rejected');
        return;
      }
      if (runningRef.current) {
        setLink('offline');
        window.setTimeout(connect, 1500);
      }
    };
  }, [cameraId, token]);

  const sendFrame = async () => {
    const video = videoRef.current;
    const ws = wsRef.current;
    if (!runningRef.current || !activeRef.current || inFlightRef.current) return;
    if (!video || !video.videoWidth || !ws || ws.readyState !== 1) return;
    // Uplink still busy with earlier frames: drop this one rather than queue latency.
    if (ws.bufferedAmount > lastFrameBytesRef.current * 1.5) {
      congestedRef.current += 1;
      return;
    }
    inFlightRef.current = true;
    try {
      const e = effRef.current;
      const scale = Math.min(1, e.width / video.videoWidth);
      const w = Math.round(video.videoWidth * scale);
      const h = Math.round(video.videoHeight * scale);
      const canvas = canvasRef.current || (canvasRef.current = document.createElement('canvas'));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      frameSizeRef.current = [w, h];
      canvas.getContext('2d', { alpha: false })?.drawImage(video, 0, 0, w, h);
      const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, 'image/jpeg', e.quality));
      if (blob && ws.readyState === 1) {
        lastFrameBytesRef.current = blob.size;
        ws.send(await blob.arrayBuffer());
        sentRef.current += 1;
      }
    } finally {
      inFlightRef.current = false;
    }
  };

  // Self-scheduling loop so a frame-rate change applies on the next tick.
  const frameLoop = () => {
    sendFrame();
    loopRef.current = window.setTimeout(frameLoop, 1000 / Math.max(1, effRef.current.fps));
  };

  // Every 2 s: adapt, and tell the server what is really being sent.
  const adaptTick = () => {
    const cfg = cfgRef.current;
    if (activeRef.current && cfg.adaptive) {
      if (congestedRef.current > 0) {
        const next = stepDown(effRef.current, cfg);
        if (next) setEffective(next);
        calmWindowsRef.current = 0;
      } else if (++calmWindowsRef.current >= 3) {
        const next = stepUp(effRef.current, cfg);
        if (next) setEffective(next);
        calmWindowsRef.current = 0;
      }
    }
    const throttled = congestedRef.current > 0 || !sameTarget(effRef.current, cfg);
    congestedRef.current = 0;
    const ws = wsRef.current;
    if (activeRef.current && ws?.readyState === 1) {
      // Report the encoding in force now, even if congestion means no frame went out this window.
      const v = videoRef.current;
      const e = effRef.current;
      const w = v?.videoWidth ? Math.round(Math.min(e.width, v.videoWidth)) : frameSizeRef.current[0];
      const h = v?.videoWidth ? Math.round((w * v.videoHeight) / v.videoWidth) : frameSizeRef.current[1];
      ws.send(JSON.stringify({ type: 'stats', w, h, q: e.quality, fps: e.fps, throttled }));
    }
  };

  const stop = useCallback(() => {
    runningRef.current = false;
    activeRef.current = false;
    timersRef.current.forEach((t) => window.clearInterval(t));
    timersRef.current = [];
    if (loopRef.current) window.clearTimeout(loopRef.current);
    loopRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    wsRef.current?.close();
    wsRef.current = null;
    wakeRef.current?.release().catch(() => {});
    wakeRef.current = null;
    wasLiveRef.current = false;
    audioRef.current?.close().catch(() => {});
    audioRef.current = null;
    setRunning(false);
    setLink('idle');
    setFps(0);
  }, []);

  const start = async () => {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      toast.error('Camera needs a secure connection', {
        description: 'Open CLEAR through its https:// address on your phone.',
      });
      return;
    }
    // Unlock audio now, inside the tap, so the start chime can play later.
    try {
      const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (AC && !audioRef.current) {
        audioRef.current = new AC();
        playTones(audioRef.current, [0.0001]); // silent unlock for iOS
      }
    } catch {
      /* no audio: the on-screen state still changes */
    }
    try {
      // Capture at 1080p when the phone allows it, so Dev tools can raise the sent
      // resolution without restarting the camera. Frames are downscaled before sending.
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          frameRate: { ideal: 30, max: 30 },
        },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      runningRef.current = true;
      setRunning(true);
      connect();
      requestWakeLock();
      frameLoop();
      timersRef.current.push(window.setInterval(adaptTick, 2000));
      // Heartbeat keeps the slot "online" while the game has not started.
      timersRef.current.push(
        window.setInterval(() => {
          if (!activeRef.current && wsRef.current?.readyState === 1) wsRef.current.send('ping');
        }, 5000)
      );
      timersRef.current.push(
        window.setInterval(() => {
          setFps(sentRef.current);
          sentRef.current = 0;
        }, 1000)
      );
    } catch (err) {
      toast.error('Could not open the camera', {
        description: err instanceof Error ? err.message : 'Allow camera access and try again.',
      });
    }
  };

  useEffect(() => stop, [stop]);

  const copy = LINK_COPY[link];
  const sending = link === 'live' || link === 'preview';
  const reduced = sending && !sameTarget(eff, cfgRef.current);

  return (
    <div className="camera-streamer">
      <div className={`camera-stage ${running ? 'is-running' : ''}`}>
        <video ref={videoRef} playsInline muted />
        {!running && (
          <div className="camera-stage-empty">
            <svg className="icon" width="32" height="32" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
          </div>
        )}
        <span className={`link-chip link-${link}`}>
          <i aria-hidden="true" />
          {copy.title}
          {link === 'live' && fps > 0 ? ` · ${fps} fps` : ''}
        </span>
        {sending && (
          <span className={`encode-chip ${reduced ? 'is-reduced' : ''}`}>
            {eff.width}px · q{Math.round(eff.quality * 100)}
            {reduced ? ' · weak signal' : ''}
          </span>
        )}
      </div>
      <p className="muted camera-note" aria-live="polite">{copy.detail}</p>
      {running ? (
        <button type="button" className="btn btn-secondary" onClick={stop}>
          Stop camera
        </button>
      ) : (
        <button type="button" className="btn btn-primary" onClick={start}>
          Start camera
        </button>
      )}
    </div>
  );
}
