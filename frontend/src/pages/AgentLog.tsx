/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ChevronRight, Terminal, Settings, Database, Search, Maximize2, Minimize2 } from 'lucide-react';
import { AgentChip } from '../components/shared/AgentChip';
import { cn } from '../lib/utils';
import { AgentRole } from '../types/agent';
import { fetchJson } from '../lib/backend';

interface AgentCallRow {
  id: string;
  agent: AgentRole;
  action: string;
  inputPayload: Record<string, unknown> | null;
  outputPayload: Record<string, unknown> | null;
  tokensUsed: number;
  latencySeconds: number;
  costUsd: number;
  status: string;
  createdAt: string;
}

export const AgentLog: React.FC = () => {
  const { id } = useParams();
  const [calls, setCalls] = useState<AgentCallRow[]>([]);
  const [activeFilter, setActiveFilter] = useState<AgentRole | 'all'>('all');
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'prompt' | 'response'>('prompt');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      return;
    }

    const load = async () => {
      try {
        const data = await fetchJson<AgentCallRow[]>(`/tasks/${id}/log`);
        setCalls(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load logs');
      }
    };

    void load();
  }, [id]);

  const filters: (AgentRole | 'all')[] = ['all', 'Developer', 'QA', 'CISO', 'Critic', 'DevOps', 'Orchestrator'];

  const filteredCalls = useMemo(
    () =>
      calls.filter((call) => {
        const matchesFilter = activeFilter === 'all' || call.agent === activeFilter;
        const haystack = `${call.agent} ${call.action} ${JSON.stringify(call.inputPayload ?? {})} ${JSON.stringify(
          call.outputPayload ?? {},
        )}`.toLowerCase();
        const matchesQuery = haystack.includes(query.toLowerCase());
        return matchesFilter && matchesQuery;
      }),
    [activeFilter, calls, query],
  );

  const totals = useMemo(
    () => ({
      calls: calls.length,
      tokens: calls.reduce((sum, call) => sum + (call.tokensUsed ?? 0), 0),
      cost: calls.reduce((sum, call) => sum + (call.costUsd ?? 0), 0),
    }),
    [calls],
  );

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to={`/tasks/${id}`} className="text-[#5A5A5A] hover:text-[#A0A0A0] transition-colors">
            <ChevronRight className="w-5 h-5 rotate-180" />
          </Link>
          <h1 className="text-xl font-semibold text-[#F5F5F5]">Agent Logs</h1>
          <span className="text-xs font-mono text-[#5A5A5A]">{id}</span>
        </div>
        <div className="flex items-center gap-4 text-[10px] text-[#5A5A5A] font-mono">
          <span className="flex items-center gap-1.5">
            <Terminal className="w-3 h-3" /> {totals.calls} calls
          </span>
          <span className="flex items-center gap-1.5">
            <Database className="w-3 h-3" /> {totals.tokens.toLocaleString()} tokens
          </span>
          <span className="flex items-center gap-1.5 text-indigo-400">
            <Settings className="w-3 h-3" /> ${totals.cost.toFixed(2)}
          </span>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between bg-[#1A1A1A] border border-[#2A2A2A] p-2 rounded-xl">
        <div className="flex gap-1 flex-wrap">
          {filters.map((filter) => (
            <button
              key={filter}
              onClick={() => setActiveFilter(filter)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
                activeFilter === filter
                  ? 'bg-indigo-600 text-white'
                  : 'text-[#A0A0A0] hover:text-[#F5F5F5] hover:bg-[#242424]',
              )}
            >
              {filter}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-[#5A5A5A]" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search logs..."
            className="bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg pl-9 pr-3 py-1.5 text-xs outline-none focus:border-indigo-500 w-48"
          />
        </div>
      </div>

      <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl overflow-hidden">
        <table className="w-full text-xs text-left">
          <thead className="bg-[#242424]/50 text-[#5A5A5A] border-b border-[#2A2A2A]">
            <tr>
              <th className="px-6 py-4 font-medium">Agent</th>
              <th className="px-6 py-4 font-medium">Action</th>
              <th className="px-6 py-4 font-medium">Tokens</th>
              <th className="px-6 py-4 font-medium">Latency</th>
              <th className="px-6 py-4 font-medium">Timestamp</th>
              <th className="px-6 py-4 font-medium text-right">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2A2A2A]">
            {filteredCalls.map((call) => (
              <React.Fragment key={call.id}>
                <tr
                  className={cn('hover:bg-[#242424]/20 transition-colors cursor-pointer', expandedRow === call.id && 'bg-[#242424]/40')}
                  onClick={() => setExpandedRow(expandedRow === call.id ? null : call.id)}
                >
                  <td className="px-6 py-4">
                    <AgentChip role={call.agent} />
                  </td>
                  <td className="px-6 py-4 font-mono text-indigo-300">{call.action}</td>
                  <td className="px-6 py-4 text-[#A0A0A0]">{(call.tokensUsed ?? 0).toLocaleString()}</td>
                  <td className="px-6 py-4 text-[#A0A0A0]">{(call.latencySeconds ?? 0).toFixed(1)}s</td>
                  <td className="px-6 py-4 text-[#5A5A5A]">{new Date(call.createdAt).toLocaleString()}</td>
                  <td className="px-6 py-4 text-right">
                    {expandedRow === call.id ? <Minimize2 className="w-4 h-4 inline" /> : <Maximize2 className="w-4 h-4 inline" />}
                  </td>
                </tr>
                {expandedRow === call.id && (
                  <tr>
                    <td colSpan={6} className="px-6 py-6 bg-[#0F0F0F]/50">
                      <div className="space-y-4">
                        <div className="flex gap-4 border-b border-[#2A2A2A]">
                          {['prompt', 'response'].map((tab) => (
                            <button
                              key={tab}
                              onClick={(e) => {
                                e.stopPropagation();
                                setActiveTab(tab as 'prompt' | 'response');
                              }}
                              className={cn(
                                'pb-2 text-[10px] font-bold uppercase tracking-wider transition-all border-b-2',
                                activeTab === tab
                                  ? 'border-indigo-500 text-indigo-400'
                                  : 'border-transparent text-[#5A5A5A] hover:text-[#A0A0A0]',
                              )}
                            >
                              {tab}
                            </button>
                          ))}
                        </div>
                        <pre className="bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg p-4 font-mono text-[11px] leading-relaxed overflow-x-auto max-h-[400px] text-indigo-200/80">
                          {JSON.stringify(activeTab === 'prompt' ? call.inputPayload : call.outputPayload, null, 2)}
                        </pre>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
            {filteredCalls.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-[#5A5A5A]">
                  No log entries found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
