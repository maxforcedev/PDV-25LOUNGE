export interface ProductApiError {
  code: string | null;
  message: string;
  fields: Record<string, string[]>;
  details: Record<string, unknown>;
}

export function archivedProductConflict(
  error: ProductApiError,
  fallbackName: string,
) {
  if (error.code !== "archived_product_exists") return null;
  const productId = Number(error.details.product_id);
  if (!Number.isSafeInteger(productId) || productId < 1) return null;
  return {
    productId,
    name: String(error.details.name || fallbackName),
    archivedAt:
      typeof error.details.archived_at === "string"
        ? error.details.archived_at
        : null,
  };
}

export function uniqueProductErrorMessage(error: ProductApiError) {
  const messages = [error.message, ...Object.values(error.fields).flat()]
    .map((message) => message.trim())
    .filter(Boolean);
  return [...new Set(messages)].join(" ");
}

export function productRestoreRedirect() {
  return "/produtos";
}
