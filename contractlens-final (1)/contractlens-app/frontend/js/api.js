/**
 * api.js — Centralised API service layer for ContractLens frontend.
 *
 * Because the FastAPI backend now SERVES the frontend as static files,
 * all API calls go to the same origin — no hardcoded localhost needed.
 *
 * Usage:
 *   import { uploadContract, getStatus, getResults, askQuestion } from './api.js';
 *
 * Or just include this script and use the global `ContractLensAPI` object.
 */

const API_BASE =https://contractlens-app-kd41.vercel.app; // Same server = same origin, always correct

// ── Error class ─────────────────────────────────────────────────────────
class APIError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name  = 'APIError';
    this.status = status;
    this.detail = detail;
  }
}

// ── Core fetch wrapper ───────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  try {
    const res = await fetch(url, {
      headers: { 'Accept': 'application/json', ...options.headers },
      ...options
    });

    const contentType = res.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await res.json() : await res.text();

    if (!res.ok) {
      const message = data?.detail || data?.error || `Request failed (${res.status})`;
      throw new APIError(message, res.status, data);
    }

    return data;
  } catch (err) {
    if (err instanceof APIError) throw err;
    // Network error (server down, CORS, etc.)
    throw new APIError(
      'Cannot connect to the server. Make sure it is running.',
      0,
      err.message
    );
  }
}

// ── API Methods ──────────────────────────────────────────────────────────

/**
 * Upload a contract PDF file.
 * @param {File} file
 * @returns {Promise<{document_id: string, filename: string, status: string}>}
 */
async function uploadContract(file) {
  const form = new FormData();
  form.append('file', file);
  return apiFetch('/api/upload', { method: 'POST', body: form });
}

/**
 * Poll analysis status until done or error.
 * @param {string} documentId
 * @returns {Promise<{status: string, progress_message: string}>}
 */
async function getStatus(documentId) {
  return apiFetch(`/api/status/${documentId}`);
}

/**
 * Get full analysis results for a completed document.
 * @param {string} documentId
 * @returns {Promise<AnalysisResponse>}
 */
async function getResults(documentId) {
  return apiFetch(`/api/results/${documentId}`);
}

/**
 * Ask a natural language question about a contract.
 * @param {string} documentId
 * @param {string} question
 * @returns {Promise<{answer: string, relevant_clauses: Clause[]}>}
 */
async function askQuestion(documentId, question) {
  return apiFetch(`/api/ask/${documentId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question })
  });
}

/**
 * Delete a document and all its data.
 * @param {string} documentId
 */
async function deleteDocument(documentId) {
  return apiFetch(`/api/document/${documentId}`, { method: 'DELETE' });
}

/**
 * Health check.
 */
async function healthCheck() {
  return apiFetch('/api/health');
}

/**
 * Poll status with automatic retry, progress callbacks, and timeout.
 * @param {string} documentId
 * @param {object} callbacks - { onProgress(pct, label), onComplete(data), onError(msg) }
 */
async function pollUntilDone(documentId, callbacks = {}) {
  const { onProgress, onComplete, onError } = callbacks;
  const steps = [
    [30, 'Parsing PDF…'],
    [45, 'Extracting clauses…'],
    [60, 'Running AI analysis…'],
    [75, 'Scoring risk levels…'],
    [88, 'Finalising report…'],
  ];
  let stepIdx  = 0;
  let attempts = 0;
  const MAX    = 90; // 90 × 2s = 3 min timeout

  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      attempts++;
      if (stepIdx < steps.length) {
        const [pct, label] = steps[stepIdx++];
        onProgress?.(pct, label);
      }
      if (attempts > MAX) {
        clearInterval(interval);
        const msg = 'Analysis timed out. Please try again.';
        onError?.(msg);
        reject(new Error(msg));
        return;
      }
      try {
        const status = await getStatus(documentId);
        if (status.status === 'done') {
          clearInterval(interval);
          onProgress?.(100, 'Complete!');
          onComplete?.(status);
          resolve(status);
        } else if (status.status === 'error') {
          clearInterval(interval);
          const msg = 'Analysis failed. The PDF may be scanned or corrupted.';
          onError?.(msg);
          reject(new Error(msg));
        }
      } catch (e) {
        clearInterval(interval);
        onError?.(e.message);
        reject(e);
      }
    }, 2000);
  });
}

// ── Document ID helpers ──────────────────────────────────────────────────

function getDocumentIdFromURL() {
  return new URLSearchParams(window.location.search).get('id');
}

function navigateToResults(documentId) {
  window.location.href = `/results?id=${documentId}`;
}

// ── Export as global object ───────────────────────────────────────────────
window.ContractLensAPI = {
  uploadContract,
  getStatus,
  getResults,
  askQuestion,
  deleteDocument,
  healthCheck,
  pollUntilDone,
  getDocumentIdFromURL,
  navigateToResults,
  APIError
};
