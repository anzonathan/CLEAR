'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
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
    { path: '/app/pair', icon: 'plus', label: '' },
    { path: '/app/videos', icon: 'video', label: 'Videos' },
    { path: '/app/profile', icon: 'user', label: 'Profile' },
  ];

  return (
    <div className="app">
      <div className="app-main">{children}</div>
      <div className="tabbar">
        {tabs.map((tab) => (
          <Link
            key={tab.path}
            href={tab.path}
            className={pathname === tab.path ? 'active' : ''}
          >
            <svg className="icon" width="20" height="20" viewBox="0 0 24 24">
              {tab.icon === 'home' && <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10" />}
              {tab.icon === 'users' && <><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75" /></>}
              {tab.icon === 'plus' && <><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>}
              {tab.icon === 'video' && <><polygon points="23 7 16 12 23 17 23 7" /><rect x="1" y="5" width="15" height="14" rx="2" ry="2" /></>}
              {tab.icon === 'user' && <><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></>}
            </svg>
            {tab.label && <span>{tab.label}</span>}
          </Link>
        ))}
      </div>
    </div>
  );
}
