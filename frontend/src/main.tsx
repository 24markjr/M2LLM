import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./theme/tokens.css";
import "./styles.css";
import "./ui/ui.css";
import "./ui/components.css";
import "./shell/shell.css";
import "./home/home.css";
import "./journal/journal.css";
import { ThemeProvider } from "./theme/ThemeProvider";
import { applyTheme, browserStorage, loadTheme } from "./theme/theme";
import { ToastProvider } from "./ui/components";

// Before the first render, so a dark choice never flashes light (index.html does the same earlier).
applyTheme(loadTheme(browserStorage()));

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

createRoot(root).render(
  <StrictMode>
    <ThemeProvider>
      <ToastProvider>
        <App />
      </ToastProvider>
    </ThemeProvider>
  </StrictMode>,
);
