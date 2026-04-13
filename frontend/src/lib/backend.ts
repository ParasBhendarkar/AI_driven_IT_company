import { useAuthStore } from '../store/authStore';
import type { AgentRole } from '../types/agent';
import type { Task, TaskEvent, QAResult, MemoryEntry, Escalation, Priority } from '../types/task';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

const toCamelTask = (task: any): Task => ({
  id: task.id ?? task.task_id,
  title: task.title,
  status: task.status,
  currentAgent: (task.currentAgent ?? task.current_agent ?? 'Orchestrator') as AgentRole,
  retryCount: task.retryCount ?? task.retry_count ?? 0,
  maxRetries: task.maxRetries ?? task.max_retries ?? 0,
  timeElapsed: task.timeElapsed ?? task.time_elapsed ?? formatRelative(task.createdAt ?? task.created_at),
  prNumber: task.prNumber ?? task.pr_number ?? undefined,
  progress: task.progress ?? 0,
  createdAt: task.createdAt ?? task.created_at ?? '',
  priority: (task.priority ?? 'Medium') as Priority,
  repo: task.repo,
  branch: task.branch,
  commitHash: task.commitHash ?? task.commit_hash ?? '',
});

export const apiUrl = (path: string) => `${BACKEND_URL}${path}`;

export const authHeaders = (includeJson = false): HeadersInit => {
  const token = useAuthStore.getState().accessToken;
  return {
    ...(includeJson ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
};

export const fetchJson = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(apiUrl(path), init);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
};

export const formatRelative = (value?: string | null) => {
  if (!value) {
    return 'just now';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  const diffSeconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (diffSeconds < 60) {
    return `${diffSeconds}s`;
  }

  const minutes = Math.floor(diffSeconds / 60);
  const seconds = diffSeconds % 60;
  if (minutes < 60) {
    return `${minutes}m ${seconds}s`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) {
    return `${hours}h ${remainingMinutes}m`;
  }

  const days = Math.floor(hours / 24);
  return `${days}d`;
};

export const normalizeTask = (task: any): Task => toCamelTask(task);

export const normalizeTaskList = (tasks: any[]): Task[] => tasks.map(toCamelTask);

export const normalizeEvent = (event: any): TaskEvent => ({
  id: event.id ?? `${event.timestamp}-${event.description}`,
  agent: (event.agent ?? 'Orchestrator') as AgentRole,
  description: event.description ?? '',
  timestamp: event.timestamp ?? '',
  payload: event.payload,
  type: event.type ?? 'info',
});

export const normalizeQAResult = (qa: any): QAResult | null => {
  if (!qa) {
    return null;
  }

  return {
    attempt: qa.attempt,
    status: qa.status,
    unitTests: {
      pass: qa.unitTests?.pass ?? qa.unit_tests?.pass ?? qa.unitTests?.pass_count ?? qa.unit_tests?.pass_count ?? 0,
      fail: qa.unitTests?.fail ?? qa.unit_tests?.fail ?? 0,
    },
    integrationTests: {
      pass:
        qa.integrationTests?.pass ??
        qa.integration_tests?.pass ??
        qa.integrationTests?.pass_count ??
        qa.integration_tests?.pass_count ??
        0,
      fail: qa.integrationTests?.fail ?? qa.integration_tests?.fail ?? 0,
    },
    coverage: qa.coverage ?? 0,
    latency: qa.latency ?? 'N/A',
    failures: (qa.failures ?? []).map((failure: any) => ({
      name: failure.name,
      error: failure.error,
      severity: failure.severity,
      location: failure.location,
    })),
  };
};

export const normalizeMemoryEntry = (entry: any): MemoryEntry => ({
  id: entry.id,
  content: entry.content,
  tags: entry.tags ?? [],
  sourceTaskId: entry.sourceTaskId ?? entry.source_task_id ?? '',
  date: entry.date,
  score: entry.score ?? undefined,
});

export const normalizeEscalation = (item: any): Escalation => ({
  id: item.id,
  taskId: item.taskId ?? item.task_id,
  reason: item.reason,
  recommendation: item.recommendation ?? undefined,
  type: item.type ?? item.escalation_type,
  findings: item.findings ?? undefined,
  taskTitle: item.taskTitle ?? item.task_title ?? '',
  createdAt: item.createdAt ?? item.created_at ?? '',
});
