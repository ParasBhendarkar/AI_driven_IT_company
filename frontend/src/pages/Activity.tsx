/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';
import { CircleCheckBig, CircleX, Shield, Clock, Database, Zap } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { cn } from '../lib/utils';
import { fetchJson } from '../lib/backend';

interface ActivityRow {
  id: string;
  title: string;
  status: string;
  description: string;
  agents: string[];
  time: string;
  type: 'success' | 'error' | 'warning' | 'info';
}

interface ActivityStats {
  tasksThisWeek: number;
  avgRetries: number;
  cisoBlocks: number;
  memoryWrites: number;
  chartData: Array<{ day: string; completed: number; escalated: number }>;
}

export const Activity: React.FC = () => {
  const [filter, setFilter] = useState('All');
  const [events, setEvents] = useState<ActivityRow[]>([]);
  const [stats, setStats] = useState<ActivityStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [activityData, statsData] = await Promise.all([
          fetchJson<ActivityRow[]>(`/activity?filter=${encodeURIComponent(filter)}`),
          fetchJson<ActivityStats>('/activity/stats'),
        ]);
        setEvents(activityData);
        setStats(statsData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load activity');
      }
    };

    void load();
  }, [filter]);

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Tasks this week', value: stats?.tasksThisWeek ?? '--', icon: Zap, color: 'text-indigo-400' },
          { label: 'Avg retries', value: stats?.avgRetries ?? '--', icon: Clock, color: 'text-amber-400' },
          { label: 'CISO blocks', value: stats?.cisoBlocks ?? '--', icon: Shield, color: 'text-orange-400' },
          { label: 'Memory writes', value: stats?.memoryWrites ?? '--', icon: Database, color: 'text-purple-400' },
        ].map((stat, i) => (
          <div key={i} className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-5">
            <div className="flex justify-between items-start mb-2">
              <span className="text-[10px] font-bold text-[#5A5A5A] uppercase tracking-wider">{stat.label}</span>
              <stat.icon className={cn('w-4 h-4', stat.color)} />
            </div>
            <div className="text-2xl font-semibold text-[#F5F5F5]">{stat.value}</div>
          </div>
        ))}
      </div>

      <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[#F5F5F5]">Tasks per Day (Last 7 Days)</h2>
        </div>
        <div className="h-[300px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stats?.chartData ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2A2A2A" vertical={false} />
              <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fill: '#5A5A5A', fontSize: 12 }} dy={10} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: '#5A5A5A', fontSize: 12 }} />
              <Tooltip cursor={{ fill: '#242424' }} contentStyle={{ backgroundColor: '#1A1A1A', border: '1px solid #2A2A2A', borderRadius: '8px' }} itemStyle={{ fontSize: '12px' }} />
              <Bar dataKey="completed" stackId="a" fill="#6366F1" radius={[0, 0, 0, 0]} />
              <Bar dataKey="escalated" stackId="a" fill="#EF4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[#F5F5F5]">Activity Feed</h2>
          <div className="flex gap-1 bg-[#1A1A1A] border border-[#2A2A2A] p-1 rounded-lg">
            {['All', 'Completed', 'Failed', 'Escalated', 'Deployed'].map((value) => (
              <button
                key={value}
                onClick={() => setFilter(value)}
                className={cn(
                  'px-3 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-all',
                  filter === value ? 'bg-[#242424] text-[#F5F5F5]' : 'text-[#5A5A5A] hover:text-[#A0A0A0]',
                )}
              >
                {value}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl divide-y divide-[#2A2A2A]">
          {events.map((event) => (
            <div key={event.id} className="p-4 flex items-center justify-between hover:bg-[#242424]/20 transition-colors group">
              <div className="flex items-center gap-4">
                <div
                  className={cn(
                    'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
                    event.type === 'success' && 'bg-green-500/10 text-green-400',
                    event.type === 'error' && 'bg-red-500/10 text-red-400',
                    event.type === 'warning' && 'bg-orange-500/10 text-orange-400',
                    event.type === 'info' && 'bg-slate-500/10 text-slate-300',
                  )}
                >
                  {event.type === 'success' && <CircleCheckBig className="w-4 h-4" />}
                  {event.type === 'error' && <CircleX className="w-4 h-4" />}
                  {event.type === 'warning' && <Shield className="w-4 h-4" />}
                  {event.type === 'info' && <Clock className="w-4 h-4" />}
                </div>
                <div className="space-y-1">
                  <h3 className="text-sm font-medium text-[#F5F5F5]">{event.title}</h3>
                  <p className="text-xs text-[#A0A0A0]">{event.description}</p>
                </div>
              </div>

              <div className="flex items-center gap-6">
                <div className="flex gap-1.5 flex-wrap justify-end max-w-[320px]">
                  {event.agents.map((agent, index) => (
                    <div key={`${event.id}-${agent}-${index}`} className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-[#242424] text-[#A0A0A0]">
                      {agent}
                    </div>
                  ))}
                </div>
                <span className="text-[10px] text-[#5A5A5A] font-mono w-16 text-right">{event.time}</span>
              </div>
            </div>
          ))}
          {events.length === 0 && <div className="p-8 text-sm text-[#5A5A5A]">No activity entries found.</div>}
        </div>
      </div>
    </div>
  );
};
