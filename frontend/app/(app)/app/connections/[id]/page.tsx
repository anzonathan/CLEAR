'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { getConnection, getGames, scheduleGame, ConnectionDetail, Game } from '@/lib/api';
import { toLocalInput } from '@/lib/game-format';
import GameRow from '@/components/GameRow';

function defaultStart() {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  d.setMinutes(0, 0, 0);
  return toLocalInput(d);
}

export default function ConnectionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [connection, setConnection] = useState<ConnectionDetail | null>(null);
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [when, setWhen] = useState(defaultStart);
  const [courtMode, setCourtMode] = useState<'singles' | 'doubles'>('singles');
  const [title, setTitle] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([getConnection(id), getGames({ connection: id })])
      .then(([conn, list]) => {
        setConnection(conn);
        setGames(list);
      })
      .catch((err) => toast.error('Could not load this connection', { description: err.message }))
      .finally(() => setLoading(false));
  }, [id]);

  const handleStartNow = async () => {
    setSaving(true);
    try {
      const game = await scheduleGame({ connection_id: id, scheduled_at: new Date().toISOString(), court_mode: courtMode });
      toast.success('Session created', { description: `Pick your end and start your camera. ${connection?.other_name ?? 'Your partner'} does the same.` });
      router.push(`/app/games/${game.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not start a session');
    } finally {
      setSaving(false);
    }
  };

  const handleSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const game = await scheduleGame({
        connection_id: id,
        scheduled_at: new Date(when).toISOString(),
        court_mode: courtMode,
        title: title.trim() || undefined,
      });
      toast.success('Game scheduled', { description: 'Next, pick which end your phone films.' });
      router.push(`/app/games/${game.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not schedule the game');
    } finally {
      setSaving(false);
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

  if (!connection) {
    return (
      <div className="screen-pad with-tabs">
        <div className="empty-state">
          <h2>Connection not found</h2>
          <Link href="/app/connections" className="btn btn-primary">Back to connections</Link>
        </div>
      </div>
    );
  }

  const upcoming = games.filter((g) => g.status === 'scheduled' || g.status === 'live');
  const past = games.filter((g) => g.status === 'completed');
  const name = connection.other_name || connection.other_email;

  return (
    <div className="screen-pad with-tabs connection-page">
      <div className="topbar">
        <Link href="/app/connections" className="icon-button" aria-label="Back to connections">
          <svg className="icon" width="18" height="18" viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6" /></svg>
        </Link>
        <h3>{name}</h3>
        <span style={{ width: 40 }} />
      </div>

      <div className="panel start-now">
        <div>
          <h3>Play now</h3>
          <p className="muted">Start a session with {name} right away. Recording begins when both phones are steady.</p>
        </div>
        <button type="button" className="btn btn-primary" disabled={saving} onClick={handleStartNow}>
          Start session now
        </button>
      </div>

      <div className="connection-layout">
        <form className="panel schedule-form" onSubmit={handleSchedule}>
          <div className="section-heading">
            <h3>Schedule for later</h3>
          </div>
          <p className="muted">You and {name} each film one end of the court with your phones.</p>

          <label className="field">
            DATE AND TIME
            <div className="input-shell">
              <input type="datetime-local" value={when} min={toLocalInput(new Date())} onChange={(e) => setWhen(e.target.value)} required />
            </div>
          </label>

          <div className="field">
            FORMAT
            <div className="segmented" role="radiogroup" aria-label="Format">
              {(['singles', 'doubles'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={courtMode === m}
                  className={courtMode === m ? 'active' : ''}
                  onClick={() => setCourtMode(m)}
                >
                  {m === 'singles' ? 'Singles' : 'Doubles'}
                </button>
              ))}
            </div>
          </div>

          <label className="field">
            NAME (OPTIONAL)
            <div className="input-shell">
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Saturday practice" maxLength={120} />
            </div>
          </label>

          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Scheduling…' : 'Schedule game'}
          </button>
        </form>

        <div className="connection-games">
          <div className="panel">
            <div className="section-heading">
              <h3>Upcoming</h3>
            </div>
            {upcoming.length === 0 ? (
              <p className="muted list-empty">Nothing scheduled with {name} yet.</p>
            ) : (
              upcoming.map((g) => (
                <GameRow key={g.id} href={`/app/games/${g.id}`} title={g.title || `vs ${name}`} subtitle={g.court_mode} when={g.scheduled_at} status={g.status} />
              ))
            )}
          </div>
          {past.length > 0 && (
            <div className="panel">
              <div className="section-heading">
                <h3>Played</h3>
              </div>
              {past.map((g) => (
                <GameRow key={g.id} href={`/app/games/${g.id}`} title={g.title || `vs ${name}`} subtitle={g.court_mode} when={g.scheduled_at} status={g.status} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
