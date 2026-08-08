import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/app/App";
import { installAdminModelVisibility } from "@/lib/admin-model-visibility";
import { installMiniMaxH3MiniappEnhancer } from "@/lib/minimax-h3-miniapp-enhancer";
import { installSeedance25MiniappEnhancer } from "@/lib/seedance25-miniapp-enhancer";
import "@/styles/globals.css";
import "@/styles/color-schemes.css";
import "@/styles/responsive.css";
import "@/styles/feed-mobile-polish.css";

const root = document.getElementById("root");
if (!root) throw new Error("Mini App root element is missing");

const legacy = new URLSearchParams(window.location.search).get("legacy") === "1";
installAdminModelVisibility();
installSeedance25MiniappEnhancer();
installMiniMaxH3MiniappEnhancer();

if (legacy) {
  void import("./main.jsx");
} else {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
