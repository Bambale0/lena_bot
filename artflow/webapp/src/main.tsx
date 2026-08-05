import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/app/App";
import { TrendRunnerPortal } from "@/features/trend-runner";
import "@/styles/globals.css";
import "@/styles/color-schemes.css";
import "@/styles/responsive.css";
import "@/styles/feed-mobile-polish.css";

const root = document.getElementById("root");
if (!root) throw new Error("Mini App root element is missing");

const legacy = new URLSearchParams(window.location.search).get("legacy") === "1";

if (legacy) {
  void import("./main.jsx");
} else {
  createRoot(root).render(
    <StrictMode>
      <App />
      <TrendRunnerPortal />
    </StrictMode>,
  );
}
