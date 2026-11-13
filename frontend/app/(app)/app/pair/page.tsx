'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { generatePairCode, joinPairCode } from '@/lib/api';

export default function PairPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'generate' | 'join'>('generate');
  const [code, setCode] = useState('');
  const [generatedCode, setGeneratedCode] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await generatePairCode();
      setGeneratedCode(data.code);
      setExpiresAt(data.expires_at);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate code');
    } finally {
      setLoading(false);
    }
  };

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = await joinPairCode(code);
      router.push(`/app/connections/${data.connectionId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to join');
    } finally {
      setLoading(false);
    }
  };

  const copyCode = async () => {
    await navigator.clipboard.writeText(generatedCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatExpiry = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = Math.max(0, Math.floor((date.getTime() - now.getTime()) / 1000 / 60));
    return `Expires in ${diff} minutes`;
  };

  return (
    <div className="screen-pad with-tabs">
      <div className="topbar">
        <button className="back-circle" onClick={() => router.back()}>
          <svg className="icon" width="18" height="18" viewBox="0 0 24 24">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <h3>Pair</h3>
        <div style={{ width: 36 }}></div>
      </div>

      <div className="pair-hero">
        <div className="pair-icon">
          <svg className="icon" width="32" height="32" viewBox="0 0 24 24">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
        </div>
        <h2>Connect with Partner</h2>
        <p className="muted">Share a code or enter one to connect</p>
      </div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <button
          className={`btn ${mode === 'generate' ? 'btn-primary' : 'btn-secondary'}`}
          style={{ flex: 1 }}
          onClick={() => setMode('generate')}
        >
          Generate Code
        </button>
        <button
          className={`btn ${mode === 'join' ? 'btn-primary' : 'btn-secondary'}`}
          style={{ flex: 1 }}
          onClick={() => setMode('join')}
        >
          Enter Code
        </button>
      </div>

      {error && (
        <div style={{
          background: 'rgba(217,76,61,0.1)',
          borderLeft: '3px solid var(--error)',
          padding: '10px',
          fontSize: '11px',
          color: 'var(--error)',
          marginBottom: '12px'
        }}>
          {error}
        </div>
      )}

      {mode === 'generate' ? (
        <div className="pair-generate">
          {generatedCode ? (
            <div className="code-display">
              <div className="code-value">{generatedCode}</div>
              <button className="code-copy" onClick={copyCode}>
                <svg className="icon" width="14" height="14" viewBox="0 0 24 24">
                  {copied ? (
                    <polyline points="20 6 9 17 4 12" />
                  ) : (
                    <>
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </>
                  )}
                </svg>
                {copied ? 'Copied!' : 'Copy Code'}
              </button>
              <span className="code-expiry">{formatExpiry(expiresAt)}</span>
            </div>
          ) : (
            <button
              className="btn btn-primary"
              onClick={handleGenerate}
              disabled={loading}
              style={{ width: '100%' }}
            >
              {loading ? 'Generating...' : 'Generate Pair Code'}
            </button>
          )}

          <div className="pair-info">
            <svg className="icon" width="16" height="16" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            Share this code with your partner. They can enter it to connect with you.
          </div>
        </div>
      ) : (
        <form className="pair-join" onSubmit={handleJoin}>
          <div className="field">
            <label>PAIR CODE</label>
            <div className="input-shell">
              <input
                type="text"
                placeholder="Enter 6-character code"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                maxLength={6}
                style={{ textAlign: 'center', letterSpacing: '0.2em', fontWeight: 600 }}
              />
            </div>
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || code.length !== 6}
            style={{ width: '100%' }}
          >
            {loading ? 'Connecting...' : 'Connect'}
          </button>

          <div className="pair-info">
            <svg className="icon" width="16" height="16" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            Enter the code shared by your partner to connect.
          </div>
        </form>
      )}
    </div>
  );
}
