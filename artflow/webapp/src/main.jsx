import React from "react";
import { createRoot } from "react-dom/client";
import ConceptApp from "./concept/App.jsx";
import "./concept/concept.css";

window.__APIX_MINIAPP_BUILD_ID__ = "20260801-velvet-concept-v1";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ConceptApp/>
  </React.StrictMode>,
);
