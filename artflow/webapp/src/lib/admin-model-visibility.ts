export function installAdminModelVisibility(): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.apixAdmin = "true";
}
