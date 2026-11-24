'use client';

import { toast } from 'sonner';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { getConnections, getActiveSessions, getGames, Connection, LiveSession, Game } from '@/lib/api';
import { END_LABEL, formatWhen } from '@/lib/game-format';
import {
  countdown,
  formatDuration,
  gameMinutes,
  gameResult,
  playerStats,
  weeklyActivity,
} from '@/lib/game-stats';
import GameRow from '@/components/GameRow';
import ActivityChart from '@/components/ActivityChart';

const getInitials = (name: string) =>
  name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

const gameTitle = (g: Game) => g.title || `vs ${g.partner?.name ?? 'partner'}`;

function Loader() {
  return (
    <div className="loader" style={{ padding: '20px 0' }}>
      <i></i>
      <i></i>
      <i></i>
    </div>
  );
}

/** The next scheduled game (or the one live now), with what's left to get ready. */
function NextGame({ game, now, hasConnections }: { game: Game | null; now: Date; hasConnections: boolean }) {
  if (!game) {
    return (
      <div className="panel home-next is-empty">
        <span className="eyebrow">NEXT GAME</span>
        <h2>Nothing on the calendar</h2>
        <p className="muted">
          {hasConnections
            ? 'Pick a partner and set a time. You each film one end with your phone.'
            : 'Pair with a partner first, then schedule a game together.'}
        </p>
        <Link href={hasConnections ? '/app/connections' : '/app/pair'} className="btn btn-primary">
          {hasConnections ? 'Schedule a game' : 'Find a partner'}
        </Link>
      </div>
    );
  }

  const live = game.status === 'live';
  const partner = game.partner?.name ?? 'your partner';
  const partnerEnd = game.my_end === 'end_a' ? 'end_b' : game.my_end === 'end_b' ? 'end_a' : null;
  const partnerClaimed = partnerEnd
    ? !!game.ends[partnerEnd].user
    : !!(game.ends.end_a.user || game.ends.end_b.user);

  return (
    <Link href={`/app/games/${game.id}`} className={`panel home-next${live ? ' is-live' : ''}`}>
      <div className="home-next-head">
        <span className="eyebrow">
          {live ? 'LIVE NOW' : 'NEXT GAME'} · {game.court_mode.toUpperCase()}
        </span>
        {live ? (
          <span className="status-chip status-live">Live</span>
        ) : (
          <span className="home-next-countdown">{countdown(game.scheduled_at, now)}</span>
        )}
      </div>
      <h2>{gameTitle(game)}</h2>
      <p className="home-next-when">
        {formatWhen(game.scheduled_at)}
        {game.title ? ` · with ${partner}` : ''}
      </p>
      <div className="home-next-ready">
        <span className={`dot-label${game.my_end ? ' on' : ''}`}>
          <i />
          {game.my_end ? `You film ${END_LABEL[game.my_end]}` : 'Choose your end'}
        </span>
        <span className={`dot-label${partnerClaimed ? ' on' : ''}`}>
          <i />
          {partnerClaimed ? `${partner} is ready` : `Waiting on ${partner}`}
        </span>
      </div>
      <span className="btn home-next-cta">
        {live ? 'Join game' : game.my_end ? 'Open game' : 'Pick your end'}
        <svg className="icon" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
          <line x1="5" y1="12" x2="19" y2="12" />
          <polyline points="12 5 19 12 12 19" />
        </svg>
      </span>
    </Link>
  );
}

