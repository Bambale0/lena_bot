import type { AppTab, UserProfile } from "./types";

export function lilacRequested(user: UserProfile, search: string): boolean {
  const requested = new URLSearchParams(search).get("ux");
  return user.miniapp_ux2_available === true && (requested === null || requested === "3");
}

export function lilacPrimaryTab(tab: AppTab): AppTab {
  if (["home", "create", "ideas", "profile"].includes(tab)) return tab;
  if (["feed", "studio", "trends", "library"].includes(tab)) return "ideas";
  if (["works", "settings", "help", "billing", "owner", "account"].includes(tab)) return "profile";
  return "create";
}

export function lilacParent(tab: AppTab): AppTab | null {
  const parent = lilacPrimaryTab(tab);
  return parent === tab ? null : parent;
}
