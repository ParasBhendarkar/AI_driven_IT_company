/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  GitBranch,
  GitCommit,
  Github,
  Shield,
  Brain,
  Play,
} from 'lucide-react';
import { StatusBadge } from '../components/shared/StatusBadge';
import { AgentChip, agentColors } from '../components/shared/AgentChip';
import { cn } from '../lib/utils';
import { authHeaders, fetchJson, normalizeEvent, normalizeMemoryEntry, normalizeQAResult, normalizeTask } from '../lib/backend';
import type { MemoryEntry, Task, TaskEvent } from '../types/task';

export const TaskDetail: React.FC = () => {
  const { id } = useParams();
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [expandedEvents, setExpandedEvents] = useState<string[]>([]);
  const [qaExpanded, setQaExpanded] = useState(true);
  const [overrideText, setOverrideText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!id) {
      return;
    }

    let isMounted = true;
    let source: EventSource | null = null;

    const loadTask = async () => {
      try {
        const response = await fetchJson<any>(`/tasks/${id}`);
        if (isMounted) {
          setTask(normalizeTask(response));
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load task');
        }
      }
    };

    void loadTask();

    source = new EventSource(`${import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'}/tasks/${id}/stream`);
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (isMounted) {
          setEvents((current) => [...current, normalizeEvent(payload)]);
        }
      } catch {
        // ignore keepalive/non-json frames
      }
    };
    source.addEventListener('status', (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data);
        if (!isMounted) {
          return;
        }
        setTask((current) =>
          current
            ? {
                ...current,
                status: payload.status,
                currentAgent: payload.current_agent ?? current.currentAgent,
                progress: payload.progress ?? current.progress,
                retryCount: payload.retry_count ?? current.retryCount,
              }
            : current,
        );
      } catch {
        // ignore malformed status frames
      }
    });
    source.onerror = () => {
      source?.close();
    };

    return () => {
      isMounted = false;
      source?.close();
    };
  }, [id]);

  const qaResult = useMemo(() => {
    const eventQa = events
      .map((event) => event.payload)
      .find((payload) => payload && payload.attempt && payload.unitTests);
    return normalizeQAResult(eventQa);
  }, [events]);

  const memoryHits = useMemo<MemoryEntry[]>(() => {
    const hits = events
      .flatMap((event) => (Array.isArray(event.payload?.memory_hits) ? event.payload.memory_hits : []))
      .map(normalizeMemoryEntry);
    return hits.slice(0, 3);
  }, [events]);

  const toggleEvent = (eventId: string) => {
    setExpandedEvents((prev) => (prev.includes(eventId) ? prev.filter((item) => item !== eventId) : [...prev, eventId]));
  };

  const handleOverride = async () => {
    if (!id || !overrideText.trim()) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      await fetchJson(`/tasks/${id}/override`, {
        method: 'PATCH',
        headers: authHeaders(true),
        body: JSON.stringify({
          action: overrideText,
          reason: 'Manual override from task detail',
          requestedBy: 'Founder',
        }),
      });
      setOverrideText('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send override');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAbort = async () => {
    if (!id) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      await fetchJson(`/tasks/${id}/abort`, {
        method: 'PATCH',
        headers: authHeaders(),
      });
      setTask((current) => (current ? { ...current, status: 'failed' } : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to abort task');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!task) {
    return (
      <div className="max-w-7xl mx-auto">
        <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-8 text-sm text-[#A0A0A0]">
          {error || 'Loading task...'}
        </div>
      </div>
    );
  }

  const canDeploy = task.status === 'awaiting_deploy';
  const liveEvents = events.length > 0 ? events : [];

  return (
    <div className="max-w-7xl mx-auto">
      <div className="flex items-center gap-4 mb-8">
        <Link to="/dashboard" className="text-[#5A5A5A] hover:text-[#A0A0A0] transition-colors">
          <ChevronRight className="w-5 h-5 rotate-180" />
        </Link>
        <h1 className="text-xl font-semibold text-[#F5F5F5]">{task.title}</h1>
        <StatusBadge status={task.status} />
        <AgentChip role={task.currentAgent} />
        {!!task.retryCount && (
          <span className="text-[10px] font-medium text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full">
            Attempt {task.retryCount} of {task.maxRetries ?? 0}
          </span>
        )}
      </div>

      {error && (
        <div className="mb-6 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-10 gap-8">
        <div className="lg:col-span-6 space-y-6">
          <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl overflow-hidden flex flex-col h-[600px]">
            <div className="p-4 border-b border-[#2A2A2A] bg-[#242424]/30 flex justify-between items-center">
              <span className="text-xs font-medium text-[#A0A0A0] uppercase tracking-wider">Live Feed</span>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
                <span className="text-[10px] text-indigo-400 font-medium uppercase">Live</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4 font-mono">
              {liveEvents.length === 0 ? (
                <div className="text-xs text-[#5A5A5A]">Waiting for task events...</div>
              ) : (
                liveEvents.map((event) => (
                  <div key={event.id} className="group">
                    <div className="flex items-start gap-3 text-xs">
                      <div
                        className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0"
                        style={{ backgroundColor: agentColors[event.agent] ?? '#64748B' }}
                      />
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center justify-between">
                          <span style={{ color: agentColors[event.agent] ?? '#64748B' }} className="font-bold">
                            [{event.agent}]
                          </span>
                          <span className="text-[#5A5A5A] text-[10px]">{event.timestamp}</span>
                        </div>
                        <div className="flex items-start gap-2">
                          <p className={cn('text-[#A0A0A0] leading-relaxed', event.type === 'error' && 'text-red-400')}>
                            {event.description}
                          </p>
                          {event.payload && (
                            <button
                              onClick={() => toggleEvent(event.id)}
                              className="text-[#5A5A5A] hover:text-[#A0A0A0] mt-0.5"
                            >
                              {expandedEvents.includes(event.id) ? (
                                <ChevronDown className="w-3 h-3" />
                              ) : (
                                <ChevronRight className="w-3 h-3" />
                              )}
                            </button>
                          )}
                        </div>
                        {expandedEvents.includes(event.id) && event.payload && (
                          <pre className="mt-2 p-3 bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg text-[10px] text-indigo-300 overflow-x-auto">
                            {JSON.stringify(event.payload, null, 2)}
                          </pre>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {qaResult && (
            <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl overflow-hidden">
              <button
                onClick={() => setQaExpanded(!qaExpanded)}
                className="w-full p-4 flex items-center justify-between hover:bg-[#242424]/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Shield className="w-4 h-4 text-teal-400" />
                  <span className="text-sm font-semibold">QA result — attempt {qaResult.attempt}</span>
                  <StatusBadge status={qaResult.status === 'pass' ? 'deployed' : 'failed'} />
                </div>
                {qaExpanded ? (
                  <ChevronDown className="w-4 h-4 text-[#5A5A5A]" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-[#5A5A5A]" />
                )}
              </button>

              {qaExpanded && (
                <div className="p-6 border-t border-[#2A2A2A] space-y-8">
                  <div className="grid grid-cols-2 gap-8">
                    <div className="space-y-4">
                      <div className="flex justify-between items-end">
                        <span className="text-xs text-[#A0A0A0]">Unit Tests</span>
                        <span className="text-xs font-mono text-[#F5F5F5]">
                          <span className="text-green-400">{qaResult.unitTests.pass}</span>
                          <span className="text-[#5A5A5A]"> / </span>
                          <span className="text-red-400">{qaResult.unitTests.fail}</span>
                        </span>
                      </div>
                    </div>
                    <div className="space-y-4">
                      <div className="flex justify-between items-end">
                        <span className="text-xs text-[#A0A0A0]">Integration Tests</span>
                        <span className="text-xs font-mono text-[#F5F5F5]">
                          <span className="text-green-400">{qaResult.integrationTests.pass}</span>
                          <span className="text-[#5A5A5A]"> / </span>
                          <span className="text-red-400">{qaResult.integrationTests.fail}</span>
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-8">
                    <div className="space-y-2">
                      <span className="text-[10px] text-[#5A5A5A] uppercase tracking-wider">Coverage</span>
                      <div className="text-xl font-semibold text-amber-400">{qaResult.coverage}%</div>
                    </div>
                    <div className="space-y-2">
                      <span className="text-[10px] text-[#5A5A5A] uppercase tracking-wider">Latency</span>
                      <div className="text-xl font-semibold text-green-400">{qaResult.latency}</div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <span className="text-[10px] text-[#5A5A5A] uppercase tracking-wider">Failures</span>
                    <div className="border border-[#2A2A2A] rounded-lg overflow-hidden">
                      <table className="w-full text-xs text-left">
                        <thead className="bg-[#242424]/50 text-[#5A5A5A]">
                          <tr>
                            <th className="px-4 py-2 font-medium">Test Name</th>
                            <th className="px-4 py-2 font-medium">Severity</th>
                            <th className="px-4 py-2 font-medium">Location</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#2A2A2A]">
                          {qaResult.failures.map((fail, index) => (
                            <tr key={`${fail.name}-${index}`} className="hover:bg-[#242424]/20">
                              <td className="px-4 py-3">
                                <div className="flex flex-col gap-0.5">
                                  <span className="text-[#F5F5F5] font-medium">{fail.name}</span>
                                  <span className="text-red-400 text-[10px] font-mono">{fail.error}</span>
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <span
                                  className={cn(
                                    'px-1.5 py-0.5 rounded text-[9px] font-bold uppercase',
                                    fail.severity === 'high'
                                      ? 'bg-red-500/10 text-red-400'
                                      : 'bg-amber-500/10 text-amber-400',
                                  )}
                                >
                                  {fail.severity}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-[#A0A0A0] font-mono text-[10px]">{fail.location}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="lg:col-span-4 space-y-6">
          <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-6 space-y-6">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-[#5A5A5A]">{task.id}</span>
              <span className="text-[10px] text-[#5A5A5A]">{task.createdAt}</span>
            </div>

            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-xs text-[#A0A0A0]">Priority</span>
                <span className="text-xs font-medium text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded">{task.priority}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-[#A0A0A0]">Repository</span>
                <div className="flex items-center gap-1.5 text-xs text-[#F5F5F5]">
                  <Github className="w-3.5 h-3.5" />
                  {task.repo}
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-[#A0A0A0]">Branch</span>
                <div className="flex items-center gap-1.5 text-xs text-[#F5F5F5]">
                  <GitBranch className="w-3.5 h-3.5" />
                  {task.branch}
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-[#A0A0A0]">PR</span>
                {task.prNumber ? (
                  <a href="#" className="flex items-center gap-1.5 text-xs text-blue-400 hover:underline">
                    <ExternalLink className="w-3.5 h-3.5" />#{task.prNumber}
                  </a>
                ) : (
                  <span className="text-xs text-[#5A5A5A]">Not opened yet</span>
                )}
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-[#A0A0A0]">Commit</span>
                <div className="flex items-center gap-1.5 text-xs text-[#5A5A5A] font-mono">
                  <GitCommit className="w-3.5 h-3.5" />
                  {task.commitHash || 'pending'}
                </div>
              </div>
            </div>
          </div>

          <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-6 space-y-6">
            <div className="space-y-3">
              <label className="text-[10px] text-[#5A5A5A] uppercase tracking-wider font-medium">Human Override</label>
              <textarea
                value={overrideText}
                onChange={(e) => setOverrideText(e.target.value)}
                placeholder="Type an instruction to inject..."
                className="w-full bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg p-3 text-xs text-[#F5F5F5] focus:border-indigo-500 outline-none min-h-[80px] resize-none"
              />
              <button
                onClick={handleOverride}
                disabled={!overrideText.trim() || isSubmitting}
                className="w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg py-2.5 text-xs font-medium transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5" />
                Resume with instruction
              </button>
            </div>

            <div className="pt-6 border-t border-[#2A2A2A] space-y-3">
              <button
                onClick={handleAbort}
                disabled={isSubmitting}
                className="w-full bg-transparent border border-[#2A2A2A] hover:border-red-500/50 hover:text-red-400 text-[#A0A0A0] rounded-lg py-2.5 text-xs font-medium transition-all disabled:opacity-50"
              >
                Abort task
              </button>
              <button
                disabled={!canDeploy}
                className={cn(
                  'w-full rounded-lg py-2.5 text-xs font-medium transition-all',
                  canDeploy
                    ? 'bg-indigo-600 hover:bg-indigo-500 text-white'
                    : 'bg-transparent border border-[#2A2A2A] text-[#5A5A5A] cursor-not-allowed opacity-40',
                )}
              >
                Approve deploy
              </button>
            </div>
          </div>

          <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[#2A2A2A] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Brain className="w-4 h-4 text-purple-400" />
                <span className="text-sm font-semibold">Memory Hits</span>
              </div>
              <span className="text-[10px] font-mono text-[#5A5A5A]">{memoryHits.length} found</span>
            </div>
            <div className="p-4 space-y-4">
              {memoryHits.length === 0 ? (
                <div className="text-xs text-[#5A5A5A]">No memory hits published yet.</div>
              ) : (
                memoryHits.map((memory) => (
                  <div key={memory.id} className="space-y-2">
                    <div className="flex justify-between items-start">
                      <p className="text-xs text-[#A0A0A0] leading-relaxed">{memory.content}</p>
                      <span className="text-[10px] font-mono text-indigo-400">
                        {typeof memory.score === 'number' ? `${(memory.score * 100).toFixed(0)}%` : ''}
                      </span>
                    </div>
                    <div className="flex gap-1.5">
                      {memory.tags.map((tag) => (
                        <span key={tag} className="text-[9px] bg-[#242424] text-[#5A5A5A] px-1.5 py-0.5 rounded">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
