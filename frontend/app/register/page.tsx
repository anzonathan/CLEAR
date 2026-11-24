'use client';

import { toast } from 'sonner';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { homeFor } from '@/lib/roles';
import Link from 'next/link';

export default function RegisterPage() {
  const router = useRouter();
  const { refetch } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showPassword2, setShowPassword2] = useState(false);
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

    if (password !== password2) {
      toast.error('Passwords do not match');
      return;
    }

    setLoading(true);

    try {
      const res = await fetch('/api/auth/registration/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        credentials: 'include',
        body: JSON.stringify({ name, email, password1: password, password2 }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: `Server error (${res.status})` }));
        const errorMsg = data.email?.[0] || data.password1?.[0] || data.non_field_errors?.[0] || data.detail || 'Registration failed';
        throw new Error(errorMsg);
      }

      // Load the new session into auth context first, else the target layout bounces to /login.
      const me = await refetch();
      toast.success('Account created');
      router.push(homeFor(me?.role));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const PasswordToggle = ({ show, onToggle }: { show: boolean; onToggle: () => void }) => (
    <button
      type="button"
      onClick={onToggle}
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
      {show ? (
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
  );

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
          <span className="eyebrow">GET STARTED</span>
          <h2 style={{ font: "600 30px/.98 'Oswald'", textTransform: 'uppercase', margin: '8px 0' }}>
            Create your<br />account
          </h2>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div className="field">
            <label>NAME</label>
            <div className="input-shell">
              <input
                type="text"
                placeholder="Your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
          </div>

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
                placeholder="Create password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                style={{ paddingRight: '40px' }}
              />
              <PasswordToggle show={showPassword} onToggle={() => setShowPassword(!showPassword)} />
            </div>
          </div>

          <div className="field">
            <label>CONFIRM PASSWORD</label>
            <div className="input-shell" style={{ position: 'relative' }}>
              <input
                type={showPassword2 ? 'text' : 'password'}
                placeholder="Confirm password"
                value={password2}
                onChange={(e) => setPassword2(e.target.value)}
                required
                style={{ paddingRight: '40px' }}
              />
              <PasswordToggle show={showPassword2} onToggle={() => setShowPassword2(!showPassword2)} />
            </div>
          </div>

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? 'Creating account...' : 'Create Account'}
          </button>
        </form>

        <p className="fine-print">
          Already have an account? <Link href="/login"><b>Sign in</b></Link>
        </p>
      </div>
    </div>
  );
}
