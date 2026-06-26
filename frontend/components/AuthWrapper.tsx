'use client';

import React, { useState, useEffect } from 'react';
import { getBackendUrl, setBackendUrl } from '../utils/api';

export default function AuthWrapper({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [isRegistering, setIsRegistering] = useState(false);
  const [inputUsername, setInputUsername] = useState('');
  const [inputEmail, setInputEmail] = useState('');
  const [inputPassword, setInputPassword] = useState('');
  const [inputRole, setInputRole] = useState('engineer');
  const [backendUrl, setLocalBackendUrl] = useState('http://localhost:8000');
  const [showSettings, setShowSettings] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  useEffect(() => {
    const savedToken = localStorage.getItem('token');
    const savedUsername = localStorage.getItem('username');
    const savedRole = localStorage.getItem('user_role');
    const savedUrl = getBackendUrl();
    
    setToken(savedToken);
    setUsername(savedUsername);
    setRole(savedRole);
    setLocalBackendUrl(savedUrl);
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputUsername || !inputPassword) return;

    setLoading(true);
    setError('');
    setSuccessMsg('');

    try {
      const response = await fetch(`${backendUrl}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: inputUsername,
          password: inputPassword,
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Authentication failed. Please check your credentials.');
      }

      const data = await response.json();
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('username', data.username);
      localStorage.setItem('user_role', data.role);
      
      setToken(data.access_token);
      setUsername(data.username);
      setRole(data.role);
      // Force reload to update headers across components
      window.location.reload();
    } catch (err: any) {
      setError(err.message || 'An error occurred during login.');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputUsername || !inputPassword || !inputEmail) return;

    setLoading(true);
    setError('');
    setSuccessMsg('');

    try {
      const response = await fetch(`${backendUrl}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: inputUsername,
          email: inputEmail,
          password: inputPassword,
          role: inputRole,
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Registration failed.');
      }

      setSuccessMsg('Registration successful! Please login.');
      setIsRegistering(false);
      setInputPassword('');
    } catch (err: any) {
      setError(err.message || 'An error occurred during registration.');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSettings = (e: React.FormEvent) => {
    e.preventDefault();
    setBackendUrl(backendUrl);
    setShowSettings(false);
  };

  if (token) {
    return <>{children}</>;
  }

  return (
    <div className="auth-lock-screen" style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      width: '100vw',
      background: 'var(--bg-primary)',
      backgroundImage: 'radial-gradient(circle at 50% 50%, rgba(14, 165, 233, 0.05) 0%, transparent 70%)',
      padding: '2rem',
      position: 'fixed',
      top: 0,
      left: 0,
      zIndex: 9999,
      fontFamily: 'var(--font-sans)',
      overflowY: 'auto'
    }}>
      <div className="card-panel" style={{
        width: '100%',
        maxWidth: '440px',
        padding: '2.5rem',
        border: '1px solid rgba(14, 165, 233, 0.15)',
        boxShadow: '0 10px 40px rgba(0, 0, 0, 0.6), 0 0 20px rgba(14, 165, 233, 0.05)',
        position: 'relative'
      }}>
        {/* Settings toggle */}
        <button 
          onClick={() => setShowSettings(!showSettings)}
          style={{
            position: 'absolute',
            top: '1.25rem',
            right: '1.25rem',
            background: 'none',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            fontSize: '1.2rem',
            transition: 'var(--transition-fast)'
          }}
          onMouseEnter={(e) => e.currentTarget.style.color = 'var(--accent-teal)'}
          onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
          title="Server Settings"
        >
          ⚙
        </button>

        {showSettings ? (
          <div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '1.25rem', color: 'var(--text-primary)' }}>
              Server Gateway Config
            </h3>
            <form onSubmit={handleSaveSettings}>
              <div className="form-group">
                <label className="form-label">Backend API Base URL</label>
                <input
                  type="text"
                  value={backendUrl}
                  onChange={(e) => setLocalBackendUrl(e.target.value)}
                  className="form-input"
                  placeholder="http://localhost:8000"
                  required
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem', display: 'block' }}>
                  Set to http://localhost:8050 if port 8000 is occupied.
                </span>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
                <button type="submit" className="btn btn-primary" style={{ flex: 1 }}>
                  Save
                </button>
                <button 
                  type="button" 
                  className="btn btn-secondary" 
                  style={{ flex: 1 }}
                  onClick={() => setShowSettings(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        ) : (
          <div>
            <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
              <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem', textShadow: '0 0 10px rgba(14, 165, 233, 0.4)', color: 'var(--accent-teal)' }}>
                ⏃
              </div>
              <h2 style={{ fontSize: '1.6rem', fontWeight: 700, letterSpacing: '1px', marginBottom: '0.25rem' }}>
                ATLASOS
              </h2>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Industrial Knowledge Intelligence Platform
              </p>
            </div>

            {error && (
              <div style={{
                marginBottom: '1.25rem',
                padding: '0.75rem 1rem',
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.2)',
                borderRadius: '8px',
                color: 'var(--accent-red)',
                fontSize: '0.85rem'
              }}>
                {error}
              </div>
            )}

            {successMsg && (
              <div style={{
                marginBottom: '1.25rem',
                padding: '0.75rem 1rem',
                background: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.2)',
                borderRadius: '8px',
                color: 'var(--accent-green)',
                fontSize: '0.85rem'
              }}>
                {successMsg}
              </div>
            )}

            <form onSubmit={isRegistering ? handleRegister : handleLogin}>
              <div className="form-group">
                <label className="form-label">Username</label>
                <input
                  type="text"
                  value={inputUsername}
                  onChange={(e) => setInputUsername(e.target.value)}
                  className="form-input"
                  placeholder="Enter username"
                  disabled={loading}
                  required
                />
              </div>

              {isRegistering && (
                <div className="form-group">
                  <label className="form-label">Email Address</label>
                  <input
                    type="email"
                    value={inputEmail}
                    onChange={(e) => setInputEmail(e.target.value)}
                    className="form-input"
                    placeholder="name@plant.com"
                    disabled={loading}
                    required
                  />
                </div>
              )}

              <div className="form-group">
                <label className="form-label">Password</label>
                <input
                  type="password"
                  value={inputPassword}
                  onChange={(e) => setInputPassword(e.target.value)}
                  className="form-input"
                  placeholder="••••••••"
                  disabled={loading}
                  required
                />
              </div>

              {isRegistering && (
                <div className="form-group">
                  <label className="form-label">Assign Role</label>
                  <select
                    value={inputRole}
                    onChange={(e) => setInputRole(e.target.value)}
                    className="form-input"
                    style={{ background: 'var(--bg-secondary)', height: '45px' }}
                    disabled={loading}
                  >
                    <option value="engineer">Engineer (Write Access)</option>
                    <option value="viewer">Viewer (Read Only)</option>
                    <option value="admin">Administrator (Full Access)</option>
                  </select>
                </div>
              )}

              <button 
                type="submit" 
                className="btn btn-primary" 
                style={{ width: '100%', marginTop: '1rem', height: '45px' }}
                disabled={loading}
              >
                {loading ? 'Authenticating...' : isRegistering ? 'Register Operator' : 'Sign In'}
              </button>

              <div style={{ textAlign: 'center', marginTop: '1.5rem', fontSize: '0.85rem' }}>
                <span style={{ color: 'var(--text-secondary)' }}>
                  {isRegistering ? 'Already registered?' : 'Authorized operators only.'}
                </span>{' '}
                <button
                  type="button"
                  onClick={() => {
                    setIsRegistering(!isRegistering);
                    setError('');
                    setSuccessMsg('');
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--accent-teal)',
                    cursor: 'pointer',
                    fontWeight: 600,
                    textDecoration: 'underline'
                  }}
                  disabled={loading}
                >
                  {isRegistering ? 'Sign In instead' : 'Request access'}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
