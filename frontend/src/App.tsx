import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store';
import { AppShell } from './components/layout/AppShell';
import { Dashboard } from './pages/Dashboard';
import { Documents } from './pages/Documents';
import { KnowledgeGraph } from './pages/KnowledgeGraph';
import { Copilot } from './pages/Copilot';
import { Coverage } from './pages/Coverage';
import { Engineers } from './pages/Engineers';
import { Compliance } from './pages/Compliance';
import { RCA } from './pages/RCA';
import { Risk } from './pages/Risk';
import { Login } from './pages/Login';

function App() {
  const token = useAuthStore((state) => state.token);

  if (!token) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/graph" element={<KnowledgeGraph />} />
        <Route path="/copilot" element={<Copilot />} />
        <Route path="/compliance" element={<Compliance />} />
        <Route path="/rca" element={<RCA />} />
        <Route path="/risk" element={<Risk />} />
        <Route path="/engineers" element={<Engineers />} />
        <Route path="/coverage" element={<Coverage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}

export default App;
