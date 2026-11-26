'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  analyzeDevGame,
  devGameChartUrl,
  getDevGame,
  nextDevGame,
  recordDevGame,
  startDevGame,
  stopCalibrationPreview,
  stopDevGame,
  AnalysisReport,
  DevGame,
  GameEnd,
} from '@/lib/api';
import { END_LABEL, formatWhen, STATUS_LABEL } from '@/lib/game-format';
import { CameraFeed, LiveCourt } from '@/components/LiveFeeds';
import VideoTrimmer from '@/components/VideoTrimmer';

const ENDS: GameEnd[] = ['end_a', 'end_b'];

function Stat({ label, value, unit }: { label: string; value: React.ReactNode; unit?: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {value}
        {unit && <small> {unit}</small>}
      </dd>
    </div>
  );
}

function CalibrationStrip({ game, onChange }: { game: DevGame; onChange: (g: DevGame) => void }) {
  const previewing = !!(game.ends.end_a.camera?.preview || game.ends.end_b.camera?.preview);
  return (
    <section className="panel calib-strip" aria-label="Calibration">
      {previewing && (
        <div className="calib-strip-preview">
          <span className="muted">Calibration preview running. The game will not start until it stops.</span>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() =>
              stopCalibrationPreview(game.id)
                .then((g) => {
                  onChange(g);
                  toast.success('Preview stopped');
                })
                .catch((err) => toast.error(err.message))
            }
          >
            Done: stop preview
          </button>
        </div>
      )}
      {ENDS.map((e) => {
        const c = game.ends[e].camera;
        return (
          <div key={e} className="calib-strip-end">
            <div>
              <b>{END_LABEL[e]}</b>
              <span className="muted">
                {!c
                  ? 'No camera yet'
                  : c.calibrated
                  ? `Calibrated (${c.calib_method ?? 'manual'}${c.reproj_error_cm != null ? ` · ${c.reproj_error_cm} cm` : ''})`
                  : 'Not calibrated'}
              </span>
            </div>
            {c && (
              <Link href={`/dev/games/${game.id}/calibrate/${e}`} className={`btn ${c.calibrated ? 'btn-secondary' : 'btn-primary'}`}>
                {c.calibrated ? 'Recalibrate' : 'Calibrate'}
              </Link>
            )}
          </div>
        );
      })}
    </section>
  );
}

function ReportCard({ gameId, end, report }: { gameId: string; end: GameEnd; report: AnalysisReport }) {
  if (report.error) {
    return (
      <div className="panel report-card">
        <h4>{END_LABEL[end]}</h4>
        <p className="form-error">{report.error}</p>
      </div>
    );
  }
  const lc = report.line_calling;
  const bt = report.ball_tracking;
  return (
    <div className="panel report-card">
      <div className="section-heading">
        <h4>{END_LABEL[end]}</h4>
        {!report.calibrated && <span className="status-chip analysis-failed" title="Default camera geometry was used">Uncalibrated</span>}
      </div>
      <dl className="stat-grid">
        <Stat label="In" value={lc?.in_calls ?? 0} />
        <Stat label="Out" value={lc?.out_calls ?? 0} />
        <Stat label="Close calls" value={lc?.doubt_zone_calls ?? 0} />
        <Stat label="Bounces" value={lc?.total_bounces ?? 0} />
        <Stat label="Avg speed" value={bt?.avg_speed_kmh ?? 0} unit="km/h" />
        <Stat label="Top speed" value={bt?.max_speed_kmh ?? 0} unit="km/h" />
        <Stat label="Strokes" value={bt?.rally_strokes ?? 0} />
        <Stat label="Ball tracked" value={bt?.coverage_pct ?? 0} unit="%" />
        <Stat label="Foot faults" value={report.foot_faults?.length ?? 0} />
        <Stat label="Service faults" value={report.service_faults?.length ?? 0} />
        <Stat label="Frames" value={report.total_frames ?? 0} />
        <Stat label="FPS" value={report.fps ?? 0} />
      </dl>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="report-chart" src={devGameChartUrl(gameId, end)} alt={`Court analytics for ${END_LABEL[end]}`} loading="lazy" />
    </div>
  );
}

