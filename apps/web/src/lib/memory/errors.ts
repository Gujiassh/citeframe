export const errors = {
  authentication_required: [401, "Authentication required.", false],
  workspace_not_found: [404, "Workspace not found.", false],
  memory_not_found: [404, "Memory not found.", false],
  source_not_found: [404, "Source not found.", false],
  operation_not_found: [404, "Operation not found.", false],
  version_conflict: [409, "Memory version changed.", false],
  terminal_memory: [409, "Memory cannot be changed by this operation.", false],
  idempotency_conflict: [409, "Request identity conflicts with an existing operation.", false],
  operation_in_progress: [409, "Operation has not settled. Poll using the original request ID.", true],
  erased: [410, "Memory content has been erased.", false],
  source_version_unavailable: [410, "Source version is unavailable.", false],
  invalid_request: [422, "Invalid request.", false],
  invalid_scope: [422, "Memory scope is unsupported.", false],
  invalid_source_ref: [422, "Source reference is unsupported.", false],
  invalid_cursor: [422, "Cursor is invalid or expired.", false],
  unsupported_operation: [422, "Memory operation is unsupported.", false],
  sensitive_content_unsupported: [422, "Submitted content contains an unsupported credential pattern.", false],
  temporarily_unavailable: [503, "Memory service is temporarily unavailable. Retry using the original request identity.", true],
  outcome_unknown: [503, "Operation outcome is unknown. Poll using the original request ID.", true],
} as const;
export type ErrorCode = keyof typeof errors;
export type ErrorDetail = { code: ErrorCode; message: string; retryable: boolean; requestId: string | null; currentVersion?: number };
export function errorDetail(code: ErrorCode, requestId: string | null = null, currentVersion?: number): ErrorDetail {
  return { code, message: errors[code][1], retryable: errors[code][2], requestId,
    ...((code === "version_conflict" || code === "terminal_memory") && Number.isSafeInteger(currentVersion) && currentVersion! > 0 ? { currentVersion } : {}) };
}
export class MemoryError extends Error {
  constructor(public detail: ErrorDetail, public status = errors[detail.code][0]) { super(detail.message); }
}
export function knownCode(value: unknown): value is ErrorCode { return typeof value === "string" && Object.hasOwn(errors, value); }
