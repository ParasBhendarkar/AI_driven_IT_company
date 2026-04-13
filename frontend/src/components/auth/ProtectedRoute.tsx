/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import React, { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isLoading = useAuthStore((state) => state.isLoading);
  const hasHydrated = useAuthStore((state) => state.hasHydrated);
  const checkAuth = useAuthStore((state) => state.checkAuth);
  const location = useLocation();
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    let isMounted = true;

    if (!hasHydrated) {
      return;
    }

    setIsReady(false);

    const verifyAuth = async () => {
      await checkAuth();

      if (isMounted) {
        setIsReady(true);
      }
    };

    void verifyAuth();

    return () => {
      isMounted = false;
    };
  }, [checkAuth, hasHydrated]);

  if (!hasHydrated || !isReady || isLoading) {
    return (
      <div className="min-h-screen bg-[#0F0F0F] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};
