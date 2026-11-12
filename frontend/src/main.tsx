import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

if (window.viperDesktop) {
  document.body.classList.add("viper-desktop-mode");
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
