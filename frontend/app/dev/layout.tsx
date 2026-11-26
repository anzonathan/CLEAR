'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth-context';
import { homeFor } from '@/lib/roles';

export default function DevLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!user) router.replace('/login');
    else if (user.role !== 'developer') router.replace(homeFor(user.role));
  }, [user, loading, router]);

  if (loading || !user || user.role !== 'developer') {
    return (
      <div className="app app-loading">
        <div className="loader">
          <i></i>
          <i></i>
          <i></i>
        </div>
      </div>
    );
  }

  const handleLogout = async () => {
    await logout();
    toast.success('Signed out');
    router.push('/login');
  };

  return (
    <div className="admin-container dev-container">
      <aside className="admin-sidebar">
        <Link href="/dev" className="brand" style={{ color: 'var(--surface)' }}>
          <div className="brand-mark">
            <span></span>
          </div>
          CLEAR
          <span className="dev-tag">DEV</span>
        </Link>

        <nav className="admin-nav" aria-label="Developer">
          <Link href="/dev" className={pathname === '/dev' || pathname.startsWith('/dev/games') ? 'active' : ''}>
            <svg className="icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <line x1="12" y1="4" x2="12" y2="20" />
              <line x1="3" y1="12" x2="21" y2="12" />
            </svg>
            Game analysis
          </Link>
          <Link href="/dev/data" className={pathname.startsWith('/dev/data') ? 'active' : ''}>
            <svg className="icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <ellipse cx="12" cy="5" rx="8" ry="3" />
              <path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5" />
              <path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
            </svg>
            Data prep
          </Link>
          <Link href="/dev/streaming" className={pathname.startsWith('/dev/streaming') ? 'active' : ''}>
            <svg className="icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 12.55a11 11 0 0 1 14.08 0" />
              <path d="M1.42 9a16 16 0 0 1 21.16 0" />
              <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
              <line x1="12" y1="20" x2="12.01" y2="20" />
            </svg>
            Streaming
          </Link>
          {/* Developers are players too. */}
          <Link href="/app">
            <svg className="icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            </svg>
            Player app
          </Link>
        </nav>

        <div className="dev-account">
          <div>
            <b>{user.name}</b>
            <span>{user.email}</span>
          </div>
          <button type="button" onClick={handleLogout} aria-label="Sign out" title="Sign out">
            <svg className="icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </div>
      </aside>
      <main className="admin-main">{children}</main>
    </div>
  );
}
