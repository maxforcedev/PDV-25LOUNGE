export interface StructuredApiError {
  code: string | null;
  details: Record<string, unknown>;
}

export function archivedRecordConflict(
  error: StructuredApiError,
  code: string,
  idField: string,
) {
  if (error.code !== code) return null;
  const id = Number(error.details[idField]);
  const name = error.details.name;
  const archivedAt = error.details.archived_at;
  if (
    !Number.isSafeInteger(id) ||
    id < 1 ||
    typeof name !== "string" ||
    typeof archivedAt !== "string"
  )
    return null;
  return { id, name, archivedAt };
}
