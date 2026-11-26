import Link from 'next/link';
import type { GameStatus } from '@/lib/api';
import { formatWhen, STATUS_LABEL } from '@/lib/game-format';

export default function GameRow({
  href,
  title,
  subtitle,
  when,
  status,
  awaitingMe = false,
}: {
  href: string;
  title: string;
  subtitle?: string;
  when: string;
  status: GameStatus;
  /** A pending game reads "Invite" for the player who must answer, "Sent" for the one who asked. */
  awaitingMe?: boolean;
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
      <span className={`status-chip status-${status}`}>{status === 'pending' && !awaitingMe ? 'Sent' : STATUS_LABEL[status]}</span>
    </Link>
  );
}
