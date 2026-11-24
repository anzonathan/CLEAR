import type { WeekBucket } from '@/lib/game-stats';

const fmt = (d: Date) => d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });

/** Games played per week. One series, so no legend: the panel title names it. */
export default function ActivityChart({ weeks }: { weeks: WeekBucket[] }) {
  const max = Math.max(1, ...weeks.map((w) => w.count));
  const total = weeks.reduce((n, w) => n + w.count, 0);

  return (
    <div className="activity-chart">
      <div className="activity-plot" role="list" aria-label={`Games played per week, last ${weeks.length} weeks`}>
        {/* Recessive gridline at the max, labelled once */}
        <span className="activity-max" aria-hidden="true">{max}</span>
        {weeks.map((w) => {
          const label = `${w.current ? 'This week' : `Week of ${fmt(w.start)}`}: ${w.count} game${w.count === 1 ? '' : 's'}`;
          return (
            <div
              key={w.start.toISOString()}
              role="listitem"
              tabIndex={0}
              aria-label={label}
              className={`activity-col${w.current ? ' is-current' : ''}`}
            >
              <span className="activity-tip" aria-hidden="true">{label}</span>
              <i style={{ height: w.count ? `${(w.count / max) * 100}%` : 0 }} />
            </div>
          );
        })}
      </div>
      <div className="activity-axis" aria-hidden="true">
        <span>{fmt(weeks[0].start)}</span>
        <span>This week</span>
      </div>
      {total === 0 && <p className="muted activity-empty">No games played in the last {weeks.length} weeks.</p>}
    </div>
  );
}
