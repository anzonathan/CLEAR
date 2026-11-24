import type { AnalysisReport, Game } from './api';

/** Per-camera reports that finished analysis without an error. */
function reports(g: Game): AnalysisReport[] {
  if (g.analysis_status !== 'done' || !g.analysis?.cameras) return [];
  return Object.values(g.analysis.cameras).filter((r): r is AnalysisReport => !!r && !r.error);
}

/** Minutes between start and end of a played game, or null if not recorded. */
export function gameMinutes(g: Game): number | null {
  if (!g.started_at || !g.ended_at) return null;
  const ms = new Date(g.ended_at).getTime() - new Date(g.started_at).getTime();
  return ms > 0 ? Math.round(ms / 60000) : null;
}

export interface GameResult {
  inCalls: number;
  outCalls: number;
  topSpeed: number | null;
  strokes: number;
}

/** Combined line calls and ball speed across both ends. Null until analysed. */
export function gameResult(g: Game): GameResult | null {
  const rs = reports(g);
  if (!rs.length) return null;
  let inCalls = 0;
  let outCalls = 0;
  let strokes = 0;
  let topSpeed: number | null = null;
  for (const r of rs) {
    inCalls += r.line_calling?.in_calls ?? 0;
    outCalls += r.line_calling?.out_calls ?? 0;
    strokes += r.ball_tracking?.rally_strokes ?? 0;
    const s = r.ball_tracking?.max_speed_kmh;
    if (typeof s === 'number' && s > 0) topSpeed = Math.max(topSpeed ?? 0, s);
  }
  return { inCalls, outCalls, topSpeed, strokes };
}

export function formatDuration(minutes: number) {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

export interface PlayerStats {
  played: number;
  playedThisMonth: number;
  courtMinutes: number;
  avgMinutes: number | null;
  topSpeed: number | null;
  inRate: number | null;
  bounces: number;
  analysed: number;
}

export function playerStats(games: Game[], now = new Date()): PlayerStats {
  const played = games.filter((g) => g.status === 'completed');
  let courtMinutes = 0;
  let timed = 0;
  let topSpeed: number | null = null;
  let inCalls = 0;
  let outCalls = 0;
  let analysed = 0;

  for (const g of played) {
    const m = gameMinutes(g);
    if (m != null) {
      courtMinutes += m;
      timed += 1;
    }
    const r = gameResult(g);
    if (r) {
      analysed += 1;
      inCalls += r.inCalls;
      outCalls += r.outCalls;
      if (r.topSpeed != null) topSpeed = Math.max(topSpeed ?? 0, r.topSpeed);
    }
  }

  const playedThisMonth = played.filter((g) => {
    const d = new Date(g.started_at ?? g.scheduled_at);
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }).length;

  const bounces = inCalls + outCalls;
  return {
    played: played.length,
    playedThisMonth,
    courtMinutes,
    avgMinutes: timed ? Math.round(courtMinutes / timed) : null,
    topSpeed: topSpeed != null ? Math.round(topSpeed) : null,
    inRate: bounces ? Math.round((inCalls / bounces) * 100) : null,
    bounces,
    analysed,
  };
}

/** Monday 00:00 of the week containing d, in local time. */
function weekStart(d: Date) {
  const s = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  s.setDate(s.getDate() - ((s.getDay() + 6) % 7));
  return s;
}

export interface WeekBucket {
  start: Date;
  count: number;
  current: boolean;
}

/** Played games per week, oldest first, ending with the current week. */
export function weeklyActivity(games: Game[], weeks = 10, now = new Date()): WeekBucket[] {
  const thisWeek = weekStart(now);
  const buckets: WeekBucket[] = Array.from({ length: weeks }, (_, i) => {
    const start = new Date(thisWeek);
    start.setDate(start.getDate() - (weeks - 1 - i) * 7);
    return { start, count: 0, current: i === weeks - 1 };
  });
  const first = buckets[0].start.getTime();
  const WEEK = 7 * 24 * 3600 * 1000;
  for (const g of games) {
    if (g.status !== 'completed') continue;
    const t = weekStart(new Date(g.started_at ?? g.scheduled_at)).getTime();
    if (t < first) continue;
    const i = Math.round((t - first) / WEEK);
    if (i >= 0 && i < weeks) buckets[i].count += 1;
  }
  return buckets;
}

/** "in 2 days", "in 3h 20m", "in 12 min", "now". */
export function countdown(iso: string, now = new Date()) {
  const mins = Math.round((new Date(iso).getTime() - now.getTime()) / 60000);
  if (mins <= 0) return 'now';
  if (mins < 60) return `in ${mins} min`;
  if (mins < 24 * 60) return `in ${formatDuration(mins)}`;
  const days = Math.round(mins / (24 * 60));
  return `in ${days} day${days === 1 ? '' : 's'}`;
}
