/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';
import { AlertCircle, Shield, Play, XCircle, Brain } from 'lucide-react';
import { cn } from '../lib/utils';
import { authHeaders, fetchJson, normalizeEscalation } from '../lib/backend';
import type { Escalation } from '../types/task';

export const Inbox: React.FC = () => {
  const [items, setItems] = useState<Escalation[]>([]);
  const [instructions, setInstructions] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const loadInbox = async () => {
    try {
      const data = await fetchJson<any[]>('/inbox');
      setItems(data.map(normalizeEscalation));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load inbox');
    }
  };

  useEffect(() => {
    void loadInbox();
  }, []);

  const handleResume = async (taskId: string) => {
    const action = instructions[taskId]?.trim();
    if (!action) {
      return;
    }

    try {
      await fetchJson(`/tasks/${taskId}/override`, {
        method: 'PATCH',
        headers: authHeaders(true),
        body: JSON.stringify({
          action,
          reason: 'Manual inbox override',
          requestedBy: 'Founder',
        }),
      });
      await loadInbox();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resume task');
    }
  };

  const handleAbort = async (taskId: string) => {
    try {
      await fetchJson(`/tasks/${taskId}/abort`, {
        method: 'PATCH',
        headers: authHeaders(),
      });
      await loadInbox();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to abort task');
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-[#F5F5F5]">Escalation Inbox</h1>
          <span className="bg-red-500 text-white text-[10px] px-2 py-0.5 rounded-full font-bold">
            {items.length} awaiting
          </span>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="space-y-6">
        {items.length === 0 ? (
          <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-8 text-sm text-[#A0A0A0]">
            No unresolved escalations right now.
          </div>
        ) : (
          items.map((esc) => {
            const isSecurity = esc.type === 'security_block';

            return (
              <div
                key={esc.id}
                className={cn(
                  'bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl overflow-hidden shadow-xl flex',
                  isSecurity ? 'border-l-4 border-l-orange-500 pb-6' : 'border-l-4 border-l-red-500',
                )}
              >
                <div className="p-8 flex-1 space-y-6">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-[#5A5A5A]">{esc.taskId}</span>
                      <span className="text-[10px] text-[#5A5A5A]">•</span>
                      <span className="text-[10px] text-[#5A5A5A]">{esc.createdAt || 'recently'}</span>
                    </div>
                    <h2 className="text-lg font-semibold text-[#F5F5F5]">{esc.taskTitle || esc.taskId}</h2>
                    <div className="flex items-center gap-2">
                      {isSecurity ? (
                        <Shield className="w-3.5 h-3.5 text-orange-400" />
                      ) : (
                        <AlertCircle className="w-3.5 h-3.5 text-red-400" />
                      )}
                      <span className={cn('text-xs font-medium', isSecurity ? 'text-orange-400' : 'text-red-400')}>
                        {esc.reason}
                      </span>
                    </div>
                  </div>

                  {esc.recommendation && (
                    <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-4 space-y-2">
                      <div className="flex items-center gap-2 text-purple-400">
                        <Brain className="w-4 h-4" />
                        <span className="text-xs font-bold uppercase tracking-wider">Recommendation</span>
                      </div>
                      <p className="text-sm text-purple-200/80 leading-relaxed">{esc.recommendation}</p>
                    </div>
                  )}

                  {esc.findings && (
                    <div className="bg-orange-500/10 border border-orange-500/20 rounded-lg p-4 space-y-2">
                      <div className="flex items-center gap-2 text-orange-400">
                        <Shield className="w-4 h-4" />
                        <span className="text-xs font-bold uppercase tracking-wider">CISO Findings</span>
                      </div>
                      <p className="text-sm text-orange-200/80 leading-relaxed font-mono">{esc.findings}</p>
                    </div>
                  )}

                  <div className="pt-4 space-y-4">
                    <textarea
                      value={instructions[esc.taskId] ?? ''}
                      onChange={(e) =>
                        setInstructions((current) => ({ ...current, [esc.taskId]: e.target.value }))
                      }
                      placeholder="Type an instruction to inject..."
                      className="w-full bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg p-4 text-sm text-[#F5F5F5] focus:border-indigo-500 outline-none min-h-[100px] resize-none"
                    />
                    <div className="flex gap-3">
                      <button
                        onClick={() => void handleResume(esc.taskId)}
                        className="flex-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg py-3 text-sm font-medium transition-all flex items-center justify-center gap-2"
                      >
                        <Play className="w-4 h-4" />
                        Resume with instruction
                      </button>
                      <button
                        onClick={() => void handleAbort(esc.taskId)}
                        className="px-6 bg-transparent border border-[#2A2A2A] hover:border-red-500/50 hover:text-red-400 text-[#A0A0A0] rounded-lg py-3 text-sm font-medium transition-all flex items-center gap-2"
                      >
                        <XCircle className="w-4 h-4" />
                        Abort
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
