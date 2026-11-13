'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getConnections, Connection } from '@/lib/api';

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchConnections() {
      try {
        const data = await getConnections();
        setConnections(data);
      } catch (err) {
        console.error('Failed to fetch connections:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchConnections();
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
    <div className="screen-pad with-tabs">
      <div className="topbar">
        <h3>Connections</h3>
        <Link href="/app/pair" className="icon-button">
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
      ) : connections.length === 0 ? (
        <div className="empty-state">
          <svg className="icon" width="48" height="48" viewBox="0 0 24 24" style={{ color: 'var(--muted)' }}>
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
          <h2>No Connections</h2>
          <p className="muted">Pair with a partner to share videos and start live sessions.</p>
          <Link href="/app/pair" className="btn btn-primary">
            Create Pair Code
          </Link>
        </div>
      ) : (
        <div>
          {connections.map((conn) => (
            <Link
              key={conn.id}
              href={`/app/connections/${conn.id}`}
              className="connection-row"
            >
              <div className="avatar">
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
          ))}
        </div>
      )}
    </div>
  );
}
