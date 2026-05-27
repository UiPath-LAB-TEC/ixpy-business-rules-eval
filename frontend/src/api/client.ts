import type {
  Analytics,
  ArchiveDocumentResult,
  Dashboard,
  DocumentDetail,
  DocumentSummary,
  EvidenceAnnotation,
  Explanation,
  LogEntry,
  RecomputeResult,
  ReviewPayload,
  Run,
  TrainingExceptionExport,
  TrainingExceptionQueueItem,
  TrainingExceptionResult,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === 'string' ? detail.detail : detail.detail?.message ?? response.statusText);
  }
  return response.json() as Promise<T>;
}

export const api = {
  dashboard: () => request<Dashboard>('/dashboard'),
  documents: (params: URLSearchParams) => request<{ items: DocumentSummary[]; total: number; limit: number; offset: number }>(`/documents?${params}`),
  document: (filename: string) => request<DocumentDetail>(`/documents/${encodeURIComponent(filename)}`),
  explanation: (filename: string, ruleName: string) => request<Explanation>(`/evaluations/${encodeURIComponent(filename)}/${encodeURIComponent(ruleName)}/explanation`),
  analytics: () => request<Analytics>('/analytics'),
  runs: () => request<Run[]>('/runs'),
  logs: () => request<{ items: LogEntry[]; total: number; limit: number; offset: number }>('/logs'),
  saveReview: (filename: string, ruleName: string, payload: ReviewPayload) =>
    request<ReviewPayload>(`/reviews/${encodeURIComponent(filename)}/${encodeURIComponent(ruleName)}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  addTrainingException: (filename: string, ruleName?: string | null) => {
    const params = ruleName ? `?rule_name=${encodeURIComponent(ruleName)}` : '';
    return request<TrainingExceptionResult>(`/documents/${encodeURIComponent(filename)}/training-exception${params}`, {
      method: 'POST',
    });
  },
  archiveDocument: (filename: string, ruleName?: string | null) => {
    const params = ruleName ? `?rule_name=${encodeURIComponent(ruleName)}` : '';
    return request<ArchiveDocumentResult>(`/documents/${encodeURIComponent(filename)}/archive${params}`, {
      method: 'POST',
    });
  },
  trainingExceptions: () => request<{ items: TrainingExceptionQueueItem[] }>('/training-exceptions'),
  removeTrainingException: (filename: string) =>
    request<{ removed: boolean }>(`/training-exceptions/${encodeURIComponent(filename)}`, {
      method: 'DELETE',
    }),
  exportTrainingExceptions: () =>
    request<TrainingExceptionExport>('/training-exceptions/export', {
      method: 'POST',
    }),
  saveAnnotations: (filename: string, ruleName: string, annotations: EvidenceAnnotation[]) =>
    request<{ annotations: EvidenceAnnotation[] }>(`/annotations/${encodeURIComponent(filename)}/${encodeURIComponent(ruleName)}`, {
      method: 'POST',
      body: JSON.stringify({ annotations }),
    }),
  recomputeAnnotations: (filename: string, ruleName: string, annotations: EvidenceAnnotation[]) =>
    request<RecomputeResult>(`/annotations/${encodeURIComponent(filename)}/${encodeURIComponent(ruleName)}/recompute`, {
      method: 'POST',
      body: JSON.stringify({ annotations }),
    }),
  failedRulesCsvUrl: () => `${API_BASE_URL}/exports/failed-rules.csv`,
  documentFileUrl: (filename: string) => `${API_BASE_URL}/documents/${encodeURIComponent(filename)}/file`,
};
