/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Activity, Database, Cpu, DollarSign, CircleAlert } from 'lucide-react';
import { StatusBadge } from '../components/shared/StatusBadge';
import { AgentChip } from '../components/shared/AgentChip';
import { Link } from 'react-router-dom';
import { cn } from '../lib/utils';
import { TaskCreateModal, TaskFormData } from '../components/tasks/TaskCreateModal';
import { authHeaders, fetchJson, normalizeTaskList } from '../lib/backend';
import type { Task } from '../types/task';

interface ActivityStats {
  tasksThisWeek: number;
  avgRetries: number;
  cisoBlocks: number;
  memoryWrites: number;
  chartData: Array<{ day: string; completed: number; escalated: number }>;
}

export const Dashboard: React.FC = () => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [stats, setStats] = useState<ActivityStats | null>(null);
  const [inboxCount, setInboxCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const loadDashboard = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [taskData, statsData, inboxData] = await Promise.all([
        fetchJson<any[]>('/tasks'),
        fetchJson<ActivityStats>('/activity/stats'),
        fetchJson<any[]>('/inbox'),
      ]);

      setTasks(normalizeTaskList(taskData));
      setStats(statsData);
      setInboxCount(inboxData.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const handleCreateTask = async (taskData: TaskFormData) => {
    setIsCreating(true);
    setError(null);

    try {
      await fetchJson('/tasks', {
        method: 'POST',
        headers: authHeaders(true),
        body: JSON.stringify(taskData),
      });

      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create task');
      throw err;
    } finally {
      setIsCreating(false);
    }
  };

  const activeTasks = useMemo(
    () => tasks.filter((task) => task.status !== 'deployed' && task.status !== 'failed'),
    [tasks],
  );

  const completedToday = useMemo(
    () =>
      tasks.filter((task) => {
        if (task.status !== 'deployed' || !task.createdAt) {
          return false;
        }

        const created = new Date(task.createdAt);
        const now = new Date();
        return created.toDateString() === now.toDateString();
      }).length,
    [tasks],
  );

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      <section className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-4 shadow-xl">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="flex-1 bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg px-4 py-3 text-sm text-left text-[#5A5A5A] hover:border-indigo-500/50 hover:text-[#A0A0A0] transition-all"
          >
            Describe a task for your AI team...
          </button>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg px-6 py-3 text-sm font-medium transition-all flex items-center gap-2 disabled:opacity-50"
            disabled={isCreating}
          >
            <Plus className="w-4 h-4" />
            {isCreating ? 'Creating...' : 'New Task'}
          </button>
        </div>
      </section>

      <TaskCreateModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSubmit={handleCreateTask}
      />

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          {
            label: 'Active tasks',
            value: String(activeTasks.length),
            subtitle: 'running now',
            icon: Cpu,
            color: 'text-blue-400',
          },
          {
            label: 'Completed today',
            value: String(completedToday),
            subtitle: 'since midnight',
            icon: Activity,
            color: 'text-green-400',
          },
          {
            label: 'Avg retries',
            value: stats ? String(stats.avgRetries) : '--',
            subtitle: 'per task',
            icon: Database,
            color: 'text-amber-400',
          },
          {
            label: 'Escalations',
            value: String(inboxCount),
            subtitle: 'awaiting you',
            icon: CircleAlert,
            color: 'text-red-400',
            alert: true,
          },
        ].map((stat, i) => (
          <div key={i} className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-5">
            <div className="flex justify-between items-start mb-2">
              <span className="text-xs font-medium text-[#A0A0A0] uppercase tracking-wider">{stat.label}</span>
              <stat.icon className={cn('w-4 h-4', stat.color)} />
            </div>
            <div className="flex items-baseline gap-2">
              <span className={cn('text-2xl font-semibold', stat.alert ? 'text-red-400' : 'text-[#F5F5F5]')}>
                {stat.value}
              </span>
              <span className="text-[10px] text-[#5A5A5A]">{stat.subtitle}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-sm font-semibold text-[#F5F5F5] flex items-center gap-2">
            Active Tasks
            <span className="bg-[#242424] text-[#A0A0A0] text-[10px] px-1.5 py-0.5 rounded">
              {activeTasks.length}
            </span>
          </h2>

          {isLoading ? (
            <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-8 text-sm text-[#A0A0A0]">
              Loading tasks...
            </div>
          ) : activeTasks.length === 0 ? (
            <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-8 text-sm text-[#A0A0A0]">
              No active tasks yet. Create one to start the pipeline.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {activeTasks.map((task) => (
                <Link
                  key={task.id}
                  to={`/tasks/${task.id}`}
                  className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-5 hover:border-[#383838] transition-all group"
                >
                  <div className="flex justify-between items-start mb-4">
                    <div className="space-y-1">
                      <h3
                        className="text-sm font-medium text-[#F5F5F5] line-clamp-1 group-hover:text-indigo-400 transition-colors"
                        title={task.title}
                      >
                        {task.title}
                      </h3>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-[#5A5A5A]">{task.id}</span>
                        <span className="text-[10px] text-[#5A5A5A]">•</span>
                        <span className="text-[10px] text-[#5A5A5A]">{task.timeElapsed}</span>
                      </div>
                    </div>
                    <StatusBadge status={task.status} />
                  </div>

                  <div className="flex items-center justify-between mb-4">
                    <AgentChip role={task.currentAgent} />
                    {typeof task.retryCount === 'number' && task.retryCount > 0 && (
                      <span className="text-[10px] font-medium text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full">
                        Attempt {task.retryCount} of {task.maxRetries ?? 0}
                      </span>
                    )}
                    {task.prNumber && <span className="text-[10px] font-medium text-blue-400">#{task.prNumber} open</span>}
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex justify-between text-[10px] text-[#5A5A5A]">
                      <span>Progress</span>
                      <span>{task.progress}%</span>
                    </div>
                    <div className="w-full h-1 bg-[#0F0F0F] rounded-full overflow-hidden">
                      <div
                        className={cn(
                          'h-full transition-all duration-500',
                          task.status === 'deployed'
                            ? 'bg-green-500'
                            : task.status === 'failed'
                              ? 'bg-red-500'
                              : task.status === 'retrying'
                                ? 'bg-amber-500'
                                : task.status === 'blocked'
                                  ? 'bg-orange-500'
                                  : task.status === 'escalated'
                                    ? 'bg-red-600'
                                    : 'bg-indigo-500',
                        )}
                        style={{ width: `${task.progress}%` }}
                      />
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-6">
          <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-6">
            <h2 className="text-sm font-semibold text-[#F5F5F5] mb-6 flex items-center gap-2">
              System Health
              <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
            </h2>

            <div className="space-y-6">
              <div className="space-y-3">
                <span className="text-[10px] font-medium text-[#5A5A5A] uppercase tracking-wider">Agent Status</span>
                <div className="space-y-2.5">
                  {['Developer', 'QA', 'CISO', 'Critic', 'DevOps'].map((role) => (
                    <div key={role} className="flex items-center justify-between">
                      <span className="text-xs text-[#A0A0A0]">{role}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-[#5A5A5A]">ready</span>
                        <div className="w-1.5 h-1.5 bg-green-500 rounded-full" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="pt-6 border-t border-[#2A2A2A] space-y-4">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <Activity className="w-3.5 h-3.5 text-[#5A5A5A]" />
                    <span className="text-xs text-[#A0A0A0]">Queue depth</span>
                  </div>
                  <span className="text-xs font-medium text-[#F5F5F5]">{activeTasks.length} active</span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <Database className="w-3.5 h-3.5 text-[#5A5A5A]" />
                    <span className="text-xs text-[#A0A0A0]">Memory writes</span>
                  </div>
                  <span className="text-xs font-medium text-[#F5F5F5]">{stats?.memoryWrites ?? '--'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <DollarSign className="w-3.5 h-3.5 text-[#5A5A5A]" />
                    <span className="text-xs text-[#A0A0A0]">LLM cost</span>
                  </div>
                  <span className="text-xs font-medium text-[#F5F5F5]">Tracked in agent logs</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
