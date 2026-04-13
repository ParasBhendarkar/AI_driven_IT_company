/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Task, TaskEvent, QAResult, MemoryEntry, Escalation } from './types/task';

export const MOCK_TASKS: Task[] = [
  {
    id: 'TASK-0042',
    title: 'Implement anomaly detection API with IsolationForest',
    status: 'retrying',
    currentAgent: 'Developer',
    retryCount: 2,
    maxRetries: 3,
    timeElapsed: '4m 32s',
    prNumber: 42,
    progress: 65,
    createdAt: '2 hours ago',
    priority: 'High',
    repo: 'org/incident-dashboard',
    branch: 'feat/anomaly-api',
    commitHash: 'a1b2c3d'
  },
  {
    id: 'TASK-0039',
    title: 'Refactor audit logging for SQL injection prevention',
    status: 'blocked',
    currentAgent: 'CISO',
    timeElapsed: '12m 10s',
    progress: 40,
    createdAt: '5 hours ago',
    priority: 'Critical',
    repo: 'org/auth-service',
    branch: 'fix/sql-injection',
    commitHash: 'e5f6g7h'
  },
  {
    id: 'TASK-0045',
    title: 'Optimize Redis cache TTL for session management',
    status: 'running',
    currentAgent: 'DevOps',
    timeElapsed: '1m 45s',
    progress: 85,
    createdAt: '15 minutes ago',
    priority: 'Medium',
    repo: 'org/core-api',
    branch: 'perf/redis-ttl',
    commitHash: 'i9j0k1l'
  },
  {
    id: 'TASK-0041',
    title: 'Add unit tests for payment webhook edge cases',
    status: 'deployed',
    currentAgent: 'QA',
    timeElapsed: '45m 20s',
    progress: 100,
    createdAt: '3 hours ago',
    priority: 'High',
    repo: 'org/payments',
    branch: 'test/webhooks',
    commitHash: 'm2n3o4p'
  },
  {
    id: 'TASK-0038',
    title: 'Migrate CI pipeline to GitHub Actions',
    status: 'failed',
    currentAgent: 'DevOps',
    timeElapsed: '1h 5m',
    progress: 90,
    createdAt: '8 hours ago',
    priority: 'Low',
    repo: 'org/infra',
    branch: 'migration/gha',
    commitHash: 'q5r6s7t'
  },
  {
    id: 'TASK-0040',
    title: 'Update documentation for API v2 release',
    status: 'escalated',
    currentAgent: 'Critic',
    timeElapsed: '22m 15s',
    progress: 30,
    createdAt: '4 hours ago',
    priority: 'Medium',
    repo: 'org/docs',
    branch: 'docs/v2-update',
    commitHash: 'u8v9w0x'
  }
];

export const MOCK_EVENTS: TaskEvent[] = [
  { id: '1', agent: 'Orchestrator', description: 'Task received. Loading memory context... (2 hits found)', timestamp: '10:00:01' },
  { id: '2', agent: 'Developer', description: 'Reading repository structure via GitHub tool...', timestamp: '10:00:15' },
  { id: '3', agent: 'Developer', description: 'Generated anomaly.py (143 lines). Opening PR #42...', timestamp: '10:02:30' },
  { id: '4', agent: 'QA', description: 'Running 26 unit tests + 8 integration tests...', timestamp: '10:02:45' },
  { id: '5', agent: 'QA', description: 'FAILED — 2 tests failed. NullPointerException at line 42.', timestamp: '10:03:20', type: 'error' },
  { id: '6', agent: 'Orchestrator', description: 'Retry 1/3 — injecting error context into Dev prompt...', timestamp: '10:03:30' },
  { id: '7', agent: 'Developer', description: 'Applying fix: added null guard at anomaly.py:42...', timestamp: '10:04:10' },
  { id: '8', agent: 'QA', description: 'Running tests again...', timestamp: '10:04:20', payload: { unit: { pass: 24, fail: 2 }, integration: { pass: 8, fail: 0 } } },
  { id: '9', agent: 'QA', description: 'FAILED — single-point series edge case.', timestamp: '10:05:05', type: 'error' },
  { id: '10', agent: 'Orchestrator', description: 'Retry 2/3 — injecting memory hint from TASK-0031...', timestamp: '10:05:15' }
];

