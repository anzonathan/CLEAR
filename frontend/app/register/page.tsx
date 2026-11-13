'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== password2) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);

    try {
      const res = await fetch('/api/auth/registration/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ name, email, password1: password, password2 }),
      });

      if (!res.ok) {
        const data = await res.json();
        const errorMsg = data.email?.[0] || data.password1?.[0] || data.non_field_errors?.[0] || 'Registration failed';
        throw new Error(errorMsg);
      }

      router.push('/app');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
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
          {error && (
            <div style={{
              background: 'rgba(217,76,61,0.1)',
              borderLeft: '3px solid var(--error)',
              padding: '10px',
              fontSize: '11px',
              color: 'var(--error)'
            }}>
              {error}
            </div>
          )}

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
            <div className="input-shell">
              <input
                type="password"
                placeholder="Create password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
              />
            </div>
          </div>

          <div className="field">
            <label>CONFIRM PASSWORD</label>
            <div className="input-shell">
              <input
                type="password"
                placeholder="Confirm password"
                value={password2}
                onChange={(e) => setPassword2(e.target.value)}
                required
              />
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
