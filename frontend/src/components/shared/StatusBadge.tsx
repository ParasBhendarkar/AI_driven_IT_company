/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { TaskStatus } from '../../types/task';
import { cn } from '../../lib/utils';

interface StatusBadgeProps {
  status: TaskStatus;
  className?: string;
}

const statusConfig: Record<TaskStatus, { label: string; color: string }> = {
  pending: { label: 'Pending', color: 'text-slate-300 bg-slate-400/15' },
  running: { label: 'Running', color: 'text-blue-400 bg-blue-400/15' },
  retrying: { label: 'Retrying', color: 'text-amber-400 bg-amber-400/15' },
  qa_review: { label: 'QA Review', color: 'text-teal-300 bg-teal-400/15' },
  security_review: { label: 'Security Review', color: 'text-orange-300 bg-orange-400/15' },
  critic_review: { label: 'Critic Review', color: 'text-purple-300 bg-purple-400/15' },
  awaiting_deploy: { label: 'Awaiting Deploy', color: 'text-indigo-300 bg-indigo-400/15' },
  blocked: { label: 'Blocked', color: 'text-orange-400 bg-orange-400/15' },
  escalated: { label: 'Escalated', color: 'text-red-400 bg-red-400/15' },
  deployed: { label: 'Deployed', color: 'text-green-400 bg-green-400/15' },
  parallel_dev: { label: 'Parallel Dev', color: 'text-fuchsia-400 bg-fuchsia-400/15' },
  merging: { label: 'Merging', color: 'text-violet-400 bg-violet-400/15' },
  failed: { label: 'Failed', color: 'text-red-500 bg-red-500/15' },
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className }) => {
  const config = statusConfig[status];
  return (
    <span className={cn(
      'px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wider',
      config.color,
      className
    )}>
      {config.label}
    </span>
  );
};
