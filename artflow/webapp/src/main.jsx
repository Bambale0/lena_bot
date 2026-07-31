import React from "react";
import { createRoot } from "react-dom/client";
import VelvetApp from "./v2/VelvetApp.jsx";
import "./v2/velvet-neon.css";
import "./v2/velvet-typography.css";

window.__APIX_MINIAPP_BUILD_ID__ = "20260801-velvet-neon-typography-v1";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <VelvetApp />
  </React.StrictMode>,
);