export const MOCK_QA_RESULT: QAResult = {
  attempt: 2,
  status: 'fail',
  unitTests: { pass: 24, fail: 2 },
  integrationTests: { pass: 8, fail: 0 },
  coverage: 81,
  latency: '187ms',
  failures: [
    { name: 'test_isolation_forest_single_point', error: 'ValueError: n_samples=1 must be >= 2', severity: 'high', location: 'anomaly.py:42' },
    { name: 'test_null_input_handling', error: 'NullPointerException', severity: 'medium', location: 'anomaly.py:15' }
  ]
};

export const MOCK_ESCALATIONS: Escalation[] = [
  {
    id: 'ESC-001',
    taskId: 'TASK-0042',
    type: 'max_retries',
    reason: 'Escalated — 5 attempts failed',
    recommendation: 'Root cause: MinMaxScaler clipping values to 0. Suggested fix: replace with RobustScaler.'
  },
  {
    id: 'ESC-002',
    taskId: 'TASK-0039',
    type: 'security_block',
    reason: 'Security block — critical finding',
    findings: 'CWE-89 SQL Injection at audit_logger.py:31 — use parameterised query'
  }
];

export const MOCK_MEMORIES: MemoryEntry[] = [
  { id: 'M1', content: 'IsolationForest requires n_samples ≥ 2 — use z-score fallback for short series', tags: ['anomaly', 'python'], sourceTaskId: 'TASK-0042', date: '2024-03-20', score: 0.91 },
  { id: 'M2', content: 'MinMaxScaler clips outlier data — prefer RobustScaler for metric series', tags: ['preprocessing', 'ml'], sourceTaskId: 'TASK-0042', date: '2024-03-20', score: 0.87 },
  { id: 'M3', content: 'Parameterised queries required — f-string SQL causes CWE-89', tags: ['security', 'sql'], sourceTaskId: 'TASK-0039', date: '2024-03-19' },
  { id: 'M4', content: 'Redis TTL 60s sufficient for anomaly API access pattern', tags: ['performance', 'redis'], sourceTaskId: 'TASK-0038', date: '2024-03-18' },
  { id: 'M5', content: 'GitHub Actions pipeline takes ~3m — add timeout 10m to workflow', tags: ['devops', 'ci'], sourceTaskId: 'TASK-0037', date: '2024-03-17' },
  { id: 'M6', content: 'p95 latency under 200ms achievable with connection pooling', tags: ['performance', 'api'], sourceTaskId: 'TASK-0036', date: '2024-03-16' }
];

export const ACTIVITY_DATA = [
  { day: 'Mon', completed: 12, escalated: 2 },
  { day: 'Tue', completed: 15, escalated: 1 },
  { day: 'Wed', completed: 8, escalated: 4 },
  { day: 'Thu', completed: 18, escalated: 0 },
  { day: 'Fri', completed: 14, escalated: 2 },
  { day: 'Sat', completed: 5, escalated: 1 },
  { day: 'Sun', completed: 7, escalated: 0 }
];

export const AGENT_CALLS = [
  { id: 1, agent: 'Developer', action: 'generate_code', tokens: 4200, latency: '12.4s', timestamp: '10:00:15' },
  { id: 2, agent: 'QA', action: 'run_tests', tokens: 1500, latency: '45.2s', timestamp: '10:02:45' },
  { id: 3, agent: 'Orchestrator', action: 'analyze_error', tokens: 800, latency: '2.1s', timestamp: '10:03:30' },
  { id: 4, agent: 'Developer', action: 'apply_fix', tokens: 3100, latency: '8.7s', timestamp: '10:04:10' },
  { id: 5, agent: 'QA', action: 'run_tests', tokens: 1600, latency: '48.1s', timestamp: '10:04:20' },
  { id: 6, agent: 'Orchestrator', action: 'retrieve_memory', tokens: 3000, latency: '1.5s', timestamp: '10:05:15' }
];