function PastGameRow({ game }: { game: Game }) {
  const d = new Date(game.started_at ?? game.scheduled_at);
  const mins = gameMinutes(game);
  const result = gameResult(game);
  const meta = [
    game.title ? `vs ${game.partner?.name ?? 'partner'}` : game.court_mode,
    mins != null ? formatDuration(mins) : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <Link href={`/app/games/${game.id}`} className="connection-row game-row past-row">
      <div className="game-date" aria-hidden="true">
        <b>{d.getDate()}</b>
        <span>{d.toLocaleString(undefined, { month: 'short' })}</span>
      </div>
      <div>
        <b>{gameTitle(game)}</b>
        <span>{meta}</span>
      </div>
      {result ? (
        <div className="past-result">
          <b>
            {result.topSpeed != null ? (
              <>
                {Math.round(result.topSpeed)}
                <small> km/h</small>
              </>
            ) : (
              '—'
            )}
          </b>
          <span>
            {result.inCalls} in · {result.outCalls} out
          </span>
        </div>
      ) : game.analysis_status === 'running' ? (
        <span className="status-chip analysis-running">Reviewing</span>
      ) : game.analysis_status === 'failed' ? (
        <span className="status-chip analysis-failed">No result</span>
      ) : (
        <span className="status-chip analysis-none">Recorded</span>
      )}
    </Link>
  );
}

