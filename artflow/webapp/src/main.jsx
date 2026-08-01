import React from "react";
import { createRoot } from "react-dom/client";
import App from "./apix/App.jsx";
import "./apix/apix.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
