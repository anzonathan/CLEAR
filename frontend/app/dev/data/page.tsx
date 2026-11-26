'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  analyzeClips,
  createDatasetExport,
  datasetDownloadUrl,
  deleteDatasetExport,
  getDatasetDefaults,
  getDatasetExports,
  getDevGames,
  ClipRef,
  DatasetExport,
  DatasetOptions,
  DevGame,
  GameEnd,
} from '@/lib/api';
import { END_LABEL, formatWhen } from '@/lib/game-format';

const ENDS: GameEnd[] = ['end_a', 'end_b'];

interface ClipRow {
  key: string;
  ref: ClipRef;
  label: string;
  /** Seconds, or null for a whole recording (length unknown until export). */
  duration: number | null;
  analysed: boolean;
  failed: boolean;
  overlay: 'analysis' | 'live' | null;
}

const keyOf = (c: ClipRef) => `${c.game_id}|${c.end}|${c.segment_id ?? ''}`;

function clipsFor(g: DevGame): ClipRow[] {
  const rows: ClipRow[] = [];
  for (const end of ENDS) {
    const vids = g.videos?.[end];
    if (!vids?.raw) continue;
    const full = g.analysis?.cameras?.[end];
    const fullDone = !!full && !full.error;
    const ref = { game_id: g.id, end, segment_id: null };
    rows.push({
      key: keyOf(ref),
      ref,
      label: `${END_LABEL[end]} · full recording`,
      duration: null,
      analysed: fullDone,
      failed: !!full?.error,
      overlay: fullDone ? 'analysis' : vids.annotated ? 'live' : null,
    });
    for (const s of g.segments.filter((x) => x.end === end)) {
      const rep = g.analysis?.segments?.[s.id];
      const segRef = { game_id: g.id, end, segment_id: s.id };
      rows.push({
        key: keyOf(segRef),
        ref: segRef,
        label: `${END_LABEL[end]} · ${s.label}`,
        duration: s.end_s - s.start_s,
        analysed: !!rep && !rep.error,
        failed: !!rep?.error,
        overlay: (rep && !rep.error) || fullDone ? 'analysis' : vids.annotated ? 'live' : null,
      });
    }
  }
  return rows;
}

function fmtDur(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m ? `${m}m ${String(sec).padStart(2, '0')}s` : `${sec}s`;
}

