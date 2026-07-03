import { useState } from 'react';
import { useAuthStore } from '../store';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { ShieldCheck, Loader2 } from 'lucide-react';

export function Login() {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState('');

  const setToken = useAuthStore((state) => state.setToken);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    const endpoint = isRegister ? '/api/auth/register' : '/api/auth/login';
    const payload = isRegister
      ? { email, password, username: username || email.split('@')[0], name: name || username, role: 'engineer' }
      : { email, password };

    try {
      let response;
      try {
        response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } catch (networkError) {
        throw new Error('Unable to connect to the server. Please check your connection or try again later.');
      }

      const text = await response.text();
      let data: any;
      try {
        data = text ? JSON.parse(text) : {};
      } catch (parseError) {
        data = { detail: text || 'Server returned an invalid response.' };
      }

      if (!response.ok) {
        throw new Error(data.detail || `HTTP Error ${response.status}`);
      }

      if (isRegister) {
        setSuccess('Registration successful! Please sign in.');
        setIsRegister(false);
        setPassword('');
      } else {
        setToken(data.access_token);
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-screen bg-bg-base flex items-center justify-center p-4">
      {/* Background visualizer */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-primary/10 via-transparent to-transparent pointer-events-none" />

      <Card className="w-full max-w-[400px] border border-outline-variant bg-surface-container-low/75 backdrop-blur-xl shadow-2xl relative z-10">
        <CardHeader className="text-center pb-4">
          <div className="w-12 h-12 rounded-xl bg-primary/15 flex items-center justify-center border border-primary/30 mx-auto mb-3">
            <ShieldCheck size={24} className="text-primary" />
          </div>
          <CardTitle className="text-xl font-bold tracking-tight">
            ATLAS<span className="text-primary">OS</span>
          </CardTitle>
          <p className="text-xs text-on-surface-variant/80 mt-1">
            Industrial Knowledge Intelligence Platform
          </p>
        </CardHeader>

        <CardContent className="space-y-4">
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-xs text-red-400 text-center">
              {error}
            </div>
          )}

          {success && (
            <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-xs text-green-400 text-center">
              {success}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            {isRegister && (
              <>
                <div className="space-y-1">
                  <label className="text-[10px] font-mono tracking-wider text-on-surface-variant uppercase">Username</label>
                  <Input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="r.mehta"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] font-mono tracking-wider text-on-surface-variant uppercase">Full Name</label>
                  <Input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Rahul Mehta"
                    required
                  />
                </div>
              </>
            )}

            <div className="space-y-1">
              <label className="text-[10px] font-mono tracking-wider text-on-surface-variant uppercase">Email Address</label>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="operator@plant.com"
                required
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-mono tracking-wider text-on-surface-variant uppercase">Password</label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>

            <Button type="submit" disabled={loading} className="w-full mt-4 flex items-center justify-center gap-2">
              {loading && <Loader2 size={14} className="animate-spin" />}
              {loading ? 'Processing...' : isRegister ? 'Create Account' : 'Sign In'}
            </Button>
          </form>

          <div className="text-center pt-2">
            <button
              onClick={() => {
                setIsRegister(!isRegister);
                setError('');
                setSuccess('');
              }}
              className="text-xs text-primary hover:underline"
            >
              {isRegister ? 'Already have an account? Sign In' : "Don't have an account? Sign Up"}
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
