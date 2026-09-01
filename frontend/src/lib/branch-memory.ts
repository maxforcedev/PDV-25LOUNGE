export const BRANCH_MEMORY_VERSION = 1;

export type BranchMemory = Record<string, number>;

interface BranchCandidate {
  id: number;
  company_id: number;
  status: string;
}

export function parseBranchMemory(value: string | null): BranchMemory {
  if (!value) return {};

  try {
    const parsed: unknown = JSON.parse(value);
    if (
      !parsed ||
      typeof parsed !== "object" ||
      Array.isArray(parsed) ||
      !("version" in parsed) ||
      parsed.version !== BRANCH_MEMORY_VERSION ||
      !("branches" in parsed) ||
      !parsed.branches ||
      typeof parsed.branches !== "object" ||
      Array.isArray(parsed.branches)
    ) {
      return {};
    }

    return Object.fromEntries(
      Object.entries(parsed.branches).filter(([companyId, branchId]) => {
        const numericCompanyId = Number(companyId);
        return (
          Number.isSafeInteger(numericCompanyId) &&
          numericCompanyId > 0 &&
          String(numericCompanyId) === companyId &&
          Number.isSafeInteger(branchId) &&
          Number(branchId) > 0
        );
      }),
    );
  } catch {
    return {};
  }
}

export function serializeBranchMemory(memory: BranchMemory): string {
  return JSON.stringify({ version: BRANCH_MEMORY_VERSION, branches: memory });
}

export function withRememberedBranch(
  memory: BranchMemory,
  companyId: number,
  branchId: number,
): BranchMemory {
  return { ...memory, [String(companyId)]: branchId };
}

export function selectActiveBranch<T extends BranchCandidate>(
  branches: readonly T[],
  companyId: number | null,
  companyIsActive: boolean,
  rememberedBranchId?: number,
  compatibilityBranchId?: number,
): T | undefined {
  if (!companyId || !companyIsActive) return undefined;

  const activeBranches = branches.filter(
    (branch) =>
      branch.company_id === companyId && branch.status === "active",
  );
  return (
    activeBranches.find((branch) => branch.id === rememberedBranchId) ??
    activeBranches.find((branch) => branch.id === compatibilityBranchId) ??
    activeBranches[0]
  );
}
