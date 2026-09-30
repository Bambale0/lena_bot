export const OPEN_BALANCE_EVENT = "apix:open-balance";
export const BALANCE_UPDATED_EVENT = "apix:balance-updated";

export interface BalanceRequirement {
  requiredCredits: number;
  contextLabel?: string;
}

export interface BalanceUpdatedDetail {
  credits: number;
}

export function openBalanceForRequirement(detail: BalanceRequirement): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<BalanceRequirement>(OPEN_BALANCE_EVENT, { detail }));
}
