/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import { create } from 'zustand';
import { useAuthStore } from './authStore';

export interface GitHubRepository {
  id: number;
  name: string;
  full_name: string;
  private: boolean;
  default_branch: string;
  html_url: string;
}

export interface GitHubBranch {
  name: string;
  protected: boolean;
}

interface GitHubState {
  repositories: GitHubRepository[];
  branches: Record<string, GitHubBranch[]>;
  isLoadingRepos: boolean;
  isLoadingBranches: Record<string, boolean>;
  error: string | null;
  fetchRepositories: () => Promise<GitHubRepository[]>;
  fetchBranches: (repoFullName: string) => Promise<GitHubBranch[]>;
}

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

const getErrorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

export const useGitHubStore = create<GitHubState>((set, get) => ({
  repositories: [],
  branches: {},
  isLoadingRepos: false,
  isLoadingBranches: {},
  error: null,

  fetchRepositories: async () => {
    const token = useAuthStore.getState().accessToken;

    if (!token) {
      const message = 'Not authenticated';
      set({ error: message, repositories: [], isLoadingRepos: false });
      throw new Error(message);
    }

    set({ isLoadingRepos: true, error: null });

    try {
      const response = await fetch(`${BACKEND_URL}/github/repositories`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || errorData.message || 'Failed to fetch repositories');
      }

      const repositories = (await response.json()) as GitHubRepository[];
      set({ repositories, isLoadingRepos: false, error: null });
      return repositories;
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to fetch repositories');

      set({
        error: message,
        isLoadingRepos: false,
        repositories: [],
      });

      throw error instanceof Error ? error : new Error(message);
    }
  },

  fetchBranches: async (repoFullName: string) => {
    const token = useAuthStore.getState().accessToken;

    if (!token) {
      const message = 'Not authenticated';
      set({ error: message });
      throw new Error(message);
    }

    if (get().branches[repoFullName]) {
      return get().branches[repoFullName];
    }

    set({
      isLoadingBranches: { ...get().isLoadingBranches, [repoFullName]: true },
      error: null,
    });

    try {
      const response = await fetch(
        `${BACKEND_URL}/github/repositories/${encodeURIComponent(repoFullName)}/branches`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || errorData.message || 'Failed to fetch branches');
      }

      const branches = (await response.json()) as GitHubBranch[];

      set({
        branches: { ...get().branches, [repoFullName]: branches },
        isLoadingBranches: { ...get().isLoadingBranches, [repoFullName]: false },
        error: null,
      });

      return branches;
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to fetch branches');

      set({
        error: message,
        isLoadingBranches: { ...get().isLoadingBranches, [repoFullName]: false },
      });

      throw error instanceof Error ? error : new Error(message);
    }
  },
}));
