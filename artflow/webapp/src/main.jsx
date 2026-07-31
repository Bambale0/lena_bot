import React from "react";
import { createRoot } from "react-dom/client";
import VelvetApp from "./v2/VelvetApp.jsx";
import "./v2/velvet-neon.css";

window.__APIX_MINIAPP_BUILD_ID__ = "20260801-velvet-neon-front-v2";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <VelvetApp />
  </React.StrictMode>,
);
