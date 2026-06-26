import './globals.css';
import type { Metadata } from 'next';
import React from 'react';
import AuthWrapper from '../components/AuthWrapper';
import SidebarFooter from '../components/SidebarFooter';

export const metadata: Metadata = {
  title: 'ATLASOS — Industrial Operations Intelligence',
  description: 'AI-grounded expert copilot, root cause analysis, and compliance intelligence platform.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet" />
      </head>
      <body>
        <AuthWrapper>
          <div className="app-container">
            <aside className="app-sidebar">
              <div className="sidebar-logo">
                <span className="logo-symbol">⏃</span>
                <span className="logo-text">ATLAS<span className="logo-sub">OS</span></span>
              </div>
              <div className="sidebar-badge">OPERATIONS HUB</div>
              
              <nav className="sidebar-nav">
                <a href="/" className="nav-item">
                  <span className="nav-icon">📊</span> Dashboard
                </a>
                <a href="/copilot" className="nav-item">
                  <span className="nav-icon">💬</span> Expert Copilot
                </a>
                <a href="/rca" className="nav-item">
                  <span className="nav-icon">🔍</span> RCA Report
                </a>
                <a href="/compliance" className="nav-item">
                  <span className="nav-icon">🛡️</span> Compliance Gaps
                </a>
                <a href="/graph" className="nav-item">
                  <span className="nav-icon">🕸️</span> Graph Explorer
                </a>
              </nav>
              
              <div className="sidebar-footer">
                <div className="system-status">
                  <span className="status-dot online"></span>
                  <span>System Gateway: OK</span>
                </div>
                <SidebarFooter />
              </div>
            </aside>
            
            <main className="app-content">
              {children}
            </main>
          </div>
        </AuthWrapper>
      </body>
    </html>
  );
}
