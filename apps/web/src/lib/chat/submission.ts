export type ChatSubmissionFailure = { message: string; draft: string | null };
export function chatSubmissionScope(userId: string, workspaceId: string, threadId: string): string {
  return JSON.stringify([userId, workspaceId, threadId]);
}
export function rejectedChatSubmission(error: unknown, question: string, isEdit = false): ChatSubmissionFailure {
  return { message: error instanceof Error ? error.message : "Chat request failed.", draft: isEdit ? null : question };
}
export function questionAfterSubmission(question: string, accepted: boolean): string {
  return accepted ? "" : question;
}
