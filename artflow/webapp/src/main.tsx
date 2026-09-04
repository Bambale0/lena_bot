import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/app/App";
import { openPinterestService } from "@/features/pinterest-service-runner";
import { installAdminModelVisibility } from "@/lib/admin-model-visibility";
import { installFeedVideoStabilizer } from "@/lib/feed-video-stabilizer";
import { installModelEnhancerLoader } from "@/lib/model-enhancer-loader";
import { installTelegramNavigation } from "@/lib/telegram-navigation";
import "@/styles/globals.css";
import "@/styles/color-schemes.css";
import "@/styles/responsive.css";
import "@/styles/performance.css";

const root = document.getElementById("root");
if (!root) throw new Error("Mini App root element is missing");

const search = new URLSearchParams(window.location.search);
const legacy = search.get("legacy") === "1";
const requestedService = String(search.get("service") || "").trim().toLowerCase();

function openRequestedService(): void {
  if (requestedService !== "pinterest") return;
  // The Pinterest portal mounts globally after module evaluation. A short delay
  // guarantees its React effect is listening before we dispatch the open event.
  window.setTimeout(() => openPinterestService(), 120);
}

installAdminModelVisibility();

if (legacy) {
  void import("./main.jsx");
} else {
  installFeedVideoStabilizer();
  installModelEnhancerLoader();
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
  installTelegramNavigation();
  openRequestedService();
}
