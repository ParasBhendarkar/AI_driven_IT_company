/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { AgentRole } from '../../types/agent';
import { cn } from '../../lib/utils';

interface AgentChipProps {
  role: AgentRole;
  className?: string;
}

export const agentColors: Record<AgentRole, string> = {
  Developer: '#6366F1',
  QA: '#14B8A6',
  CISO: '#F97316',
  Critic: '#A855F7',
  DevOps: '#22C55E',
  'CEO/Manager': '#EC4899',
  Orchestrator: '#64748B',
};

export const AgentChip: React.FC<AgentChipProps> = ({ role, className }) => {
  const color = agentColors[role];
  return (
    <div 
      className={cn('flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-medium border border-white/5', className)}
      style={{ backgroundColor: `${color}15`, color: color }}
    >
      <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {role}
    </div>
  );
};
