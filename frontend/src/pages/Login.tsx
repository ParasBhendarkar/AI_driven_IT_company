/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import React from 'react';
import { Navigate } from 'react-router-dom';
import { CheckCircle, GitBranch, Github, Lock, Terminal } from 'lucide-react';
import { useAuthStore } from '../store/authStore';

export const Login: React.FC = () => {
  const initiateGitHubLogin = useAuthStore((state) => state.initiateGitHubLogin);
  const error = useAuthStore((state) => state.error);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const hasHydrated = useAuthStore((state) => state.hasHydrated);

  const features = [
    { icon: Lock, text: 'Secure OAuth 2.0 authentication' },
    { icon: GitBranch, text: 'Access to your repositories and branches' },
    { icon: CheckCircle, text: 'Select repo & branch per task' },
    { icon: Terminal, text: 'AI-powered task automation' },
  ];

  if (hasHydrated && isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="min-h-screen bg-[#0F0F0F] flex items-center justify-center p-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center space-y-4">
          <div className="w-16 h-16 bg-indigo-600 rounded-2xl flex items-center justify-center mx-auto shadow-xl shadow-indigo-500/20">
            <Terminal className="text-white w-8 h-8" />
          </div>
          <div className="space-y-2">
            <h1 className="text-3xl font-bold text-[#F5F5F5]">Welcome to Conductor</h1>
            <p className="text-[#A0A0A0] text-sm">
              AI-driven software development automation
            </p>
          </div>
        </div>

        <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-2xl p-8 space-y-6 shadow-xl">
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-[#F5F5F5]">Connect Your GitHub Account</h2>
            <p className="text-sm text-[#A0A0A0] leading-relaxed">
              To use Conductor, you need to connect your GitHub account. This allows our AI
              agents to access and manage your repositories.
            </p>
          </div>

          <div className="space-y-3 py-4 border-y border-[#2A2A2A]">
            {features.map((feature, index) => (
              <div key={index} className="flex items-center gap-3">
                <div className="w-8 h-8 bg-[#242424] rounded-lg flex items-center justify-center">
                  <feature.icon className="w-4 h-4 text-indigo-400" />
                </div>
                <span className="text-sm text-[#A0A0A0]">{feature.text}</span>
              </div>
            ))}
          </div>

          <button
            onClick={initiateGitHubLogin}
            className="w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl px-6 py-4 text-sm font-medium transition-all flex items-center justify-center gap-3 shadow-lg shadow-indigo-500/20"
          >
            <Github className="w-5 h-5" />
            Continue with GitHub
          </button>

          {error && (
            <p className="text-xs text-red-400 text-center leading-relaxed">
              {error}
            </p>
          )}

          <p className="text-xs text-[#5A5A5A] text-center leading-relaxed">
            By connecting, you agree to allow Conductor access to your repositories. You can
            revoke access anytime from your GitHub settings.
          </p>
        </div>

        <div className="text-center space-y-2">
          <p className="text-xs text-[#5A5A5A]">
            Powered by open-source AI models - 100% private
          </p>
        </div>
      </div>
    </div>
  );
};
