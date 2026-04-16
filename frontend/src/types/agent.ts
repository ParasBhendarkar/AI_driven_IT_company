/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export type AgentRole = 'Developer' | 'QA' | 'CISO' | 'Critic' | 'DevOps' | 'CEO/Manager' | 'Orchestrator' | 'QA Planner' | 'QA Runner';

export interface Agent {
  id: string;
  role: AgentRole;
  status: 'ready' | 'busy' | 'error';
  color: string;
}
