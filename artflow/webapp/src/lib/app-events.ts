export const OPEN_BALANCE_EVENT = "apix:open-balance";
export const BALANCE_UPDATED_EVENT = "apix:balance-updated";
export const BALANCE_SHEET_STATE_EVENT = "apix:balance-sheet-state";

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

export interface BalanceSheetStateDetail {
  open: boolean;
}

export function notifyBalanceSheetState(open: boolean): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<BalanceSheetStateDetail>(BALANCE_SHEET_STATE_EVENT, { detail: { open } }));
}
