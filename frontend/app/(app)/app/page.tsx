'use client';

import { toast } from 'sonner';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { getConnections, getActiveSessions, getGames, Connection, LiveSession, Game } from '@/lib/api';
import GameRow from '@/components/GameRow';

export default function HomePage() {
  const { user } = useAuth();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [activeSessions, setActiveSessions] = useState<LiveSession[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [conns, sessions, upcoming] = await Promise.all([
          getConnections(),
          getActiveSessions(),
          getGames({ upcoming: true }),
        ]);
        setConnections(conns);
        setGames(upcoming);
        setActiveSessions(sessions);
      } catch (err) {
        toast.error('Could not load data', { description: err instanceof Error ? err.message : undefined });
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const getInitials = (name: string) => {
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

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
          <h2>{user?.name || 'Player'}</h2>
        </div>
        <div className="avatar" style={{ width: 50, height: 50 }}>
          {user?.image ? (
            <img src={user.image} alt="" style={{ width: '100%', height: '100%', borderRadius: '50%' }} />
          ) : (
            getInitials(user?.name || 'U')
          )}
        </div>
      </div>

      {activeSessions.length > 0 && (
        <div className="panel home-live">
          <div className="section-heading">
            <h3>Live Sessions</h3>
          </div>
          {activeSessions.map((session) => (
            <Link
              key={session.id}
              href={`/app/live/${session.id}`}
              className="connection-row"
            >
              <div className="avatar avatar-small" style={{ background: 'var(--error)' }}>
                <svg className="icon" width="14" height="14" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" />
                </svg>
              </div>
              <div>
                <b>Live with {session.other_name}</b>
                <span>Tap to join session</span>
              </div>
              <div style={{ color: 'var(--error)', fontSize: '8px', fontWeight: 700 }}>LIVE</div>
            </Link>
          ))}
        </div>
      )}

      {games.length > 0 && (
        <div className="panel home-games">
          <div className="section-heading">
            <h3>{games.some((g) => g.awaiting_me) ? 'Invites and upcoming games' : 'Upcoming games'}</h3>
            <Link href="/app/games">View all</Link>
          </div>
          {[...games.filter((g) => g.awaiting_me), ...games.filter((g) => !g.awaiting_me)].slice(0, 3).map((g) => (
            <GameRow
              key={g.id}
              href={`/app/games/${g.id}`}
              title={g.title || `vs ${g.partner?.name ?? 'partner'}`}
              subtitle={g.court_mode}
              when={g.scheduled_at}
              status={g.status}
              awaitingMe={g.awaiting_me}
            />
          ))}
        </div>
      )}

      <div className="panel home-connections">
        <div className="section-heading">
          <h3>Connections</h3>
          <Link href="/app/connections">View all</Link>
        </div>

        {loading ? (
          <div className="loader" style={{ padding: '20px 0' }}>
            <i></i>
            <i></i>
            <i></i>
          </div>
        ) : connections.length === 0 ? (
          <div className="empty-state" style={{ padding: '30px 0' }}>
            <p className="muted">No connections yet. Pair with a partner to get started.</p>
            <Link href="/app/pair" className="btn btn-primary">
              <svg className="icon" width="16" height="16" viewBox="0 0 24 24">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Create Pair Code
            </Link>
          </div>
        ) : (
          connections.slice(0, 3).map((conn) => (
            <Link
              key={conn.id}
              href={`/app/connections/${conn.id}`}
              className="connection-row"
            >
              <div className="avatar avatar-small">
                {conn.other_image ? (
                  <img src={conn.other_image} alt="" style={{ width: '100%', height: '100%', borderRadius: '50%' }} />
                ) : (
                  getInitials(conn.other_name || 'U')
                )}
              </div>
              <div>
                <b>{conn.other_name}</b>
                <span>{conn.other_email}</span>
              </div>
              <svg className="icon" width="16" height="16" viewBox="0 0 24 24" style={{ color: 'var(--muted)' }}>
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </Link>
          ))
        )}
      </div>

    </div>
  );
}
