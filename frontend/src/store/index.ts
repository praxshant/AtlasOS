import { create } from 'zustand';

interface UIState {
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (isOpen: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  isSidebarOpen: true,
  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  setSidebarOpen: (isOpen) => set({ isSidebarOpen: isOpen }),
}));

interface AuthState {
  token: string | null;
  tenantId: string;
  setToken: (token: string | null) => void;
  setTenantId: (tenantId: string) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('token') || sessionStorage.getItem('token'),
  tenantId: 'default',
  setToken: (token) => {
    if (token) localStorage.setItem('token', token);
    else localStorage.removeItem('token');
    set({ token });
  },
  setTenantId: (tenantId) => set({ tenantId }),
}));
