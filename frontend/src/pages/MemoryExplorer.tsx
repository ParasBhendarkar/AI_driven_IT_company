/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Search, Trash2, Plus, TrendingUp, Tag } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer, XAxis, CartesianGrid } from 'recharts';
import { fetchJson, normalizeMemoryEntry } from '../lib/backend';
import type { MemoryEntry } from '../types/task';

export const MemoryExplorer: React.FC = () => {
  const [memories, setMemories] = useState<MemoryEntry[]>([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);

  const loadMemories = async () => {
    try {
      const data = await fetchJson<any[]>('/memory');
      setMemories(data.map(normalizeMemoryEntry));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load memories');
    }
  };

  useEffect(() => {
    void loadMemories();
  }, []);

  const handleSearch = async () => {
    try {
      const path = query.trim() ? `/memory/search?q=${encodeURIComponent(query)}&limit=20` : '/memory';
      const data = await fetchJson<any[]>(path);
      setMemories(data.map(normalizeMemoryEntry));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await fetchJson<void>(`/memory/${id}`, { method: 'DELETE' });
      setMemories((current) => current.filter((memory) => memory.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete memory');
    }
  };

  const handleAdd = async () => {
    const content = window.prompt('Add memory content');
    if (!content?.trim()) {
      return;
    }

    try {
      await fetchJson('/memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          tags: ['manual'],
          sourceTaskId: 'manual-entry',
        }),
      });
      await loadMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add memory');
    }
  };

  const growthData = useMemo(() => {
    const counts = new Map<string, number>();
    memories.forEach((memory) => {
      const date = new Date(memory.date);
      const key = Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleDateString(undefined, { weekday: 'short' });
      counts.set(key, (counts.get(key) ?? 0) + 1);
    });
    return Array.from(counts.entries()).map(([day, count]) => ({ day, count }));
  }, [memories]);

  const topTags = useMemo(() => {
    const counts = new Map<string, number>();
    memories.forEach((memory) => {
      memory.tags.forEach((tag) => counts.set(tag, (counts.get(tag) ?? 0) + 1));
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);
  }, [memories]);

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      <div className="flex items-center gap-4 bg-[#1A1A1A] border border-[#2A2A2A] p-4 rounded-xl shadow-xl">
        <div className="flex-1 relative">
          <Search className="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-[#5A5A5A]" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search memory semantically..."
            className="w-full bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg pl-12 pr-4 py-3 text-sm focus:border-indigo-500 outline-none transition-all"
          />
        </div>
        <button onClick={() => void handleSearch()} className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg px-8 py-3 text-sm font-medium transition-colors">
          Search
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-sm font-semibold text-[#F5F5F5] flex items-center gap-2">
            Recent Memory Entries
            <span className="bg-[#242424] text-[#A0A0A0] text-[10px] px-1.5 py-0.5 rounded">{memories.length}</span>
          </h2>
          <div className="space-y-3">
            {memories.map((memory) => (
              <div key={memory.id} className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-5 hover:border-[#383838] transition-all group">
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1 space-y-3">
                    <p className="text-sm text-[#F5F5F5] leading-relaxed">{memory.content}</p>
                    <div className="flex items-center gap-4 flex-wrap">
                      <div className="flex gap-1.5 flex-wrap">
                        {memory.tags.map((tag) => (
                          <span key={tag} className="text-[10px] bg-[#242424] text-[#A0A0A0] px-2 py-0.5 rounded-md border border-[#2A2A2A]">
                            {tag}
                          </span>
                        ))}
                      </div>
                      <span className="text-[10px] font-mono text-[#5A5A5A]">{memory.sourceTaskId}</span>
                      <span className="text-[10px] text-[#5A5A5A]">{memory.date}</span>
                    </div>
                  </div>
                  <button onClick={() => void handleDelete(memory.id)} className="text-[#5A5A5A] hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
            {memories.length === 0 && (
              <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-8 text-sm text-[#A0A0A0]">
                No memory entries yet.
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-6 space-y-8">
            <div className="space-y-6">
              <div className="space-y-1">
                <span className="text-[10px] text-[#5A5A5A] uppercase tracking-wider font-bold">Total Memories</span>
                <div className="text-3xl font-semibold text-[#F5F5F5]">{memories.length}</div>
              </div>

              <div className="space-y-3">
                <span className="text-[10px] text-[#5A5A5A] uppercase tracking-wider font-bold">Highest Match</span>
                <div className="bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg p-3 space-y-2">
                  <p className="text-xs text-[#A0A0A0] leading-tight">{memories[0]?.content || 'No semantic results yet'}</p>
                  <div className="flex items-center gap-2">
                    <TrendingUp className="w-3 h-3 text-green-400" />
                    <span className="text-[10px] text-green-400 font-bold">
                      {typeof memories[0]?.score === 'number' ? `${(memories[0].score * 100).toFixed(0)}% match` : 'Recent entry'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <span className="text-[10px] text-[#5A5A5A] uppercase tracking-wider font-bold">Growth</span>
                <div className="h-[120px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={growthData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#2A2A2A" vertical={false} />
                      <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fill: '#5A5A5A', fontSize: 10 }} dy={10} />
                      <Line type="monotone" dataKey="count" stroke="#6366F1" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="space-y-3">
                <span className="text-[10px] text-[#5A5A5A] uppercase tracking-wider font-bold">Top Tags</span>
                <div className="flex flex-wrap gap-2">
                  {topTags.map(([name, count]) => (
                    <div key={name} className="flex items-center gap-1.5 bg-[#242424] border border-[#2A2A2A] px-2 py-1 rounded-md">
                      <Tag className="w-3 h-3 text-[#5A5A5A]" />
                      <span className="text-xs text-[#A0A0A0]">{name}</span>
                      <span className="text-[10px] text-[#5A5A5A] font-mono">×{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <button onClick={() => void handleAdd()} className="w-full bg-transparent border border-[#2A2A2A] hover:border-[#383838] text-[#A0A0A0] rounded-lg py-3 text-sm font-medium transition-all flex items-center justify-center gap-2">
              <Plus className="w-4 h-4" />
              Add memory manually
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
