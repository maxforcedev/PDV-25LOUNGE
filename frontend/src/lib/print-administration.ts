export type PrintRouteDraft = {
  document_type: string;
  mode: string;
  printer_device_ids: number[];
  copies: number;
  document_format: string;
};

export function isCurrentPrintAdministrationRequest(token: number, current: number) {
  return token === current;
}

export function buildPrintRouteBatch(
  documentTypes: readonly string[],
  routeFor: (documentType: string) => PrintRouteDraft,
) {
  return documentTypes.map((document_type) => {
    const route = routeFor(document_type);
    return {
      document_type,
      mode: route.mode,
      printer_device_ids: route.printer_device_ids,
      copies: route.copies,
      document_format: route.document_format,
    };
  });
}
