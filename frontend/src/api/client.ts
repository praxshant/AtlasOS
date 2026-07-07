export const API_BASE = '/api';

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, data: any, message: string) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export async function authenticatedFetch(endpoint: string, options: RequestInit = {}) {
  const token = localStorage.getItem('token') || sessionStorage.getItem('token');
  const headers = new Headers(options.headers);
  
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  // Ensure JSON for POST/PUT if body is an object and not FormData
  if (
    options.body && 
    typeof options.body === 'object' && 
    !(options.body instanceof FormData) && 
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json');
    options.body = JSON.stringify(options.body);
  }

  const response = await fetch(`${API_BASE}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem('token');
      sessionStorage.removeItem('token');
      window.location.href = '/login';
      throw new ApiError(401, null, 'Session expired. Please log in again.');
    }

    let errorData = null;
    try {
      errorData = await response.json();
    } catch {
      errorData = await response.text();
    }
    throw new ApiError(response.status, errorData, `HTTP Error ${response.status}`);
  }

  return response;
}

export async function getJson<T>(endpoint: string): Promise<T> {
  const res = await authenticatedFetch(endpoint);
  return res.json();
}
