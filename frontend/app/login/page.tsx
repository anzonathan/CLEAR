'use client';

import { toast } from 'sonner';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import Link from 'next/link';

export default function LoginPage() {
  const router = useRouter();
  const { refetch } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [csrfToken, setCsrfToken] = useState('');

  useEffect(() => {
    // Fetch CSRF token on mount
    fetch('/api/auth/csrf/', { credentials: 'include' })
      .then(res => res.json())
      .then(data => setCsrfToken(data.csrfToken))
      .catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const res = await fetch('/api/auth/login/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        credentials: 'include',
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: `Server error (${res.status})` }));
        throw new Error(data.detail || data.non_field_errors?.[0] || 'Login failed');
      }

      await refetch(); // load the new session into auth context, else /app bounces to /login
      toast.success('Signed in');
      router.push('/app');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = '/api/auth/google/';
  };

  return (
    <div className="app auth-layout">
      <aside className="auth-art" aria-hidden="true">
        <div className="brand">
          <div className="brand-mark">
            <span></span>
          </div>
          CLEAR
        </div>
        <svg className="auth-court" viewBox="0 0 360 710" fill="none">
          <rect x="30" y="30" width="300" height="650" rx="2" />
          <line x1="67.5" y1="30" x2="67.5" y2="680" />
          <line x1="292.5" y1="30" x2="292.5" y2="680" />
          <line x1="67.5" y1="180" x2="292.5" y2="180" />
          <line x1="67.5" y1="530" x2="292.5" y2="530" />
          <line x1="180" y1="180" x2="180" y2="530" />
          <line x1="180" y1="30" x2="180" y2="42" />
          <line x1="180" y1="668" x2="180" y2="680" />
          <line className="auth-net" x1="14" y1="355" x2="346" y2="355" />
          <circle className="auth-ball" cx="241" cy="238" r="7" />
          <path className="auth-trail" d="M150 520 Q 168 380 241 238" />
        </svg>
        <div className="auth-tagline">
          <h1>Clay-court AI referee studio</h1>
          <p>Pair with a partner, record from both ends of the court and review every call.</p>
        </div>
      </aside>
      <div className="screen-pad auth-screen">
        <div className="brand">
          <div className="brand-mark">
            <span></span>
          </div>
          CLEAR
        </div>

        <div style={{ marginBottom: '5px' }}>
          <span className="eyebrow">WELCOME BACK</span>
          <h2 style={{ font: "600 30px/.98 'Oswald'", textTransform: 'uppercase', margin: '8px 0' }}>
            Sign in to<br />your account
          </h2>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div className="field">
            <label>EMAIL</label>
            <div className="input-shell">
              <input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="field">
            <label>PASSWORD</label>
            <div className="input-shell" style={{ position: 'relative' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                style={{ paddingRight: '40px' }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '10px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '4px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--muted)',
                }}
              >
                {showPassword ? (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div className="or">
          <span></span>
          OR
          <span></span>
        </div>

        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleGoogleLogin}
          style={{ gap: '8px' }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Continue with Google
        </button>

        <p className="fine-print">
          Don&apos;t have an account? <Link href="/register"><b>Sign up</b></Link>
        </p>
      </div>
    </div>
  );
}