export default function HomePage() {
  const { user } = useAuth();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [activeSessions, setActiveSessions] = useState<LiveSession[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    async function fetchData() {
      try {
        const [conns, sessions, all] = await Promise.all([getConnections(), getActiveSessions(), getGames()]);
        setConnections(conns);
        setGames(all);
        setActiveSessions(sessions);
      } catch (err) {
        toast.error('Could not load data', { description: err instanceof Error ? err.message : undefined });
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  // Keep the countdown honest without refetching.
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  const { upcoming, past, stats, weeks, gamesWith } = useMemo(() => {
    const upcoming = games
      .filter((g) => g.status === 'scheduled' || g.status === 'live')
      .sort((a, b) => {
        if (a.status !== b.status) return a.status === 'live' ? -1 : 1;
        return a.scheduled_at.localeCompare(b.scheduled_at);
      });
    const past = games
      .filter((g) => g.status === 'completed')
      .sort((a, b) => (b.started_at ?? b.scheduled_at).localeCompare(a.started_at ?? a.scheduled_at));
    const gamesWith = new Map<string, number>();
    for (const g of games) {
      if (g.status === 'completed') gamesWith.set(g.connection, (gamesWith.get(g.connection) ?? 0) + 1);
    }
    return { upcoming, past, stats: playerStats(games), weeks: weeklyActivity(games), gamesWith };
  }, [games]);

  const next = upcoming[0] ?? null;
  const laterGames = upcoming.slice(1, 4);
  const firstName = (user?.name || 'Player').split(' ')[0];

  const heroLine = loading
    ? ' '
    : stats.played === 0
      ? 'Your first game is the hardest to schedule.'
      : `${stats.played} game${stats.played === 1 ? '' : 's'} played · ${connections.length} partner${connections.length === 1 ? '' : 's'}`;

  return (
    <div className="screen-pad with-tabs home-page">
      <div className="topbar">
        <h3>Dashboard</h3>
        <div className="icon-button">
          <svg className="icon" width="18" height="18" viewBox="0 0 24 24">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9 M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
        </div>
      </div>

      <div className="home-hero">
        <div>
          <span className="eyebrow" style={{ color: 'var(--accent)' }}>WELCOME BACK</span>
          <h2>{firstName}</h2>
          <p className="home-hero-line">{heroLine}</p>
        </div>
        <div className="avatar" style={{ width: 50, height: 50 }}>
          {user?.image ? (
            <img src={user.image} alt="" style={{ width: '100%', height: '100%', borderRadius: '50%' }} />
          ) : (
            getInitials(user?.name || 'U')
          )}
        </div>
      </div>

      <div className="home-col home-col-main">
        {activeSessions.length > 0 && (
          <div className="panel home-live">
            <div className="section-heading">
              <h3>Live Sessions</h3>
            </div>
            {activeSessions.map((session) => (
              <Link key={session.id} href={`/app/live/${session.id}`} className="connection-row">
                <div className="avatar avatar-small" style={{ background: 'var(--error)' }}>
                  <svg className="icon" width="14" height="14" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10" />
                  </svg>
                </div>
                <div>
                  <b>Live with {session.other_name}</b>
                  <span>Tap to join session</span>
                </div>
                <span className="status-chip status-live">Live</span>
              </Link>
            ))}
          </div>
        )}

        {loading ? (
          <div className="panel home-next is-empty">
            <Loader />
          </div>
        ) : (
          <NextGame game={next} now={now} hasConnections={connections.length > 0} />
        )}

        <div className="panel home-past">
          <div className="section-heading">
            <h3>Past games</h3>
            {past.length > 0 && <Link href="/app/games">View all</Link>}
          </div>
          {loading ? (
            <Loader />
          ) : past.length === 0 ? (
            <p className="muted list-empty">
              Games you finish land here, with line calls and ball speed once the referee has reviewed them.
            </p>
          ) : (
            past.slice(0, 5).map((g) => <PastGameRow key={g.id} game={g} />)
          )}
        </div>

        <div className="panel home-connections">
          <div className="section-heading">
            <h3>Partners</h3>
            <Link href="/app/connections">View all</Link>
          </div>

          {loading ? (
            <Loader />
          ) : connections.length === 0 ? (
            <div className="empty-state" style={{ padding: '30px 0' }}>
              <p className="muted">No partners yet. Pair with someone to get started.</p>
              <Link href="/app/pair" className="btn btn-primary">
                <svg className="icon" width="16" height="16" viewBox="0 0 24 24">
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                Create Pair Code
              </Link>
            </div>
          ) : (
            [...connections]
              .sort((a, b) => (gamesWith.get(b.id) ?? 0) - (gamesWith.get(a.id) ?? 0))
              .slice(0, 4)
              .map((conn) => {
                const n = gamesWith.get(conn.id) ?? 0;
                return (
                  <Link key={conn.id} href={`/app/connections/${conn.id}`} className="connection-row">
                    <div className="avatar avatar-small">
                      {conn.other_image ? (
                        <img src={conn.other_image} alt="" style={{ width: '100%', height: '100%', borderRadius: '50%' }} />
                      ) : (
                        getInitials(conn.other_name || 'U')
                      )}
                    </div>
                    <div>
                      <b>{conn.other_name}</b>
                      <span>{n ? `${n} game${n === 1 ? '' : 's'} together` : 'No games yet'}</span>
                    </div>
                    <svg className="icon" width="16" height="16" viewBox="0 0 24 24" style={{ color: 'var(--muted)' }}>
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </Link>
                );
              })
          )}
        </div>
      </div>

      <div className="home-col home-col-side">
        <div className="panel home-stats">
          <div className="section-heading">
            <h3>Your numbers</h3>
          </div>
          <dl className="home-stat-grid">
            <div>
              <dt>Played</dt>
              <dd>{loading ? '—' : stats.played}</dd>
              <small>{stats.playedThisMonth} this month</small>
            </div>
            <div>
              <dt>On court</dt>
              <dd>{stats.courtMinutes ? formatDuration(stats.courtMinutes) : '—'}</dd>
              <small>{stats.avgMinutes != null ? `${formatDuration(stats.avgMinutes)} a game` : 'No timed games'}</small>
            </div>
            <div>
              <dt>Top speed</dt>
              <dd>
                {stats.topSpeed ?? '—'}
                {stats.topSpeed != null && <small> km/h</small>}
              </dd>
              <small>Fastest ball tracked</small>
            </div>
            <div>
              <dt>Called in</dt>
              <dd>
                {stats.inRate ?? '—'}
                {stats.inRate != null && <small>%</small>}
              </dd>
              <small>{stats.bounces ? `of ${stats.bounces} bounces` : 'Awaiting analysis'}</small>
            </div>
          </dl>
        </div>

        <div className="panel home-activity">
          <div className="section-heading">
            <h3>Activity</h3>
            <span className="home-activity-sub">Games per week</span>
          </div>
          {loading ? <Loader /> : <ActivityChart weeks={weeks} />}
        </div>

        {laterGames.length > 0 && (
          <div className="panel home-games">
            <div className="section-heading">
              <h3>Coming up</h3>
              <Link href="/app/games">View all</Link>
            </div>
            {laterGames.map((g) => (
              <GameRow
                key={g.id}
                href={`/app/games/${g.id}`}
                title={gameTitle(g)}
                subtitle={g.court_mode}
                when={g.scheduled_at}
                status={g.status}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
