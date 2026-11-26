'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { getDevGames, DevGame } from '@/lib/api';
import { formatWhen, STATUS_LABEL } from '@/lib/game-format';

const ANALYSIS_LABEL = { none: 'Not analysed', running: 'Analysing…', done: 'Analysed', failed: 'Analysis failed' };

function pairName(g: DevGame) {
  return g.players.map((p) => p?.name ?? '?').join(' vs ');
}

function GameTable({ games, empty }: { games: DevGame[]; empty: string }) {
  if (!games.length) return <p className="muted list-empty">{empty}</p>;
  return (
    <div className="dev-table" role="table">
      {games.map((g) => (
        <Link key={g.id} href={`/dev/games/${g.id}`} className="dev-row" role="row">
          <div role="cell">
            <b>{pairName(g)}</b>
            <span>{g.title || g.court_mode}</span>
          </div>
          <div role="cell" className="dev-when">{formatWhen(g.started_at || g.scheduled_at)}</div>
          <div role="cell" className="dev-cams">
            {(['end_a', 'end_b'] as const).map((e) => (
              <span key={e} className={`dot-label ${g.ends[e].camera?.online ? 'on' : ''}`} title={`${e === 'end_a' ? 'End A' : 'End B'}: ${g.ends[e].user?.name ?? 'open'}`}>
                <i aria-hidden="true" />
                {e === 'end_a' ? 'A' : 'B'}
              </span>
            ))}
          </div>
          <div role="cell">
            {g.status === 'completed' ? (
              <span className={`status-chip analysis-${g.analysis_status}`}>{ANALYSIS_LABEL[g.analysis_status]}</span>
            ) : g.status === 'scheduled' && g.start_blockers?.length === 0 ? (
              <span className="status-chip analysis-done" title="Both phones are online: open the game to start it">
                Ready to start
              </span>
            ) : (
              <span className={`status-chip status-${g.status}`}>{STATUS_LABEL[g.status]}</span>
            )}
          </div>
        </Link>
      ))}
    </div>
  );
}

export default function DevHome() {
  const [games, setGames] = useState<DevGame[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () =>
      getDevGames()
        .then(setGames)
        .catch((err) => toast.error('Could not load games', { description: err.message }))
        .finally(() => setLoading(false));
    load();
    const t = window.setInterval(load, 5000);
    return () => window.clearInterval(t);
  }, []);

  const live = games.filter((g) => g.status === 'live');
  const recorded = games.filter((g) => g.status === 'completed');
  const scheduled = games.filter((g) => g.status === 'scheduled' || g.status === 'pending').sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));

  return (
    <>
      <div className="admin-topbar">
        <div>
          <h3>Game analysis</h3>
          <p className="muted">Every paired game: watch it live or analyse the recording.</p>
        </div>
      </div>

      {loading ? (
        <div className="loader" style={{ padding: '40px 0' }}>
          <i></i>
          <i></i>
          <i></i>
        </div>
      ) : (
        <div className="dev-sections">
          <section className="panel">
            <div className="section-heading">
              <h3>Live now</h3>
              {live.length > 0 && <span className="status-chip status-live">{live.length}</span>}
            </div>
            <GameTable games={live} empty="No game is live." />
          </section>
          <section className="panel">
            <div className="section-heading">
              <h3>Recorded</h3>
            </div>
            <GameTable games={recorded} empty="No recorded games yet." />
          </section>
          <section className="panel">
            <div className="section-heading">
              <h3>Scheduled</h3>
            </div>
            <GameTable games={scheduled} empty="Nothing scheduled." />
          </section>
        </div>
      )}
    </>
  );
}
