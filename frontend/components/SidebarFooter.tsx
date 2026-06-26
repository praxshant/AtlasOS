'use client';

import React, { useEffect, useState } from 'react';

export default function SidebarFooter() {
  const [username, setUsername] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    setUsername(localStorage.getItem('username'));
    setRole(localStorage.getItem('user_role'));
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    localStorage.removeItem('user_role');
    window.location.reload();
  };

  return (
    <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      {username && (
        <div style={{ fontSize: '0.8rem', borderTop: '1px solid rgba(255, 255, 255, 0.05)', paddingTop: '0.75rem', marginBottom: '0.25rem' }}>
          <div style={{ color: 'var(--text-primary)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            👤 {username}
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.5px', marginTop: '0.1rem' }}>
            Role: {role}
          </div>
        </div>
      )}
      <button
        onClick={handleLogout}
        className="btn btn-secondary"
        style={{
          padding: '0.4rem',
          fontSize: '0.8rem',
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '32px'
        }}
      >
        🚪 Sign Out
      </button>
    </div>
  );
}
