import type { AppTab, UserProfile } from "./types";

export function lilacRequested(user: UserProfile, search: string): boolean {
  return user.miniapp_ux2_available === true && new URLSearchParams(search).get("ux") === "3";
}

export function lilacPrimaryTab(tab: AppTab): AppTab {
  if (["home", "create", "ideas", "works", "profile"].includes(tab)) return tab;
  if (["feed", "studio", "trends", "library"].includes(tab)) return "ideas";
  if (["settings", "help", "billing", "owner", "account"].includes(tab)) return "profile";
  return "create";
}

export function lilacParent(tab: AppTab): AppTab | null {
  const parent = lilacPrimaryTab(tab);
  return parent === tab ? null : parent;
}
