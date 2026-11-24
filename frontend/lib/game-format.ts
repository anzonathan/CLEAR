import type { GameEnd, GameStatus } from './api';

export const END_LABEL: Record<GameEnd, string> = { end_a: 'End A', end_b: 'End B' };

export const STATUS_LABEL: Record<GameStatus, string> = {
  scheduled: 'Scheduled',
  live: 'Live',
  completed: 'Played',
  cancelled: 'Cancelled',
};

export function formatWhen(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Value for <input type="datetime-local"> in the viewer's own timezone. */
export function toLocalInput(d: Date) {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
