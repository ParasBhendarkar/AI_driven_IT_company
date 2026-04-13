/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  CheckSquare,
  AlertCircle,
  Brain,
  Activity,
  Terminal,
  LogOut,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useAuthStore } from '../../store/authStore';

const navItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/dashboard' },
  { icon: CheckSquare, label: 'Tasks', path: '/tasks', count: 3 },
  { icon: AlertCircle, label: 'Inbox', path: '/inbox', badge: 2 },
  { icon: Brain, label: 'Memory', path: '/memory' },
  { icon: Activity, label: 'Activity', path: '/activity' },
];

export const Sidebar: React.FC = () => {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  return (
    <aside className="w-[220px] fixed left-0 top-0 h-screen bg-[#0F0F0F] border-r border-[#2A2A2A] flex flex-col z-50">
      <div className="p-6 flex items-center gap-3">
        <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
          <Terminal className="text-white w-5 h-5" />
        </div>
        <span className="font-semibold text-lg tracking-tight text-[#F5F5F5]">Conductor</span>
      </div>

      <nav className="flex-1 px-3 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => cn(
              'flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors',
              isActive 
                ? 'bg-indigo-600/10 text-indigo-400 font-medium' 
                : 'text-[#A0A0A0] hover:text-[#F5F5F5] hover:bg-[#1A1A1A]'
            )}
          >
            <div className="flex items-center gap-3">
              <item.icon className="w-4 h-4" />
              {item.label}
            </div>
            {item.badge && (
              <span className="bg-red-500 text-white text-[10px] px-1.5 py-0.5 rounded-full font-bold">
                {item.badge}
              </span>
            )}
            {item.count && (
              <span className="text-[#5A5A5A] text-[10px] font-mono">
                {item.count}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-[#2A2A2A] space-y-4">
        <button
          onClick={logout}
          className="flex items-center gap-3 px-3 py-2 w-full text-[#5A5A5A] hover:text-red-400 text-sm transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Logout
        </button>

        <div className="flex items-center gap-3 px-3 py-2">
          <img
            src={user?.avatar_url || 'https://avatar.vercel.sh/conductor'}
            alt={user?.name || 'User'}
            className="w-8 h-8 rounded-full border border-[#2A2A2A]"
            onError={(event) => {
              event.currentTarget.src = 'https://avatar.vercel.sh/conductor';
            }}
          />
          <div className="flex flex-col overflow-hidden">
            <span className="text-xs font-medium text-[#F5F5F5] truncate">
              {user?.name || user?.login || 'User'}
            </span>
            <span className="text-[10px] text-[#5A5A5A] truncate">
              @{user?.login || 'user'}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
};
