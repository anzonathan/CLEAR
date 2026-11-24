'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';

function getInitials(name: string) {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login');
    }
  }, [user, loading, router]);

  if (loading) {
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

  if (!user) {
    return null;
  }

  const tabs = [
    { path: '/app', icon: 'home', label: 'Home' },
    { path: '/app/connections', icon: 'users', label: 'Connect' },
    { path: '/app/pair', icon: 'plus', label: 'Pair' },
    { path: '/app/videos', icon: 'video', label: 'Videos' },
    { path: '/app/profile', icon: 'user', label: 'Profile' },
  ];

  const isActive = (path: string) =>
    path === '/app' ? pathname === '/app' : pathname === path || pathname.startsWith(`${path}/`);

  const handleLogout = async () => {
    await logout();
    router.push('/login');
  };

  return (
    <div className="app app-shell">
      <nav className="tabbar" aria-label="Main">
        <Link href="/app" className="tabbar-brand brand">
          <div className="brand-mark">
            <span></span>
          </div>
          CLEAR
        </Link>

        <div className="tabbar-links">
          {tabs.map((tab) => (
            <Link
              key={tab.path}
              href={tab.path}
              className={`${isActive(tab.path) ? 'active' : ''} ${tab.icon === 'plus' ? 'tab-pair' : ''}`}
              aria-current={isActive(tab.path) ? 'page' : undefined}
              aria-label={tab.label}
            >
              <svg className="icon" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
                {tab.icon === 'home' && <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10" />}
                {tab.icon === 'users' && <><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75" /></>}
                {tab.icon === 'plus' && <><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>}
                {tab.icon === 'video' && <><polygon points="23 7 16 12 23 17 23 7" /><rect x="1" y="5" width="15" height="14" rx="2" ry="2" /></>}
                {tab.icon === 'user' && <><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></>}
              </svg>
              <span>{tab.label}</span>
            </Link>
          ))}
        </div>

        <div className="tabbar-user">
          {user.role === 'admin' && (
            <Link href="/admin" className="tabbar-admin">
              <svg className="icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
              </svg>
              Admin dashboard
            </Link>
          )}
          <div className="tabbar-account">
            <div className="avatar avatar-small">
              {user.image ? (
                <img src={user.image} alt="" style={{ width: '100%', height: '100%', borderRadius: '50%' }} />
              ) : (
                getInitials(user.name || 'U')
              )}
            </div>
            <div>
              <b>{user.name}</b>
              <span>{user.email}</span>
            </div>
            <button type="button" className="tabbar-signout" onClick={handleLogout} aria-label="Sign out" title="Sign out">
              <svg className="icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        </div>
      </nav>
      <main className="app-main">{children}</main>
    </div>
  );
}
