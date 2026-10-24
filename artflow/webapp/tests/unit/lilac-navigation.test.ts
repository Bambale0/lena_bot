import assert from "node:assert/strict";
import { test } from "node:test";
import { lilacParent, lilacPrimaryTab, lilacRequested } from "../../src/lib/lilac.ts";
import type { AppTab, UserProfile } from "../../src/lib/types";

test("Studio query requires authenticated server capability, never URL alone", () => {
  const user = { id: 7, miniapp_ux2_available: true } as UserProfile;
  assert.equal(lilacRequested(user, "?ux=3"), true);
  assert.equal(lilacRequested(user, "?ux=2"), false);
  assert.equal(lilacRequested({ ...user, miniapp_ux2_available: false }, "?ux=3&is_admin=true"), false);
  assert.equal(lilacRequested({ id: 7 } as UserProfile, "?ux=3"), false);
});
test("all nested supported Studio destinations have a visible five-section parent", () => {
  for (const tab of ["photo", "video", "motion", "models", "music", "services", "assistant"] as AppTab[]) assert.equal(lilacParent(tab), "create");
  for (const tab of ["feed", "trends", "library"] as AppTab[]) assert.equal(lilacParent(tab), "ideas");
  for (const tab of ["billing", "help", "settings", "owner"] as AppTab[]) assert.equal(lilacParent(tab), "profile");
  for (const tab of ["home", "create", "ideas", "works", "profile"] as AppTab[]) { assert.equal(lilacParent(tab), null); assert.equal(lilacPrimaryTab(tab), tab); }
});
