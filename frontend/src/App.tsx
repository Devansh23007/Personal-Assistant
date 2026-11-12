import { useState } from "react";
import { ViperHUD, type ViperStatus } from "./ViperHUD";

declare global {
  interface Window {
    viperDesktop?: {
      setExpanded: (expanded: boolean) => Promise<void>;
    };
  }
}

function App() {
  const [isOpen, setIsOpen] = useState(false);
  const [hudState, setHudState] = useState<ViperStatus>("armed");

  const setExpanded = (expanded: boolean) => {
    setIsOpen(expanded);
    void window.viperDesktop?.setExpanded(expanded);
  };

  return (
    <div className="viper-app-root">
      <section
        className={`viper-widget-window${isOpen ? " is-open" : " is-collapsed"}`}
        hidden={!isOpen}
        role="dialog"
        aria-label="Viper personal assistant"
        aria-hidden={!isOpen}
      >
        <header className="viper-widget-titlebar">
          <span className="viper-widget-logo" aria-hidden="true">
            V
            <span className={`titlebar-status-dot state-${hudState}`} />
          </span>
          <span className="viper-widget-title">
            <strong>V.I.P.E.R.</strong>
            <small>Personal assistant</small>
          </span>
          <div className="viper-widget-window-actions">
            <button type="button" aria-label="Minimize Viper" title="Minimize" onClick={() => void setExpanded(false)}>−</button>
            <button type="button" aria-label="Close Viper window" title="Close" onClick={() => void setExpanded(false)}>×</button>
          </div>
        </header>
        <div className="viper-widget-content">
          <ViperHUD onStateChange={setHudState} />
        </div>
      </section>

      {!isOpen && (
        <button
          type="button"
          className="viper-widget-launcher"
          aria-label="Open Viper assistant"
          title="Open Viper assistant"
          onClick={() => void setExpanded(true)}
        >
          <span className="viper-widget-logo launcher-logo" aria-hidden="true">V</span>
          <span className={`viper-widget-launcher-pulse state-${hudState}`} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

export default App;
