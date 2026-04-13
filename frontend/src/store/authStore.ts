/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const GITHUB_CLIENT_ID = import.meta.env.VITE_GITHUB_CLIENT_ID;
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
const REDIRECT_URI = `${window.location.origin}/auth/callback`;

export interface GitHubUser {
  login: string;
  name: string;
  avatar_url: string;
  email: string;
}

interface AuthState {
  hasHydrated: boolean;
  isAuthenticated: boolean;
  accessToken: string | null;
  user: GitHubUser | null;
  error: string | null;
  isLoading: boolean;
  initiateGitHubLogin: () => void;
  exchangeCode: (code: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
  markHydrated: () => void;
}

const getErrorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      hasHydrated: false,
      isAuthenticated: false,
      accessToken: null,
      user: null,
      error: null,
      isLoading: false,

      markHydrated: () => set({ hasHydrated: true }),

      initiateGitHubLogin: () => {
        if (!GITHUB_CLIENT_ID) {
          set({
            error: 'Missing VITE_GITHUB_CLIENT_ID. Add it to your environment before signing in.',
          });
          return;
        }

        const githubAuthUrl = new URL('https://github.com/login/oauth/authorize');
        githubAuthUrl.searchParams.set('client_id', GITHUB_CLIENT_ID);
        githubAuthUrl.searchParams.set('redirect_uri', REDIRECT_URI);
        githubAuthUrl.searchParams.set('scope', 'repo user:email');

        window.location.assign(githubAuthUrl.toString());
      },

      exchangeCode: async (code: string) => {
        set({ isLoading: true, error: null });

        try {
          const response = await fetch(`${BACKEND_URL}/auth/github/callback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code }),
          });

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(
              errorData.detail || errorData.message || 'Failed to authenticate with GitHub',
            );
          }

          const data = await response.json();

          set({
            isAuthenticated: true,
            accessToken: data.access_token,
            user: data.user,
            isLoading: false,
            error: null,
          });
        } catch (error) {
          const message = getErrorMessage(error, 'Failed to authenticate with GitHub');

          set({
            isAuthenticated: false,
            accessToken: null,
            user: null,
            isLoading: false,
            error: message,
          });

          throw error instanceof Error ? error : new Error(message);
        }
      },

      logout: () => {
        set({
          isAuthenticated: false,
          accessToken: null,
          user: null,
          error: null,
          isLoading: false,
        });

        window.localStorage.removeItem('conductor-auth');
        window.location.assign('/login');
      },

      checkAuth: async () => {
        const { accessToken, user } = get();

        if (!accessToken) {
          set({ isAuthenticated: false, isLoading: false, error: null });
          return;
        }

        set({ isLoading: true, error: null });

        try {
          const response = await fetch(`${BACKEND_URL}/auth/verify`, {
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
          });

          if (!response.ok) {
            throw new Error('Your GitHub session has expired. Please sign in again.');
          }

          const contentType = response.headers.get('content-type') || '';
          const data = contentType.includes('application/json')
            ? await response.json().catch(() => null)
            : null;

          set({
            isAuthenticated: true,
            user: data?.user ?? user,
            isLoading: false,
            error: null,
          });
        } catch (error) {
          set({
            isAuthenticated: false,
            accessToken: null,
            user: null,
            isLoading: false,
            error: getErrorMessage(error, 'Authentication check failed'),
          });

          window.localStorage.removeItem('conductor-auth');
        }
      },
    }),
    {
      name: 'conductor-auth',
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
        accessToken: state.accessToken,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        state?.markHydrated();
      },
    },
  ),
);
