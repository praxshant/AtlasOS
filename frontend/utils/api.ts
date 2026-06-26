export function getBackendUrl(): string {
  if (typeof window !== 'undefined') {
    return localStorage.getItem("backend_url") || "http://localhost:8000";
  }
  return "http://localhost:8000";
}

export function setBackendUrl(url: string) {
  if (typeof window !== 'undefined') {
    localStorage.setItem("backend_url", url);
  }
}

export async function authenticatedFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = typeof window !== 'undefined' ? localStorage.getItem("token") : null;
  const baseUrl = getBackendUrl();
  const url = `${baseUrl}${path.startsWith('/') ? '' : '/'}${path}`;

  const headers = new Headers(options.headers || {});
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem("token");
      localStorage.removeItem("user_role");
      localStorage.removeItem("username");
      // Trigger a reload so the parent AuthWrapper immediately locks down the UI
      window.location.reload();
    }
  }

  return response;
}
