'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  acceptGame,
  cancelGame,
  declineGame,
  claimGameEnd,
  getGame,
  releaseGameEnd,
  startGame,
  stopGame,
  Game,
  GameEnd,
} from '@/lib/api';
import { END_LABEL, formatWhen, STATUS_LABEL } from '@/lib/game-format';
import CameraStreamer from '@/components/CameraStreamer';

const ENDS: GameEnd[] = ['end_a', 'end_b'];
// Both cameras must stay online this long before the game starts by itself.
const STEADY_MS = 3000;

export default function GamePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [game, setGame] = useState<Game | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const steadySinceRef = useRef<number | null>(null);
  const autoStartingRef = useRef(false);

  // The game this page shows. Follows a developer's "Next game" in place (same page, same
  // mounted camera), so the phone keeps streaming without the player tapping again.
  const [gameId, setGameId] = useState(id);
  useEffect(() => setGameId(id), [id]);

  const load = useCallback(async () => {
    try {
      let g = await getGame(gameId);
      if (g.status === 'completed' && g.next_game_id) {
        // Swap to the next game in this same update: rendering the finished game would
        // unmount the camera and stop it.
        g = await getGame(g.next_game_id);
        setGameId(g.id);
        window.history.replaceState(null, '', `/app/games/${g.id}`);
        toast.success('Next game started', { description: 'Keep your phone where it is: your camera stays on.' });
      }
      setGame(g);
    } catch (err) {
      toast.error('Could not load this game', { description: err instanceof Error ? err.message : undefined });
    } finally {
      setLoading(false);
    }
  }, [gameId]);

  useEffect(() => {
    load();
  }, [load]);

  const readyToStart =
    !!game &&
    game.status === 'scheduled' &&
    !!(game.ends.end_a.user && game.ends.end_b.user) &&
    !!(game.ends.end_a.camera?.online && game.ends.end_b.camera?.online) &&
    // Hold the auto-start while a developer is calibrating the cameras.
    !(game.ends.end_a.camera?.preview || game.ends.end_b.camera?.preview);

  // Partner readiness, invite answers and camera status change on the other phone: poll while
  // it matters, faster once both ends are claimed so the auto-start reacts quickly.
  useEffect(() => {
    if (!game || !['pending', 'scheduled', 'live'].includes(game.status)) return;
    const bothClaimed = !!(game.ends.end_a.user && game.ends.end_b.user);
    const t = window.setInterval(load, game.status === 'scheduled' && bothClaimed ? 1000 : 3000);
    return () => window.clearInterval(t);
  }, [game?.status, game?.ends.end_a.user?.id, game?.ends.end_b.user?.id, load]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-start once both cameras have been steady for STEADY_MS. Both phones may fire this;
  // the server treats the second start as a no-op.
  useEffect(() => {
    if (!readyToStart || !game?.my_end) {
      steadySinceRef.current = null;
      return;
    }
    const now = Date.now();
    if (steadySinceRef.current === null) steadySinceRef.current = now;
    if (now - steadySinceRef.current < STEADY_MS || autoStartingRef.current) return;
    autoStartingRef.current = true;
    startGame(game.id)
      .then((g) => {
        setGame(g);
        toast.success('Game started', {
          description: g.dev_mode ? 'Both cameras are live. A developer controls the recording.' : 'Both cameras are live and recording.',
        });
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : 'Could not start the game'))
      .finally(() => {
        autoStartingRef.current = false;
        steadySinceRef.current = null;
      });
  }, [readyToStart, game]);

  const run = async (fn: () => Promise<Game>, success?: string) => {
    setBusy(true);
    try {
      setGame(await fn());
      if (success) toast.success(success);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Something went wrong');
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
      <div className="screen-pad with-tabs">
        <div className="empty-state">
          <h2>Game not found</h2>
          <Link href="/app/games" className="btn btn-primary">All games</Link>
        </div>
      </div>
    );
  }

  const partnerName = game.partner?.name ?? 'your partner';
  // Ends can be picked while the invite is open, so both phones are ready once it is accepted.
  const editable = game.status === 'pending' || game.status === 'scheduled';
  const pending = game.status === 'pending';
  const proposerName = game.proposed_by?.name ?? partnerName;
  const bothClaimed = !!(game.ends.end_a.user && game.ends.end_b.user);
  const bothOnline = !!(game.ends.end_a.camera?.online && game.ends.end_b.camera?.online);
  const calibrating = !!(game.ends.end_a.camera?.preview || game.ends.end_b.camera?.preview);
  const done = game.analysis_status === 'done' ? game.analysis?.cameras : null;

  return (
    <div className="screen-pad with-tabs game-page">
      <div className="topbar">
        <Link href="/app/games" className="icon-button" aria-label="All games">
          <svg className="icon" width="18" height="18" viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6" /></svg>
        </Link>
        <h3>{game.title || `vs ${partnerName}`}</h3>
        <span style={{ width: 40 }} />
      </div>

      <div className="game-summary panel">
        <div>
          <span className="eyebrow">{game.court_mode.toUpperCase()} · WITH {partnerName.toUpperCase()}</span>
          <h2>{formatWhen(game.scheduled_at)}</h2>
        </div>
        <span className={`status-chip status-${game.status}`}>{STATUS_LABEL[game.status]}</span>
      </div>

      {pending && (
        <section className="panel game-invite" aria-labelledby="invite-h" aria-live="polite">
          <div className="section-heading">
            <h3 id="invite-h">{game.awaiting_me ? `${proposerName} invited you` : 'Invite sent'}</h3>
          </div>
          {game.awaiting_me ? (
            <>
              <p className="muted">
                {game.court_mode === 'doubles' ? 'Doubles' : 'Singles'} on {formatWhen(game.scheduled_at)}. The game can only
                start after you accept.
              </p>
              <div className="invite-actions">
                <button type="button" className="btn btn-primary" disabled={busy} onClick={() => run(() => acceptGame(game.id), 'Invite accepted')}>
                  Accept
                </button>
                <button
                  type="button"
                  className="btn btn-ghost danger"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(`Decline this game with ${proposerName}?`)) {
                      run(() => declineGame(game.id), 'Invite declined').then(() => router.push('/app/games'));
                    }
                  }}
                >
                  Decline
                </button>
              </div>
            </>
          ) : (
            <p className="muted">Waiting for {partnerName} to accept. You can pick your end meanwhile.</p>
          )}
        </section>
      )}

      <div className="game-layout">
        <section className="panel game-ends" aria-labelledby="ends-h">
          <div className="section-heading">
            <h3 id="ends-h">Court ends</h3>
          </div>
          <p className="muted">
            Each phone films one end, mounted high behind the baseline. Pick yours; {partnerName} takes the other.
          </p>
          <div className="end-cards">
            {ENDS.map((end) => {
              const slot = game.ends[end];
              const mine = game.my_end === end;
              const taken = !!slot.user && !mine;
              return (
                <div key={end} className={`end-card ${mine ? 'is-mine' : ''} ${taken ? 'is-taken' : ''}`}>
                  <div className="end-card-head">
                    <b>{END_LABEL[end]}</b>
                    {slot.camera && (
                      <span className={`dot-label ${slot.camera.online ? 'on' : ''}`}>
                        <i aria-hidden="true" />
                        {slot.camera.online ? 'Camera on' : 'Camera off'}
                      </span>
                    )}
                  </div>
                  <span className="end-card-who">{mine ? 'You' : slot.user ? slot.user.name : 'Open'}</span>
                  {editable && !slot.user && (
                    <button type="button" className="btn btn-primary" disabled={busy} onClick={() => run(() => claimGameEnd(game.id, end), `You film ${END_LABEL[end]}`)}>
                      {game.my_end ? 'Switch here' : 'Film this end'}
                    </button>
                  )}
                  {editable && mine && (
                    <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => run(() => releaseGameEnd(game.id), 'End released')}>
                      Release
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {game.my_camera?.token && (game.status === 'scheduled' || game.status === 'live') && (
          <section className="panel game-camera" aria-labelledby="cam-h">
            <div className="section-heading">
              <h3 id="cam-h">Your camera · {game.my_end ? END_LABEL[game.my_end] : ''}</h3>
            </div>
            <CameraStreamer cameraId={game.my_camera.id} token={game.my_camera.token} />
          </section>
        )}

        <section className="panel game-control" aria-labelledby="ctl-h">
          <div className="section-heading">
            <h3 id="ctl-h">{game.status === 'live' ? 'Game in progress' : game.status === 'completed' ? 'Result' : 'Start the game'}</h3>
          </div>

          {editable && (
            <>
              <ul className="checklist">
                <li className={pending ? '' : 'ok'}>{game.awaiting_me ? 'You accepted the invite' : `${partnerName} accepted the invite`}</li>
                <li className={game.my_end ? 'ok' : ''}>You picked an end</li>
                <li className={bothClaimed ? 'ok' : ''}>{partnerName} picked the other end</li>
                <li className={bothOnline ? 'ok' : ''}>Both cameras are on</li>
              </ul>
              <p className="muted" aria-live="polite">
                {pending
                  ? 'The game starts by itself once the invite is accepted and both cameras are on and steady.'
                  : calibrating
                  ? 'A referee is calibrating the cameras. The game starts once they finish.'
                  : bothOnline
                  ? 'Cameras are steady. Starting… your phone will chime when recording begins.'
                  : 'The game starts by itself once both cameras are on and steady. Your phone chimes when it begins.'}
              </p>
              {!game.awaiting_me && (
              <button
                type="button"
                className="btn btn-ghost danger"
                disabled={busy}
                onClick={() => {
                  const msg = pending && !game.awaiting_me ? 'Withdraw this invite?' : 'Cancel this game? Both camera slots are freed.';
                  if (window.confirm(msg)) {
                    run(() => cancelGame(game.id), 'Game cancelled').then(() => router.push('/app/games'));
                  }
                }}
              >
                {pending && !game.awaiting_me ? 'Withdraw invite' : 'Cancel game'}
              </button>
              )}
            </>
          )}

          {game.status === 'live' && (
            <>
              <p className="muted">
                {!game.dev_mode
                  ? 'Both cameras stream to the referee and the game is being recorded.'
                  : game.recording_state === 'recording'
                  ? 'Dev mode: both cameras stream and a developer is recording.'
                  : game.recording_state === 'paused'
                  ? 'Dev mode: recording is paused by the developer. Keep playing.'
                  : 'Dev mode: both cameras stream; recording starts when the developer starts it.'}
              </p>
              {game.dev_mode && (
                <span className={`status-chip rec-chip rec-${game.recording_state}`} aria-live="polite">
                  {game.recording_state === 'recording' ? 'Recording' : game.recording_state === 'paused' ? 'Paused' : 'Not recording'}
                </span>
              )}
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => run(() => stopGame(game.id), 'Game ended. Recording saved.')}>
                End game
              </button>
            </>
          )}

          {game.status === 'completed' &&
            (done ? (
              <div className="result-grid">
                {ENDS.map((end) => {
                  const r = done[end];
                  if (!r?.line_calling) return null;
                  return (
                    <div key={end} className="result-card">
                      <span className="eyebrow">{END_LABEL[end]}</span>
                      <dl>
                        <div><dt>In</dt><dd>{r.line_calling.in_calls}</dd></div>
                        <div><dt>Out</dt><dd>{r.line_calling.out_calls}</dd></div>
                        <div><dt>Top speed</dt><dd>{r.ball_tracking?.max_speed_kmh ?? 0}<small> km/h</small></dd></div>
                      </dl>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="muted">
                {game.analysis_status === 'running'
                  ? 'The referee is reviewing the recording.'
                  : 'Recorded. Line calls appear here once the recording has been analysed.'}
              </p>
            ))}

          {game.status === 'cancelled' && <p className="muted">This game was cancelled.</p>}
          {game.status === 'declined' && (
            <p className="muted">
              {game.proposed_by && game.proposed_by.id !== game.partner?.id
                ? `${partnerName} declined this invite.`
                : 'You declined this invite.'}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
