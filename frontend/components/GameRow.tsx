import Link from 'next/link';
import type { GameStatus } from '@/lib/api';
import { formatWhen, STATUS_LABEL } from '@/lib/game-format';

export default function GameRow({
  href,
  title,
  subtitle,
  when,
  status,
}: {
  href: string;
  title: string;
  subtitle?: string;
  when: string;
  status: GameStatus;
}) {
  const d = new Date(when);
  return (
    <Link href={href} className="connection-row game-row">
      <div className="game-date" aria-hidden="true">
        <b>{d.getDate()}</b>
        <span>{d.toLocaleString(undefined, { month: 'short' })}</span>
      </div>
      <div>
        <b>{title}</b>
        <span>{subtitle ? `${subtitle} · ` : ''}{formatWhen(when)}</span>
      </div>
      <span className={`status-chip status-${status}`}>{STATUS_LABEL[status]}</span>
    </Link>
  );
}
