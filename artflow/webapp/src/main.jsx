import React from "react";
import { createRoot } from "react-dom/client";
import App from "./apix/App.jsx";
import "./apix/apix.tokens.css";
import "./apix/apix.css";
import "./apix/apix-art.css";
import "./apix/apix.archive.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
