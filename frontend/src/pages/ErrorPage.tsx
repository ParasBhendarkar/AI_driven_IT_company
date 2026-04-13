/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { useRouteError, isRouteErrorResponse, Link } from 'react-router-dom';
import { AlertCircle, Home } from 'lucide-react';

export const ErrorPage: React.FC = () => {
  const error = useRouteError();
  let errorMessage: string;

  if (isRouteErrorResponse(error)) {
    errorMessage = error.statusText || error.data?.message || 'Page not found';
  } else if (error instanceof Error) {
    errorMessage = error.message;
  } else if (typeof error === 'string') {
    errorMessage = error;
  } else {
    console.error(error);
    errorMessage = 'Unknown error';
  }

  return (
    <div className="min-h-screen bg-[#0F0F0F] flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-[#1A1A1A] border border-[#2A2A2A] rounded-2xl p-8 text-center space-y-6 shadow-2xl">
        <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mx-auto">
          <AlertCircle className="w-8 h-8 text-red-500" />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-[#F5F5F5]">Oops! Something went wrong</h1>
          <p className="text-[#A0A0A0] text-sm">{errorMessage}</p>
        </div>
        <Link 
          to="/dashboard" 
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-3 rounded-xl text-sm font-medium transition-all shadow-lg shadow-indigo-600/20"
        >
          <Home className="w-4 h-4" />
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
};
