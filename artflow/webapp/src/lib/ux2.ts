import type { AppTab, UserProfile } from "./types";

export const UX2_TABS = ["feed", "trends", "create", "works", "profile"] as const;
export type Ux2Tab = (typeof UX2_TABS)[number];

export function primaryTab(tab: AppTab): Ux2Tab {
  if (["photo", "video", "motion", "services", "create"].includes(tab)) return "create";
  if (tab === "settings" || tab === "profile") return "profile";
  if (tab === "works" || tab === "trends") return tab;
  return "feed";
}

export function editorParent(tab: AppTab): Ux2Tab | null {
  if (["photo", "video", "motion", "services"].includes(tab)) return "create";
  return tab === "settings" ? "profile" : null;
}

export function previewKey(userId: number): string {
  return `apix:ux2:preview:${userId}`;
}

export function previewEnabled(user: UserProfile, search: string, saved: string | null): boolean {
  if (user.miniapp_ux2_available !== true) return false;
  const requested = new URLSearchParams(search).get("ux");
  return requested === "2" || (requested === null && saved === "2");
}
