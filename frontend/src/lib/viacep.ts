import type { Address } from "@/types";

interface ViaCepResponse {
  logradouro?: string;
  complemento?: string;
  bairro?: string;
  localidade?: string;
  uf?: string;
  erro?: boolean;
}

export type ViaCepAddress = Pick<Address, "street" | "complement" | "neighborhood" | "city" | "state">;

export class ViaCepError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ViaCepError";
  }
}

export function zipCodeDigits(value: string) {
  return value.replace(/\D/g, "").slice(0, 8);
}

export function formatZipCode(value: string) {
  const digits = zipCodeDigits(value);
  return digits.length > 5 ? `${digits.slice(0, 5)}-${digits.slice(5)}` : digits;
}

export async function lookupAddressByZipCode(zipCode: string, signal?: AbortSignal, timeoutMs = 6000): Promise<ViaCepAddress> {
  const digits = zipCodeDigits(zipCode);
  if (digits.length !== 8) throw new ViaCepError("Informe um CEP com 8 dígitos.");

  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetch(`https://viacep.com.br/ws/${digits}/json/`, { signal: controller.signal });
    if (!response.ok) throw new ViaCepError("Não foi possível consultar o CEP. Preencha o endereço manualmente.");
    const data = await response.json() as ViaCepResponse;
    if (data.erro) throw new ViaCepError("CEP não encontrado. Confira o número ou preencha o endereço manualmente.");
    return {
      street: data.logradouro || "",
      complement: data.complemento || "",
      neighborhood: data.bairro || "",
      city: data.localidade || "",
      state: data.uf || "",
    };
  } catch (caught) {
    if (timedOut) throw new ViaCepError("A consulta do CEP demorou demais. Preencha o endereço manualmente.");
    if (caught instanceof ViaCepError || signal?.aborted) throw caught;
    throw new ViaCepError("Não foi possível consultar o CEP. Preencha o endereço manualmente.");
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}
