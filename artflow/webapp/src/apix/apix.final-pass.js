// Final APIX navigation polish.
// React owns routing; this layer only fixes legacy labels and forwards the secondary create tab
// to the existing center create action until BottomNav is split into a dedicated component.

const NAV_LABELS = [
  { icon: "⌂", label: "Лента" },
  { icon: "＋", label: "Создать" },
  { icon: "✦", label: "" },
  { icon: "▱", label: "Промпты" },
  { icon: "◉", label: "Профиль" },
];

function normalizeBottomNav(root = document) {
  const buttons = Array.from(root.querySelectorAll(".bottomNav button"));
  if (buttons.length < 5) return;

  buttons.slice(0, 5).forEach((button, index) => {
    const data = NAV_LABELS[index];
    const icon = button.querySelector("b");
    let label = button.querySelector("span");

    if (icon && icon.textContent !== data.icon) icon.textContent = data.icon;

    if (data.label) {
      if (!label) {
        label = document.createElement("span");
        button.appendChild(label);
      }
      if (label.textContent !== data.label) label.textContent = data.label;
    } else if (label) {
      label.remove();
    }

    button.dataset.apixNavIndex = String(index);
  });
}

function bindBottomNavForwarding() {
  document.addEventListener(
    "click",
    (event) => {
      const target = event.target instanceof Element ? event.target.closest(".bottomNav button") : null;
      if (!target || target.dataset.apixNavIndex !== "1") return;

      const centerCreate = document.querySelector('.bottomNav button[data-apix-nav-index="2"]');
      if (!centerCreate || centerCreate === target) return;

      event.preventDefault();
      event.stopPropagation();
      centerCreate.click();
    },
    true,
  );
}

if (typeof window !== "undefined") {
  window.addEventListener("DOMContentLoaded", () => normalizeBottomNav());
  bindBottomNavForwarding();

  const observer = new MutationObserver(() => normalizeBottomNav());
  observer.observe(document.documentElement, { childList: true, subtree: true });
}