export default function DevGamePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [game, setGame] = useState<DevGame | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setGame(await getDevGame(id));
    } catch (err) {
      toast.error('Could not load game', { description: err instanceof Error ? err.message : undefined });
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const polling = game && (game.status === 'scheduled' || game.status === 'live' || game.analysis_status === 'running');
  useEffect(() => {
    if (!polling) return;
    const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t);
  }, [polling, load]);

  const run = async (fn: () => Promise<DevGame>, ok: string) => {
    setBusy(true);
    try {
      setGame(await fn());
      toast.success(ok);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="loader" style={{ padding: '60px 0' }}>
        <i></i>
        <i></i>
        <i></i>
      </div>
    );
  }
  if (!game) {
    return (
      <div className="empty-state">
        <h2>Game not found</h2>
        <Link href="/dev" className="btn btn-primary">All games</Link>
      </div>
    );
  }

  const pair = game.players.map((p) => p?.name ?? '?').join(' vs ');
  const camNames: Record<string, string> = {};
  ENDS.forEach((e) => {
    const c = game.ends[e].camera;
    if (c) camNames[c.id] = END_LABEL[e];
  });
  const reports = game.analysis?.cameras ?? {};

  return (
    <>
      <div className="admin-topbar dev-game-top">
        <div>
          <Link href="/dev" className="back-link">
            <svg className="icon" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><polyline points="15 18 9 12 15 6" /></svg>
            All games
          </Link>
          <h3>{pair}</h3>
          <p className="muted">
            {game.title ? `${game.title} · ` : ''}
            {game.court_mode} · {formatWhen(game.started_at || game.scheduled_at)}
            {game.match_id && <> · <code>{game.match_id}</code></>}
          </p>
        </div>
        <div className="dev-game-chips">
          {game.dev_mode && <span className="status-chip dev-mode-chip">Dev mode</span>}
          <span className={`status-chip status-${game.status}`}>{STATUS_LABEL[game.status]}</span>
        </div>
      </div>
      {game.next_game_id && (
        <p className="dev-next-link">
          This game continued as a next game. <Link href={`/dev/games/${game.next_game_id}`}>Open the next game</Link>
        </p>
      )}

      {(game.status === 'live' || game.status === 'scheduled') && <CalibrationStrip game={game} onChange={setGame} />}

      {game.status === 'live' && (
        <section className="panel rec-bar" aria-label="Recording">
          <div className="rec-bar-state">
            <span className={`status-chip rec-chip rec-${game.recording_state}`} aria-live="polite">
              {game.recording_state === 'recording' ? 'Recording' : game.recording_state === 'paused' ? 'Paused' : 'Not recording'}
            </span>
            <span className="muted">
              {game.dev_mode
                ? 'Dev mode: you control the recording. Pausing skips that stretch; resuming continues the same file.'
                : 'Recording started with the game. Pausing skips that stretch; resuming continues the same file.'}
            </span>
          </div>
          <div className="rec-bar-actions">
            {game.recording_state === 'off' && (
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => run(() => recordDevGame(game.id, 'start'), 'Recording started')}>
                Start recording
              </button>
            )}
            {game.recording_state === 'recording' && (
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => run(() => recordDevGame(game.id, 'pause'), 'Recording paused')}>
                Pause recording
              </button>
            )}
            {game.recording_state === 'paused' && (
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => run(() => recordDevGame(game.id, 'resume'), 'Recording resumed')}>
                Resume recording
              </button>
            )}
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              title="End this game (its recording is saved) and start a new one for the same players and cameras"
              onClick={async () => {
                if (!window.confirm(`End this game and start the next one for ${pair}? Phones keep their cameras on.`)) return;
                setBusy(true);
                try {
                  const next = await nextDevGame(game.id);
                  toast.success(next.status === 'live' ? 'Next game started' : 'Next game created', {
                    description: next.dev_mode ? 'Not recording yet: start it when ready.' : undefined,
                  });
                  router.replace(`/dev/games/${next.id}`);
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : 'Could not start the next game');
                } finally {
                  setBusy(false);
                }
              }}
            >
              Next game
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => window.confirm('End this game for both players?') && run(() => stopDevGame(game.id), 'Game ended')}
            >
              End game
            </button>
          </div>
        </section>
      )}

      {game.status === 'live' && (
        <div className="dev-live">
          <div className="dev-feeds">
            {ENDS.map((e) =>
              game.ends[e].camera ? (
                <CameraFeed key={e} cameraId={game.ends[e].camera!.id} label={END_LABEL[e]} who={game.ends[e].user?.name} />
              ) : null
            )}
          </div>
          <aside className="panel dev-court-panel">
            <div className="section-heading">
              <h3>Fused court</h3>
            </div>
            <LiveCourt cameraNames={camNames} />
          </aside>
        </div>
      )}

      {game.status === 'scheduled' && (
        <section className="panel">
          <div className="section-heading dev-start-head">
            <h3>Waiting to start</h3>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !game.start_blockers || game.start_blockers.length > 0}
              onClick={() =>
                window.confirm(`Start this game now for ${pair}? Both phones begin live analysis and recording.`) &&
                run(() => startDevGame(game.id), 'Game started')
              }
            >
              Start game
            </button>
          </div>
          {game.start_blockers && game.start_blockers.length > 0 ? (
            <ul className="dev-start-blockers" aria-label="Why the game can't start yet">
              {game.start_blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          ) : (
            <p className="dev-start-ready">Both players&apos; phones are online. You can start the game for them.</p>
          )}
          <dl className="stat-grid">
            {ENDS.map((e) => (
              <Stat
                key={e}
                label={END_LABEL[e]}
                value={
                  game.ends[e].user ? (
                    <span className={`dot-label ${game.ends[e].camera?.online ? 'on' : ''}`}>
                      <i aria-hidden="true" />
                      {game.ends[e].user!.name}
                    </span>
                  ) : (
                    'Open'
                  )
                }
              />
            ))}
          </dl>
          <p className="muted">
            Live feeds appear here once the game starts, either from the players&apos; phones or with Start game above.
            Calibrate both ends first: the game will not start while a calibration preview is running.
          </p>
        </section>
      )}

      {game.status === 'completed' && (
        <section className="dev-analysis">
          <div className="panel analysis-bar">
            <div>
              <h3>Recorded analysis</h3>
              <p className="muted">
                {game.recorded
                  ? `${game.recorded} camera recording${game.recorded > 1 ? 's' : ''} saved. Analysis runs the full pipeline on each end: detection, tracking, bounce judge and faults.`
                  : 'No recording was saved for this game, so it cannot be analysed.'}
              </p>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !game.recorded || game.analysis_status === 'running'}
              onClick={() => run(() => analyzeDevGame(game.id), 'Analysis started')}
            >
              {game.analysis_status === 'running' ? 'Analysing…' : game.analysis?.cameras ? 'Run full again' : 'Analyse full recording'}
            </button>
          </div>
          {game.analysis_status === 'failed' && <p className="form-error">{game.analysis?.error ?? 'Analysis failed.'}</p>}
          {game.recorded > 0 && <VideoTrimmer game={game} onGameChange={setGame} />}
          {game.analysis?.cameras && (
            <div className="report-grid">
              {ENDS.map((e) => (reports[e] ? <ReportCard key={e} gameId={game.id} end={e} report={reports[e]!} /> : null))}
            </div>
          )}
        </section>
      )}

      {game.status === 'cancelled' && <p className="muted">This game was cancelled.</p>}
    </>
  );
}
