/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AlertCircle, CheckCircle, Loader2 } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useGitHubStore } from '../store/githubStore';

const getErrorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

export const Auth: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const exchangeCode = useAuthStore((state) => state.exchangeCode);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const authError = useAuthStore((state) => state.error);
  const fetchRepositories = useGitHubStore((state) => state.fetchRepositories);

  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const processedCodeRef = useRef<string | null>(null);
  const redirectTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (redirectTimerRef.current !== null) {
        window.clearTimeout(redirectTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const code = searchParams.get('code');
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setError(`GitHub OAuth error: ${errorParam}`);
      return;
    }

    if (!code) {
      setError('Missing GitHub authorization code.');
      return;
    }

    if (processedCodeRef.current === code) {
      return;
    }

    processedCodeRef.current = code;

    const handleCodeExchange = async () => {
      setIsLoading(true);
      setError(null);

      try {
        await exchangeCode(code);
        await fetchRepositories();

        redirectTimerRef.current = window.setTimeout(() => {
          navigate('/dashboard', { replace: true });
        }, 1500);
      } catch (exchangeError) {
        setError(getErrorMessage(exchangeError, 'Failed to authenticate with GitHub'));
      } finally {
        setIsLoading(false);
      }
    };

    void handleCodeExchange();
  }, [exchangeCode, fetchRepositories, navigate, searchParams]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#0F0F0F] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-[#1A1A1A] border border-[#2A2A2A] rounded-2xl p-8 text-center space-y-6">
          <Loader2 className="w-12 h-12 text-indigo-500 animate-spin mx-auto" />
          <div className="space-y-2">
            <h2 className="text-xl font-bold text-[#F5F5F5]">Connecting to GitHub</h2>
            <p className="text-[#A0A0A0] text-sm">
              Please wait while we authenticate your account...
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (error || authError) {
    return (
      <div className="min-h-screen bg-[#0F0F0F] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-[#1A1A1A] border border-[#2A2A2A] rounded-2xl p-8 text-center space-y-6">
          <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mx-auto">
            <AlertCircle className="w-8 h-8 text-red-500" />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-bold text-[#F5F5F5]">Authentication Failed</h2>
            <p className="text-red-400 text-sm">{error || authError}</p>
          </div>
          <button
            onClick={() => navigate('/login', { replace: true })}
            className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-3 rounded-xl text-sm font-medium transition-all"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#0F0F0F] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-[#1A1A1A] border border-[#2A2A2A] rounded-2xl p-8 text-center space-y-6">
          <div className="w-16 h-16 bg-green-500/10 rounded-full flex items-center justify-center mx-auto">
            <CheckCircle className="w-8 h-8 text-green-500" />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-bold text-[#F5F5F5]">Authentication Successful!</h2>
            <p className="text-[#A0A0A0] text-sm">Loading your repositories...</p>
            <p className="text-[#A0A0A0] text-sm">Redirecting to dashboard...</p>
          </div>
        </div>
      </div>
    );
  }

  return null;
};
