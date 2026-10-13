import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./theme/tokens.css";
import "./styles.css";
import "./ui/ui.css";
import { ThemeProvider } from "./theme/ThemeProvider";
import { applyTheme, browserStorage, loadTheme } from "./theme/theme";

// Before the first render, so a dark choice never flashes light (index.html does the same earlier).
applyTheme(loadTheme(browserStorage()));

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

createRoot(root).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
);