function fmtBytes(n: number) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1e3))} KB`;
}

const pairName = (g: DevGame) => g.players.map((p) => p?.name ?? '?').join(' vs ');

export default function DataPrepPage() {
  const [games, setGames] = useState<DevGame[]>([]);
  const [exports, setExports] = useState<DatasetExport[]>([]);
  const [options, setOptions] = useState<DatasetOptions | null>(null);
  const [classes, setClasses] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const [segmentsOnly, setSegmentsOnly] = useState(false);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const loadGames = useCallback(
    () =>
      getDevGames('completed')
        .then(setGames)
        .catch((err) => toast.error('Could not load recordings', { description: err.message })),
    []
  );
  const loadExports = useCallback(
    () => getDatasetExports().then(setExports).catch(() => undefined),
    []
  );

  useEffect(() => {
    Promise.all([
      loadGames(),
      loadExports(),
      getDatasetDefaults()
        .then((d) => {
          setOptions(d.options);
          setClasses(d.classes);
        })
        .catch((err) => toast.error('Could not load export settings', { description: err.message })),
    ]).finally(() => setLoading(false));
  }, [loadGames, loadExports]);

  // Poll while an export builds or a game is being analysed.
  const exporting = exports.some((e) => e.status === 'queued' || e.status === 'running');
  const analysing = games.some((g) => g.analysis_status === 'running');
  useEffect(() => {
    if (!exporting && !analysing) return;
    const t = window.setInterval(() => {
      if (exporting) loadExports();
      if (analysing) loadGames();
    }, 3000);
    return () => window.clearInterval(t);
  }, [exporting, analysing, loadExports, loadGames]);

  const library = useMemo(() => {
    const q = query.trim().toLowerCase();
    return games
      .map((g) => ({ game: g, clips: clipsFor(g).filter((c) => !segmentsOnly || c.ref.segment_id) }))
      .filter(({ game, clips }) => clips.length > 0 && (!q || `${pairName(game)} ${game.title} ${game.id}`.toLowerCase().includes(q)))
      .sort((a, b) => (b.game.started_at ?? '').localeCompare(a.game.started_at ?? ''));
  }, [games, query, segmentsOnly]);

  const allRows = useMemo(() => new Map(games.flatMap(clipsFor).map((c) => [c.key, c])), [games]);
  const chosen = Array.from(selected).map((k) => allRows.get(k)).filter((c): c is ClipRow => !!c);
  const refs = chosen.map((c) => c.ref);
  const segSeconds = chosen.reduce((s, c) => s + (c.duration ?? 0), 0);
  const fullCount = chosen.filter((c) => c.duration === null).length;
  const estFrames = options ? Math.round(segSeconds * options.frames_fps) : 0;

  const toggle = (keys: string[], on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      keys.forEach((k) => (on ? next.add(k) : next.delete(k)));
      return next;
    });

  const handleAnalyse = async () => {
    setBusy(true);
    try {
      const res = await analyzeClips(refs);
      const errs = Object.entries(res.errors);
      if (res.started.length) toast.success(`Analysing ${res.started.length} game(s)`, { description: 'Each game runs in the background.' });
      errs.forEach(([gid, msg]) => toast.error(`${games.find((g) => g.id === gid)?.title || gid}: ${msg}`));
      await loadGames();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not start analysis');
    } finally {
      setBusy(false);
    }
  };

  const handleExport = async () => {
    if (!options) return;
    setBusy(true);
    try {
      await createDatasetExport(refs, options, name.trim() || undefined);
      toast.success('Export started', { description: 'It builds in the background. Download it below when it is done.' });
      setName('');
      await loadExports();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not start the export');
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (e: DatasetExport) => {
    if (!window.confirm(`Delete "${e.name}" and its ZIP from the server?`)) return;
    try {
      await deleteDatasetExport(e.id);
      setExports((xs) => xs.filter((x) => x.id !== e.id));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not delete the export');
    }
  };

  const setOpt = (patch: Partial<DatasetOptions>) => setOptions((o) => (o ? { ...o, ...patch } : o));
  const nothingToExport = !options || (!options.raw && !options.overlay && options.frames_fps === 0 && !options.analysis);

  return (
    <>
      <div className="admin-topbar">
        <div>
          <h3>Data prep</h3>
          <p className="muted">
            Pick recordings and trimmed segments, analyse them, and export raw and overlay clips, frames and pre-labels
            for Roboflow.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="loader" style={{ padding: '40px 0' }}>
          <i></i>
          <i></i>
          <i></i>
        </div>
      ) : (
        <div className="dp-layout">
          <section className="panel dp-library" aria-labelledby="lib-h">
            <div className="section-heading">
              <h3 id="lib-h">Recordings</h3>
              {selected.size > 0 && (
                <button type="button" className="btn btn-ghost dp-small" onClick={() => setSelected(new Set())}>
                  Clear selection
                </button>
              )}
            </div>
            <div className="dp-filters">
              <label className="input-shell dp-search">
                <span className="sr-only">Search games</span>
                <input type="search" placeholder="Search players, title or game id" value={query} onChange={(e) => setQuery(e.target.value)} />
              </label>
              <label className="dp-check">
                <input type="checkbox" checked={segmentsOnly} onChange={(e) => setSegmentsOnly(e.target.checked)} />
                Trimmed segments only
              </label>
            </div>

            {library.length === 0 ? (
              <p className="muted list-empty">
                {games.length ? 'Nothing matches the filter.' : 'No recorded games yet. Finished games with a recording show up here.'}
              </p>
            ) : (
              library.map(({ game, clips }) => {
                const keys = clips.map((c) => c.key);
                const n = keys.filter((k) => selected.has(k)).length;
                return (
                  <div key={game.id} className="dp-game">
                    <div className="dp-game-head">
                      <label className="dp-check">
                        <input
                          type="checkbox"
                          checked={n === keys.length}
                          ref={(el) => {
                            if (el) el.indeterminate = n > 0 && n < keys.length;
                          }}
                          onChange={(e) => toggle(keys, e.target.checked)}
                          aria-label={`Select all clips of ${pairName(game)}`}
                        />
                        <span>
                          <b>{game.title || pairName(game)}</b>
                          <span className="muted">
                            {game.title ? `${pairName(game)} · ` : ''}
                            {formatWhen(game.started_at || game.scheduled_at)} · {game.court_mode}
                            {game.dev_mode ? ' · dev' : ''}
                          </span>
                        </span>
                      </label>
                      {game.analysis_status === 'running' && <span className="status-chip analysis-running">Analysing…</span>}
                      <Link href={`/dev/games/${game.id}`} className="btn btn-ghost dp-small">
                        Trim
                      </Link>
                    </div>
                    <ul className="dp-clips">
                      {clips.map((c) => (
                        <li key={c.key}>
                          <label className="dp-check">
                            <input type="checkbox" checked={selected.has(c.key)} onChange={(e) => toggle([c.key], e.target.checked)} />
                            <span className="dp-clip-label">{c.label}</span>
                          </label>
                          <span className="dp-clip-meta">{c.duration === null ? 'Full' : fmtDur(c.duration)}</span>
                          <span className="dp-tags">
                            <span className={`status-chip ${c.analysed ? 'analysis-done' : c.failed ? 'analysis-failed' : 'analysis-none'}`}>
                              {c.analysed ? 'Analysed' : c.failed ? 'Failed' : 'Not analysed'}
                            </span>
                            <span className="status-chip analysis-none" title="Which overlay the export will include">
                              {c.overlay === 'analysis' ? 'Overlay: pipeline' : c.overlay === 'live' ? 'Overlay: live' : 'No overlay'}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })
            )}
          </section>

          <div className="dp-side">
            <section className="panel dp-actions" aria-labelledby="sel-h">
              <div className="section-heading">
                <h3 id="sel-h">{selected.size ? `${selected.size} clip${selected.size === 1 ? '' : 's'} selected` : 'Nothing selected'}</h3>
              </div>
              <p className="muted">
                {selected.size
                  ? `${segSeconds ? fmtDur(segSeconds) + ' of segments' : 'No segments'}${fullCount ? ` + ${fullCount} full recording${fullCount === 1 ? '' : 's'}` : ''}.`
                  : 'Tick clips in the list. Trim new segments on a game page.'}
              </p>
              <button type="button" className="btn btn-ghost" disabled={busy || !selected.size} onClick={handleAnalyse}>
                Analyse selected
              </button>
              <p className="muted dp-note">Analysis adds the pipeline overlay, tracks and line calls to the export. Not required for labelling.</p>
            </section>

            {options && (
              <section className="panel dp-options" aria-labelledby="exp-h">
                <div className="section-heading">
                  <h3 id="exp-h">Export</h3>
                </div>
                <label className="dp-check">
                  <input type="checkbox" checked={options.raw} onChange={(e) => setOpt({ raw: e.target.checked })} />
                  Raw clips (H.264)
                </label>
                <label className="dp-check">
                  <input type="checkbox" checked={options.overlay} onChange={(e) => setOpt({ overlay: e.target.checked })} />
                  Overlay clips
                </label>
                <label className="dp-check">
                  <input type="checkbox" checked={options.analysis} onChange={(e) => setOpt({ analysis: e.target.checked })} />
                  Analysis data (tracks, bounces, faults)
                </label>
                <label className="field">
                  FRAMES FOR LABELLING (PER SECOND)
                  <div className="input-shell">
                    <input
                      type="number"
                      min={0}
                      max={30}
                      step={0.5}
                      value={options.frames_fps}
                      onChange={(e) => {
                        const v = Math.min(30, Math.max(0, Number(e.target.value) || 0));
                        setOpt({ frames_fps: v, prelabels: v === 0 ? false : options.prelabels });
                      }}
                    />
                  </div>
                </label>
                <label className={`dp-check ${options.frames_fps === 0 ? 'dp-disabled' : ''}`}>
                  <input
                    type="checkbox"
                    checked={options.prelabels}
                    disabled={options.frames_fps === 0}
                    onChange={(e) => setOpt({ prelabels: e.target.checked })}
                  />
                  YOLO pre-labels ({classes.join(', ')})
                </label>
                <p className="muted dp-note">
                  {options.frames_fps > 0
                    ? `≈${estFrames.toLocaleString()} frames from segments${fullCount ? ', plus full recordings' : ''}. Pre-labels come from the stock detector: check them in Roboflow.`
                    : 'No frames: the export holds clips and data only.'}
                </p>
                <label className="field">
                  NAME (OPTIONAL)
                  <div className="input-shell">
                    <input value={name} maxLength={120} placeholder="e.g. Ball labelling batch 1" onChange={(e) => setName(e.target.value)} />
                  </div>
                </label>
                <button type="button" className="btn btn-primary" disabled={busy || !selected.size || nothingToExport} onClick={handleExport}>
                  Export {selected.size || ''} clip{selected.size === 1 ? '' : 's'}
                </button>
              </section>
            )}

            <section className="panel dp-exports" aria-labelledby="hist-h">
              <div className="section-heading">
                <h3 id="hist-h">Exports</h3>
              </div>
              {exports.length === 0 ? (
                <p className="muted list-empty">No exports yet.</p>
              ) : (
                <ul className="dp-export-list" aria-live="polite">
                  {exports.map((e) => (
                    <li key={e.id}>
                      <div className="dp-export-top">
                        <b>{e.name}</b>
                        <span
                          className={`status-chip ${
                            e.status === 'done' ? 'analysis-done' : e.status === 'failed' ? 'analysis-failed' : 'analysis-running'
                          }`}
                        >
                          {e.status === 'queued' ? 'Queued' : e.status === 'running' ? 'Building…' : e.status === 'done' ? 'Ready' : 'Failed'}
                        </span>
                      </div>
                      <span className="muted">
                        {formatWhen(e.created_at)}
                        {e.created_by ? ` · ${e.created_by}` : ''}
                      </span>
                      {e.status === 'running' && e.progress && <span className="dp-progress">{e.progress}</span>}
                      {e.status === 'failed' && <span className="dp-error">{e.error}</span>}
                      {e.result && (
                        <span className="muted">
                          {e.result.clips} clips · {e.result.frames.toLocaleString()} frames
                          {e.result.labelled_frames ? ` (${e.result.labelled_frames.toLocaleString()} pre-labelled)` : ''} ·{' '}
                          {fmtBytes(e.result.size_bytes)}
                          {e.result.failed_clips ? ` · ${e.result.failed_clips} clip(s) failed, see manifest.json` : ''}
                        </span>
                      )}
                      <div className="dp-export-actions">
                        {e.status === 'done' && (
                          <a className="btn btn-primary dp-small" href={datasetDownloadUrl(e.id)} download>
                            Download ZIP
                          </a>
                        )}
                        {(e.status === 'done' || e.status === 'failed') && (
                          <button type="button" className="btn btn-ghost danger dp-small" onClick={() => handleDelete(e)}>
                            Delete
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      )}
    </>
  );
}
