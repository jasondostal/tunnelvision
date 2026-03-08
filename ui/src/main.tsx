import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./lib/theme"; // Apply accent hue before render — no flash
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
