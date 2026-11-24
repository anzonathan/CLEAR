'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { getGames, Game } from '@/lib/api';
import GameRow from '@/components/GameRow';

export default function GamesPage() {
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getGames()
      .then(setGames)
      .catch((err) => toast.error('Could not load games', { description: err.message }))
      .finally(() => setLoading(false));
  }, []);

  const upcoming = games
    .filter((g) => g.status === 'scheduled' || g.status === 'live')
    .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
  const past = games.filter((g) => g.status === 'completed');

  const row = (g: Game) => (
    <GameRow
      key={g.id}
      href={`/app/games/${g.id}`}
      title={g.title || `vs ${g.partner?.name ?? 'partner'}`}
      subtitle={g.title ? `vs ${g.partner?.name ?? 'partner'}` : g.court_mode}
      when={g.scheduled_at}
      status={g.status}
    />
  );

  return (
    <div className="screen-pad with-tabs games-page">
      <div className="topbar">
        <h3>Games</h3>
        <Link href="/app/connections" className="icon-button" aria-label="Schedule a game">
          <svg className="icon" width="18" height="18" viewBox="0 0 24 24">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </Link>
      </div>

      {loading ? (
        <div className="loader" style={{ padding: '40px 0' }}>
          <i></i>
          <i></i>
          <i></i>
        </div>
      ) : games.length === 0 ? (
        <div className="empty-state">
          <h2>No games yet</h2>
          <p className="muted">Open a connection to schedule a game with your partner.</p>
          <Link href="/app/connections" className="btn btn-primary">Choose a partner</Link>
        </div>
      ) : (
        <>
          <div className="panel">
            <div className="section-heading">
              <h3>Upcoming</h3>
            </div>
            {upcoming.length ? upcoming.map(row) : <p className="muted list-empty">No upcoming games.</p>}
          </div>
          {past.length > 0 && (
            <div className="panel">
              <div className="section-heading">
                <h3>Played</h3>
              </div>
              {past.map(row)}
            </div>
          )}
        </>
      )}
    </div>
  );
}
