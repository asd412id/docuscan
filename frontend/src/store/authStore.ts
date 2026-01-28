import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '@/types';
import { authService } from '@/services/auth';

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isInitialized: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
  initialize: () => Promise<void>;
  setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      isInitialized: false,
      
      login: async (username: string, password: string) => {
        set({ isLoading: true });
        try {
          await authService.login(username, password);
          const user = await authService.getCurrentUser();
          set({ user, isAuthenticated: true, isLoading: false });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },
      
      register: async (email: string, username: string, password: string, fullName?: string) => {
        set({ isLoading: true });
        try {
          await authService.register(email, username, password, fullName);
          set({ isLoading: false });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },
      
      logout: async () => {
        set({ isLoading: true });
        try {
          await authService.logout();
        } finally {
          set({ user: null, isAuthenticated: false, isLoading: false });
        }
      },
      
      initialize: async () => {
        // Skip if already initialized
        if (get().isInitialized) return;
        
        // Check if there's a token
        if (!authService.isAuthenticated()) {
          set({ user: null, isAuthenticated: false, isInitialized: true });
          return;
        }
        
        // Validate token by fetching current user
        set({ isLoading: true });
        try {
          const user = await authService.getCurrentUser();
          set({ user, isAuthenticated: true, isLoading: false, isInitialized: true });
        } catch {
          // Token invalid - clear auth state
          authService.clearTokens();
          set({ user: null, isAuthenticated: false, isLoading: false, isInitialized: true });
        }
      },
      
      setUser: (user: User | null) => set({ user, isAuthenticated: !!user }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ 
        isAuthenticated: state.isAuthenticated,
        user: state.user,
      }),
    }
  )
);
