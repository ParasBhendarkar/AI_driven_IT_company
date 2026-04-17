/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { AgentRole } from './agent';

export type TaskStatus =
  | 'pending'
  | 'running'
  | 'retrying'
  | 'qa_review'
  | 'security_review'
  | 'critic_review'
  | 'awaiting_deploy'
  | 'blocked'
  | 'escalated'
  | 'deployed'
  | 'parallel_dev'
  | 'merging'
  | 'failed';
export type Priority = 'Low' | 'Medium' | 'High' | 'Critical';
export type RequestType = 'task' | 'module';
 
export interface SubTask {
  id: string;
  title: string;
  description: string;
  branch: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  pr_number?: number;
}
 
export interface PullRequestSummary {
  pr_number: number;
  branch: string;
  title: string;
  status: 'open' | 'merged' | 'failed';
  sub_task_id?: string;
}

export interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  currentAgent: AgentRole;
  retryCount?: number;
  maxRetries?: number;
  timeElapsed: string;
  prNumber?: number;
  progress: number;
  createdAt: string;
  priority: Priority;
  repo: string;
  branch: string;
  commitHash: string;
  requestType?: RequestType;
  tasksToBuild?: SubTask[];
  pullRequests?: PullRequestSummary[];
  mergeCommitHash?: string;
}

export interface TaskEvent {
  id: string;
  agent: AgentRole;
  description: string;
  timestamp: string;
  payload?: any;
  type?: 'info' | 'error' | 'success' | 'warning';
}

export interface QAResult {
  attempt: number;
  status: 'pass' | 'fail';
  unitTests: { pass: number; fail: number };
  integrationTests: { pass: number; fail: number };
  coverage: number;
  latency: string;
  failures: Array<{
    name: string;
    error: string;
    severity: 'high' | 'medium' | 'low';
    location: string;
  }>;
}

export interface MemoryEntry {
  id: string;
  content: string;
  tags: string[];
  sourceTaskId: string;
  date: string;
  score?: number;
}

export interface Escalation {
  id: string;
  taskId: string;
  reason: string;
  recommendation?: string;
  type: 'max_retries' | 'security_block';
  findings?: string;
  taskTitle?: string;
  createdAt?: string;
}
