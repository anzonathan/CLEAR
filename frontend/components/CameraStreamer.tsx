'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { resolveWsUrl } from '@/lib/webrtc';

// Same budget as the original field camera page: ~8 fps of 640px JPEGs keeps phones cool
// and fits a mobile uplink, which is plenty for the detector.
const SEND_INTERVAL_MS = 125;
const MAX_WIDTH = 640;
const JPEG_QUALITY = 0.66;

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

type LinkState = 'idle' | 'connecting' | 'standby' | 'live' | 'offline' | 'rejected';

const LINK_COPY: Record<LinkState, { title: string; detail: string }> = {
  idle: { title: 'Camera off', detail: 'Start your camera, then mount the phone behind your end of the court.' },
  connecting: { title: 'Connecting', detail: 'Linking your camera to CLEAR…' },
  standby: { title: 'Ready', detail: 'Your camera is linked. Frames are sent once the game starts.' },
  live: { title: 'Live', detail: 'Streaming to the referee. Keep this screen open and awake.' },
  offline: { title: 'Reconnecting', detail: 'Connection dropped. Retrying…' },
  rejected: { title: 'Link rejected', detail: 'This camera slot changed. Reload the page.' },
};

export default function CameraStreamer({ cameraId, token }: { cameraId: string; token: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const timersRef = useRef<number[]>([]);
  const runningRef = useRef(false);
  const activeRef = useRef(false);
  const inFlightRef = useRef(false);
  const wakeRef = useRef<{ release: () => Promise<void> } | null>(null);
  const sentRef = useRef(0);
  const audioRef = useRef<AudioContext | null>(null);
  const wasLiveRef = useRef(false);

  const [link, setLink] = useState<LinkState>('idle');
  const [running, setRunning] = useState(false);
  const [fps, setFps] = useState(0);

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
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'status') {
          activeRef.current = !!msg.active;
          setLink(msg.active ? 'live' : 'standby');
          // Signal the start (and end) of the game on the phone itself: players are on court, not looking at the screen.
          if (msg.active && !wasLiveRef.current) {
            playTones(audioRef.current, START_CHIME);
            navigator.vibrate?.([120, 60, 120]);
          } else if (!msg.active && wasLiveRef.current) {
            playTones(audioRef.current, END_CHIME, 0.22);
            navigator.vibrate?.(300);
          }
          wasLiveRef.current = !!msg.active;
        }
      } catch {
        /* ignore non-JSON */
      }
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
    inFlightRef.current = true;
    try {
      const scale = Math.min(1, MAX_WIDTH / video.videoWidth);
      const w = Math.round(video.videoWidth * scale);
      const h = Math.round(video.videoHeight * scale);
      const canvas = canvasRef.current || (canvasRef.current = document.createElement('canvas'));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      canvas.getContext('2d', { alpha: false })?.drawImage(video, 0, 0, w, h);
      const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, 'image/jpeg', JPEG_QUALITY));
      if (blob && ws.readyState === 1) {
        ws.send(await blob.arrayBuffer());
        sentRef.current += 1;
      }
    } finally {
      inFlightRef.current = false;
    }
  };

  const stop = useCallback(() => {
    runningRef.current = false;
    activeRef.current = false;
    timersRef.current.forEach((t) => window.clearInterval(t));
    timersRef.current = [];
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
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 },
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
      timersRef.current.push(window.setInterval(sendFrame, SEND_INTERVAL_MS));
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
