'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { getAdminStats, getAdminUsers, updateUserRole, deleteUser, AdminStats, AdminUser } from '@/lib/api';

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!authLoading && (!user || user.role !== 'admin')) {
      router.replace('/app');
    }
  }, [user, authLoading, router]);

  useEffect(() => {
    async function fetchData() {
      try {
        const [statsData, usersData] = await Promise.all([
          getAdminStats(),
          getAdminUsers(),
        ]);
        setStats(statsData);
        setUsers(usersData);
      } catch (err) {
        console.error('Failed to fetch admin data:', err);
      } finally {
        setLoading(false);
      }
    }
    if (user?.role === 'admin') {
      fetchData();
    }
  }, [user]);

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      await updateUserRole(userId, newRole);
      setUsers(users.map(u => u.id === userId ? { ...u, role: newRole as AdminUser['role'] } : u));
    } catch (err) {
      console.error('Failed to update role:', err);
    }
  };

  const handleDelete = async (userId: string) => {
    if (!confirm('Are you sure you want to delete this user?')) return;
    try {
      await deleteUser(userId);
      setUsers(users.filter(u => u.id !== userId));
    } catch (err) {
      console.error('Failed to delete user:', err);
    }
  };

  if (authLoading || !user || user.role !== 'admin') {
    return (
      <div className="admin-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="loader">
          <i></i>
          <i></i>
          <i></i>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-container">
      <aside className="admin-sidebar">
        <div className="brand" style={{ color: 'var(--surface)' }}>
          <div className="brand-mark">
            <span></span>
          </div>
          CLEAR
        </div>

        <nav className="admin-nav">
          <Link href="/admin" className="active">
            <svg className="icon" width="18" height="18" viewBox="0 0 24 24">
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
            Dashboard
          </Link>
          <Link href="/admin/users">
            <svg className="icon" width="18" height="18" viewBox="0 0 24 24">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
            Users
          </Link>
          <Link href="/admin/videos">
            <svg className="icon" width="18" height="18" viewBox="0 0 24 24">
              <polygon points="23 7 16 12 23 17 23 7" />
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
            </svg>
            Videos
          </Link>
        </nav>

        <div style={{ marginTop: 'auto', paddingTop: '20px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
          <Link href="/app" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#a9bbb5', fontSize: '11px' }}>
            <svg className="icon" width="16" height="16" viewBox="0 0 24 24">
              <polyline points="15 18 9 12 15 6" />
            </svg>
            Back to App
          </Link>
        </div>
      </aside>

      <main className="admin-main">
        <div className="admin-topbar">
          <div>
            <h3>Dashboard</h3>
            <p style={{ fontSize: '10px', color: 'var(--muted)', marginTop: '3px' }}>
              System overview and management
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
          <>
            <div className="metric-grid">
              <div className="metric-card">
                <div>
                  <span>TOTAL USERS</span>
                </div>
                <b>{stats?.totalUsers || 0}</b>
                <p>Registered accounts</p>
              </div>
              <div className="metric-card">
                <div>
                  <span>CONNECTIONS</span>
                </div>
                <b>{stats?.activeConnections || 0}</b>
                <p>Active pairs</p>
              </div>
              <div className="metric-card">
                <div>
                  <span>VIDEOS</span>
                </div>
                <b>{stats?.totalVideos || 0}</b>
                <p>Shared videos</p>
              </div>
              <div className="metric-card">
                <div>
                  <span>LIVE SESSIONS</span>
                </div>
                <b>{stats?.activeSessions || 0}</b>
                <p>Currently active</p>
              </div>
            </div>

            <div style={{ marginTop: '24px', background: 'white', border: '1px solid var(--border)', borderRadius: '14px', padding: '18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ font: "600 17px 'Oswald'", textTransform: 'uppercase' }}>Recent Users</h3>
              </div>

              <div style={{ fontSize: '11px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 1fr 1fr 80px', gap: '12px', padding: '8px 0', borderBottom: '1px solid var(--border)', color: 'var(--muted)', fontWeight: 700, letterSpacing: '0.05em' }}>
                  <span>NAME</span>
                  <span>EMAIL</span>
                  <span>ROLE</span>
                  <span>JOINED</span>
                  <span></span>
                </div>
                {users.slice(0, 10).map((u) => (
                  <div key={u.id} style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 1fr 1fr 80px', gap: '12px', padding: '12px 0', borderBottom: '1px solid var(--border)', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600 }}>{u.name}</span>
                    <span style={{ color: 'var(--muted)' }}>{u.email}</span>
                    <select
                      value={u.role}
                      onChange={(e) => handleRoleChange(u.id, e.target.value)}
                      disabled={u.id === user.id}
                      style={{
                        padding: '4px 8px',
                        borderRadius: '6px',
                        border: '1px solid var(--border)',
                        fontSize: '10px',
                        background: u.id === user.id ? 'var(--surface)' : 'white',
                      }}
                    >
                      <option value="user">User</option>
                      <option value="developer">Developer</option>
                      <option value="admin">Admin</option>
                    </select>
                    <span style={{ color: 'var(--muted)', fontSize: '10px' }}>
                      {new Date(u.created_at).toLocaleDateString()}
                    </span>
                    <button
                      onClick={() => handleDelete(u.id)}
                      disabled={u.id === user.id}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: u.id === user.id ? 'var(--muted)' : 'var(--error)',
                        cursor: u.id === user.id ? 'not-allowed' : 'pointer',
                        fontSize: '10px',
                      }}
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
