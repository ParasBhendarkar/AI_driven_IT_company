/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { Login } from './pages/Login';
import { Auth } from './pages/Auth';
import { Dashboard } from './pages/Dashboard';
import { TaskDetail } from './pages/TaskDetail';
import { AgentLog } from './pages/AgentLog';
import { Inbox } from './pages/Inbox';
import { MemoryExplorer } from './pages/MemoryExplorer';
import { Activity } from './pages/Activity';
import { ErrorPage } from './pages/ErrorPage';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/auth/callback',
    element: <Auth />,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    errorElement: <ErrorPage />,
    children: [
      {
        index: true,
        element: <Navigate to="/dashboard" replace />,
      },
      {
        path: 'dashboard',
        element: <Dashboard />,
      },
      {
        path: 'tasks',
        element: <Navigate to="/dashboard" replace />,
      },
      {
        path: 'tasks/:id',
        element: <TaskDetail />,
      },
      {
        path: 'tasks/:id/log',
        element: <AgentLog />,
      },
      {
        path: 'inbox',
        element: <Inbox />,
      },
      {
        path: 'memory',
        element: <MemoryExplorer />,
      },
      {
        path: 'activity',
        element: <Activity />,
      },
      {
        path: '*',
        element: <Navigate to="/dashboard" replace />,
      },
    ],
  },
]);
