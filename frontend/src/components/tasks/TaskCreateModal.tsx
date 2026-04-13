/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, GitBranch, Github, Loader2, Plus, Trash2, X } from 'lucide-react';
import { useGitHubStore } from '../../store/githubStore';
import { cn } from '../../lib/utils';

interface TaskCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (taskData: TaskFormData) => void | Promise<void>;
}

export interface TaskFormData {
  title: string;
  description: string;
  repo: string;
  branch: string;
  priority: 'Low' | 'Medium' | 'High' | 'Critical';
  acceptance_criteria: string[];
  context_refs: string[];
}

const INITIAL_FORM_DATA: TaskFormData = {
  title: '',
  description: '',
  repo: '',
  branch: '',
  priority: 'Medium',
  acceptance_criteria: [''],
  context_refs: [],
};

const getErrorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

export const TaskCreateModal: React.FC<TaskCreateModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
}) => {
  const repositories = useGitHubStore((state) => state.repositories);
  const branches = useGitHubStore((state) => state.branches);
  const isLoadingRepos = useGitHubStore((state) => state.isLoadingRepos);
  const isLoadingBranches = useGitHubStore((state) => state.isLoadingBranches);
  const githubError = useGitHubStore((state) => state.error);
  const fetchRepositories = useGitHubStore((state) => state.fetchRepositories);
  const fetchBranches = useGitHubStore((state) => state.fetchBranches);

  const [formData, setFormData] = useState<TaskFormData>(INITIAL_FORM_DATA);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const selectedRepository = useMemo(
    () => repositories.find((repository) => repository.full_name === formData.repo),
    [formData.repo, repositories],
  );

  useEffect(() => {
    if (isOpen && repositories.length === 0) {
      void fetchRepositories().catch(() => undefined);
    }
  }, [fetchRepositories, isOpen, repositories.length]);

  useEffect(() => {
    if (isOpen && formData.repo) {
      void fetchBranches(formData.repo).catch(() => undefined);
    }
  }, [fetchBranches, formData.repo, isOpen]);

  useEffect(() => {
    if (!formData.repo) {
      return;
    }

    if (!formData.branch && selectedRepository?.default_branch) {
      setFormData((prev) => ({ ...prev, branch: selectedRepository.default_branch }));
      return;
    }

    const loadedBranches = branches[formData.repo];

    if (
      loadedBranches &&
      formData.branch &&
      !loadedBranches.some((branch) => branch.name === formData.branch) &&
      selectedRepository?.default_branch
    ) {
      setFormData((prev) => ({ ...prev, branch: selectedRepository.default_branch }));
    }
  }, [branches, formData.branch, formData.repo, selectedRepository]);

  const handleAddCriteria = () => {
    setFormData((prev) => ({
      ...prev,
      acceptance_criteria: [...prev.acceptance_criteria, ''],
    }));
  };

  const handleRemoveCriteria = (index: number) => {
    setFormData((prev) => ({
      ...prev,
      acceptance_criteria: prev.acceptance_criteria.filter((_, currentIndex) => currentIndex !== index),
    }));
  };

  const handleCriteriaChange = (index: number, value: string) => {
    setFormData((prev) => ({
      ...prev,
      acceptance_criteria: prev.acceptance_criteria.map((criterion, currentIndex) =>
        currentIndex === index ? value : criterion,
      ),
    }));
  };

  const validate = () => {
    const nextErrors: Record<string, string> = {};

    if (!formData.title.trim()) {
      nextErrors.title = 'Title is required';
    }

    if (!formData.description.trim()) {
      nextErrors.description = 'Description is required';
    }

    if (!formData.repo) {
      nextErrors.repo = 'Repository is required';
    }

    if (!formData.branch) {
      nextErrors.branch = 'Branch is required';
    }

    if (formData.acceptance_criteria.filter((criterion) => criterion.trim()).length === 0) {
      nextErrors.acceptance_criteria = 'At least one acceptance criterion is required';
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const resetForm = () => {
    setFormData(INITIAL_FORM_DATA);
    setErrors({});
    setSubmitError(null);
    setIsSubmitting(false);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleRepositoryChange = (repoFullName: string) => {
    const defaultBranch =
      repositories.find((repository) => repository.full_name === repoFullName)?.default_branch || '';

    setFormData((prev) => ({
      ...prev,
      repo: repoFullName,
      branch: defaultBranch,
    }));

    setErrors((prev) => {
      const nextErrors = { ...prev };
      delete nextErrors.repo;
      delete nextErrors.branch;
      return nextErrors;
    });
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);

    if (!validate()) {
      return;
    }

    const cleanedData = {
      ...formData,
      title: formData.title.trim(),
      description: formData.description.trim(),
      acceptance_criteria: formData.acceptance_criteria
        .map((criterion) => criterion.trim())
        .filter(Boolean),
    };

    setIsSubmitting(true);

    try {
      await onSubmit(cleanedData);
      handleClose();
    } catch (error) {
      setSubmitError(getErrorMessage(error, 'Failed to create task'));
      setIsSubmitting(false);
    }
  };

  if (!isOpen) {
    return null;
  }

  const selectedRepoBranches = formData.repo ? branches[formData.repo] || [] : [];
  const isLoadingSelectedBranches = formData.repo ? isLoadingBranches[formData.repo] : false;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
        <div className="flex items-center justify-between p-6 border-b border-[#2A2A2A]">
          <h2 className="text-xl font-semibold text-[#F5F5F5]">Create New Task</h2>
          <button
            onClick={handleClose}
            className="text-[#5A5A5A] hover:text-[#F5F5F5] transition-colors"
            aria-label="Close task creation modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form
          id="task-create-form"
          onSubmit={handleSubmit}
          className="flex-1 overflow-y-auto p-6 space-y-6"
        >
          {githubError && (
            <div className="flex items-start gap-3 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{githubError}</span>
            </div>
          )}

          {submitError && (
            <div className="flex items-start gap-3 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{submitError}</span>
            </div>
          )}

          <div className="space-y-2">
            <label className="text-sm font-medium text-[#F5F5F5]">
              Task Title <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={formData.title}
              onChange={(event) =>
                setFormData((prev) => ({ ...prev, title: event.target.value }))
              }
              placeholder="e.g., Implement user authentication API"
              className={cn(
                'w-full bg-[#0F0F0F] border rounded-lg px-4 py-3 text-sm text-[#F5F5F5] outline-none transition-all',
                errors.title
                  ? 'border-red-500 focus:border-red-400'
                  : 'border-[#2A2A2A] focus:border-indigo-500',
              )}
            />
            {errors.title && (
              <div className="flex items-center gap-2 text-red-400 text-xs">
                <AlertCircle className="w-3 h-3" />
                {errors.title}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-[#F5F5F5]">
              Description <span className="text-red-400">*</span>
            </label>
            <textarea
              value={formData.description}
              onChange={(event) =>
                setFormData((prev) => ({ ...prev, description: event.target.value }))
              }
              placeholder="Describe what needs to be done..."
              rows={4}
              className={cn(
                'w-full bg-[#0F0F0F] border rounded-lg px-4 py-3 text-sm text-[#F5F5F5] outline-none transition-all resize-none',
                errors.description
                  ? 'border-red-500 focus:border-red-400'
                  : 'border-[#2A2A2A] focus:border-indigo-500',
              )}
            />
            {errors.description && (
              <div className="flex items-center gap-2 text-red-400 text-xs">
                <AlertCircle className="w-3 h-3" />
                {errors.description}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-[#F5F5F5] flex items-center gap-2">
                <Github className="w-4 h-4" />
                Repository <span className="text-red-400">*</span>
              </label>
              {isLoadingRepos ? (
                <div className="w-full bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg px-4 py-3 flex items-center gap-2 text-[#5A5A5A]">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Loading repositories...</span>
                </div>
              ) : (
                <select
                  value={formData.repo}
                  onChange={(event) => handleRepositoryChange(event.target.value)}
                  className={cn(
                    'w-full bg-[#0F0F0F] border rounded-lg px-4 py-3 text-sm text-[#F5F5F5] outline-none transition-all',
                    errors.repo
                      ? 'border-red-500 focus:border-red-400'
                      : 'border-[#2A2A2A] focus:border-indigo-500',
                  )}
                >
                  <option value="">Select repository</option>
                  {repositories.length === 0 && (
                    <option value="" disabled>
                      No repositories available
                    </option>
                  )}
                  {repositories.map((repository) => (
                    <option key={repository.id} value={repository.full_name}>
                      {repository.full_name}
                    </option>
                  ))}
                </select>
              )}
              {errors.repo && (
                <div className="flex items-center gap-2 text-red-400 text-xs">
                  <AlertCircle className="w-3 h-3" />
                  {errors.repo}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-[#F5F5F5] flex items-center gap-2">
                <GitBranch className="w-4 h-4" />
                Branch <span className="text-red-400">*</span>
              </label>
              {isLoadingSelectedBranches ? (
                <div className="w-full bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg px-4 py-3 flex items-center gap-2 text-[#5A5A5A]">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Loading branches...</span>
                </div>
              ) : (
                <select
                  value={formData.branch}
                  onChange={(event) =>
                    setFormData((prev) => ({ ...prev, branch: event.target.value }))
                  }
                  disabled={!formData.repo}
                  className={cn(
                    'w-full bg-[#0F0F0F] border rounded-lg px-4 py-3 text-sm text-[#F5F5F5] outline-none transition-all',
                    !formData.repo && 'opacity-50 cursor-not-allowed',
                    errors.branch
                      ? 'border-red-500 focus:border-red-400'
                      : 'border-[#2A2A2A] focus:border-indigo-500',
                  )}
                >
                  <option value="">Select branch</option>
                  {selectedRepoBranches.map((branch) => (
                    <option key={branch.name} value={branch.name}>
                      {branch.name}
                      {branch.protected ? ' (protected)' : ''}
                    </option>
                  ))}
                </select>
              )}
              {errors.branch && (
                <div className="flex items-center gap-2 text-red-400 text-xs">
                  <AlertCircle className="w-3 h-3" />
                  {errors.branch}
                </div>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-[#F5F5F5]">Priority</label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {(['Low', 'Medium', 'High', 'Critical'] as const).map((priority) => (
                <button
                  key={priority}
                  type="button"
                  onClick={() => setFormData((prev) => ({ ...prev, priority }))}
                  className={cn(
                    'px-4 py-2 rounded-lg text-sm font-medium transition-all',
                    formData.priority === priority
                      ? priority === 'Critical'
                        ? 'bg-red-600 text-white'
                        : priority === 'High'
                          ? 'bg-orange-600 text-white'
                          : priority === 'Medium'
                            ? 'bg-amber-600 text-white'
                            : 'bg-indigo-600 text-white'
                      : 'bg-[#242424] text-[#A0A0A0] hover:bg-[#2A2A2A]',
                  )}
                >
                  {priority}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-[#F5F5F5]">
                Acceptance Criteria <span className="text-red-400">*</span>
              </label>
              <button
                type="button"
                onClick={handleAddCriteria}
                className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
              >
                <Plus className="w-3 h-3" />
                Add criterion
              </button>
            </div>
            <div className="space-y-3">
              {formData.acceptance_criteria.map((criterion, index) => (
                <div key={index} className="flex gap-2">
                  <input
                    type="text"
                    value={criterion}
                    onChange={(event) => handleCriteriaChange(index, event.target.value)}
                    placeholder={`Criterion ${index + 1}`}
                    className="flex-1 bg-[#0F0F0F] border border-[#2A2A2A] rounded-lg px-4 py-2 text-sm text-[#F5F5F5] outline-none focus:border-indigo-500 transition-all"
                  />
                  {formData.acceptance_criteria.length > 1 && (
                    <button
                      type="button"
                      onClick={() => handleRemoveCriteria(index)}
                      className="text-[#5A5A5A] hover:text-red-400 transition-colors"
                      aria-label={`Remove criterion ${index + 1}`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
            {errors.acceptance_criteria && (
              <div className="flex items-center gap-2 text-red-400 text-xs">
                <AlertCircle className="w-3 h-3" />
                {errors.acceptance_criteria}
              </div>
            )}
          </div>
        </form>

        <div className="flex items-center justify-end gap-3 p-6 border-t border-[#2A2A2A]">
          <button
            type="button"
            onClick={handleClose}
            className="px-6 py-2.5 rounded-lg text-sm font-medium text-[#A0A0A0] bg-transparent border border-[#2A2A2A] hover:border-[#383838] transition-all"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="task-create-form"
            disabled={isSubmitting}
            className="px-6 py-2.5 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed transition-all shadow-lg shadow-indigo-500/20"
          >
            {isSubmitting ? 'Creating...' : 'Create Task'}
          </button>
        </div>
      </div>
    </div>
  );
};
