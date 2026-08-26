const BACKOFFICE_URL = (process.env.NEXT_PUBLIC_BACKOFFICE_URL || "").replace(/#.*$/, "");

export function supportSessionUrl(sessionId: number) {
  return BACKOFFICE_URL ? `${BACKOFFICE_URL}#support-session=${encodeURIComponent(String(sessionId))}` : null;
}

export async function copySupportAccess(sessionId: number) {
  const value = supportSessionUrl(sessionId) || String(sessionId);
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall through for browsers or contexts that deny Clipboard API access.
    }
  }
  const input = document.createElement("textarea");
  input.value = value;
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  const copied = document.execCommand("copy");
  input.remove();
  if (!copied) throw new Error("Nao foi possivel copiar o acesso de suporte.");
}
