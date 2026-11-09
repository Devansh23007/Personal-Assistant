import { FormEvent, useEffect, useRef, useState } from "react";

type JarvisStatus = "idle" | "listening" | "thinking" | "speaking";

interface Telemetry {
  cpu_percent: number | null;
  memory_used_gb: number | null;
  memory_total_gb: number | null;
  memory_percent: number | null;
  battery_percent: number | null;
  battery_status: string | null;
  os_name: string;
  hostname: string;
  status: string;
}

interface ActionLogItem {
  id: string;
  timestamp: string;
  type: "user" | "jarvis" | "action";
  text: string;
  actionTag?: string;
}

// Global AudioContext singleton to prevent recreation overhead
let sharedAudioCtx: AudioContext | null = null;
function getAudioContext(): AudioContext | null {
  try {
    if (!sharedAudioCtx) {
      const AudioContextClass =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (AudioContextClass) {
        sharedAudioCtx = new AudioContextClass();
      }
    }
    if (sharedAudioCtx && sharedAudioCtx.state === "suspended") {
      sharedAudioCtx.resume().catch(() => {});
    }
    return sharedAudioCtx;
  } catch {
    return null;
  }
}

function playAudioChime(type: "activate" | "confirm" | "alert") {
  const ctx = getAudioContext();
  if (!ctx) return;

  try {
    if (type === "activate") {
      // 2-tone futuristic chirp
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.12);
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.22);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.22);
    } else if (type === "confirm") {
      // 3-tone arpeggio
      [523.25, 659.25, 783.99].forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        const start = ctx.currentTime + idx * 0.07;
        osc.frequency.setValueAtTime(freq, start);
        gain.gain.setValueAtTime(0.1, start);
        gain.gain.exponentialRampToValueAtTime(0.001, start + 0.16);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(start);
        osc.stop(start + 0.16);
      });
    } else {
      // Alert tone
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(220, ctx.currentTime);
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.25);
    }
  } catch {}
}

export function JarvisHUD({ onNavigateModule }: { onNavigateModule?: (mod: string) => void } = {}) {
  const [hudState, setHudState] = useState<JarvisStatus>("idle");
  const [isWakeWordActive, setIsWakeWordActive] = useState<boolean>(false);
  const [isVoiceMuted, setIsVoiceMuted] = useState<boolean>(false);
  const [micStatusMsg, setMicStatusMsg] = useState<string>("Click Core or toggle Wake Word to start.");
  const [currentTranscript, setCurrentTranscript] = useState<string>("");
  const [commandInput, setCommandInput] = useState<string>("");
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [clock, setClock] = useState<string>("");
  const [logs, setLogs] = useState<ActionLogItem[]>([
    {
      id: "init",
      timestamp: new Date().toLocaleTimeString(),
      type: "jarvis",
      text: "J.A.R.V.I.S. Core Online. All primary diagnostics nominal. Standing by for your instructions, Sir.",
      actionTag: "SYSTEM_READY",
    },
  ]);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const recognitionRef = useRef<any>(null);
  const isListeningRef = useRef<boolean>(false);
  const isWakeWordRef = useRef<boolean>(false);
  const restartTimerRef = useRef<any>(null);
  const hudStateRef = useRef<JarvisStatus>("idle");
  hudStateRef.current = hudState;
  isWakeWordRef.current = isWakeWordActive;

  // Real-time HUD Clock
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setClock(
        now.toLocaleTimeString("en-US", { hour12: false }) +
          " · " +
          now.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  // Poll Telemetry
  useEffect(() => {
    const fetchTelemetry = () => {
      fetch("/api/jarvis/telemetry")
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data) setTelemetry(data);
        })
        .catch(() => {});
    };
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 6000);
    return () => clearInterval(interval);
  }, []);

  // Web Speech Synthesis (JARVIS voice)
  const speakReply = (text: string) => {
    if (isVoiceMuted || !("speechSynthesis" in window)) return;

    window.speechSynthesis.cancel();
    const cleanText = text.replace(/[*#`_\[\]]/g, "").trim();
    const utterance = new SpeechSynthesisUtterance(cleanText);

    const voices = window.speechSynthesis.getVoices();
    const britishVoice = voices.find(
      (v) =>
        (v.lang.includes("en-GB") || v.lang.includes("en_GB")) &&
        (v.name.toLowerCase().includes("george") ||
          v.name.toLowerCase().includes("male") ||
          v.name.toLowerCase().includes("daniel"))
    );
    const englishMale = voices.find(
      (v) =>
        v.lang.startsWith("en") &&
        (v.name.toLowerCase().includes("male") ||
          v.name.toLowerCase().includes("david") ||
          v.name.toLowerCase().includes("mark"))
    );

    if (britishVoice) {
      utterance.voice = britishVoice;
    } else if (englishMale) {
      utterance.voice = englishMale;
    }

    utterance.pitch = 0.95;
    utterance.rate = 1.05;

    utterance.onstart = () => setHudState("speaking");
    utterance.onend = () => {
      setHudState("idle");
      // If wake-word was active, resume recognition safely
      if (isWakeWordRef.current && recognitionRef.current && !isListeningRef.current) {
        scheduleRestart(400);
      }
    };
    utterance.onerror = () => setHudState("idle");

    window.speechSynthesis.speak(utterance);
  };

  // Submit Command to Backend
  const executeCommand = async (commandText: string, isVoice = false) => {
    const trimmed = commandText.trim();
    if (!trimmed) return;

    // Add user message to log
    const userLogId = Math.random().toString(36).substring(7);
    setLogs((prev) => [
      ...prev,
      {
        id: userLogId,
        timestamp: new Date().toLocaleTimeString(),
        type: "user",
        text: trimmed,
      },
    ]);

    setCommandInput("");
    setCurrentTranscript("");
    setHudState("thinking");

    try {
      const res = await fetch("/api/jarvis/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, voice_mode: isVoice }),
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }

      const data = await res.json();
      playAudioChime("confirm");

      const jarvisLogId = Math.random().toString(36).substring(7);
      setLogs((prev) => [
        ...prev,
        {
          id: jarvisLogId,
          timestamp: new Date().toLocaleTimeString(),
          type: "jarvis",
          text: data.reply,
          actionTag: data.action_taken ? data.action_taken.toUpperCase() : undefined,
        },
      ]);

      if (data.system_status) {
        setTelemetry(data.system_status);
      }

      // Check if user requested module navigation
      const lower = trimmed.toLowerCase();
      if (lower.includes("show tasks") || lower.includes("open lifeos") || lower.includes("tasks module")) {
        onNavigateModule?.("LifeOS");
      } else if (lower.includes("show emails") || lower.includes("open inbox")) {
        onNavigateModule?.("InboxZero");
      } else if (lower.includes("show expenses") || lower.includes("open spendwise")) {
        onNavigateModule?.("SpendWise");
      } else if (lower.includes("show documents") || lower.includes("open docuvault")) {
        onNavigateModule?.("DocuVault");
      }

      // Speak Jarvis response
      speakReply(data.audio_text || data.reply);
    } catch (err: any) {
      playAudioChime("alert");
      setLogs((prev) => [
        ...prev,
        {
          id: Math.random().toString(36).substring(7),
          timestamp: new Date().toLocaleTimeString(),
          type: "jarvis",
          text: `Command error: ${err.message || "Failed to execute"}. Please verify backend status, Sir.`,
          actionTag: "ERROR",
        },
      ]);
      setHudState("idle");
    }
  };

  // Safe restart scheduler (prevents tight loops and browser freezes)
  const scheduleRestart = (delayMs = 800) => {
    if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
    restartTimerRef.current = setTimeout(() => {
      if (isWakeWordRef.current && recognitionRef.current && !isListeningRef.current) {
        try {
          recognitionRef.current.start();
        } catch {}
      }
    }, delayMs);
  };

  // Initialize Speech Recognition
  useEffect(() => {
    const SpeechRecognitionClass =
      (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;

    if (!SpeechRecognitionClass) {
      setMicStatusMsg("Voice recognition not supported in this browser. Please use Chrome or Edge.");
      return;
    }

    const recognition = new SpeechRecognitionClass();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onstart = () => {
      isListeningRef.current = true;
      setMicStatusMsg(
        isWakeWordRef.current
          ? "Hands-free listening active. Say 'Hey Jarvis' or click to speak."
          : "Listening to your voice... speak now."
      );
    };

    recognition.onresult = (event: any) => {
      let interim = "";
      let finalTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }

      const activeText = (finalTranscript || interim).trim();
      if (activeText) {
        setCurrentTranscript(activeText);
      }

      const lower = activeText.toLowerCase();

      // Trigger activate chime when wake word detected
      if (lower.includes("jarvis") && hudStateRef.current === "idle") {
        playAudioChime("activate");
        setHudState("listening");
      }

      if (finalTranscript) {
        const cleaned = finalTranscript.trim();
        if (cleaned.length > 1) {
          executeCommand(cleaned, true);
        }
      }
    };

    recognition.onerror = (event: any) => {
      const err = event.error;
      if (err === "not-allowed" || err === "service-not-allowed") {
        setMicStatusMsg("Microphone permission denied. Please allow microphone in browser bar.");
        setIsWakeWordActive(false);
        isWakeWordRef.current = false;
      } else if (err === "no-speech") {
        // Normal silence, no action needed
      } else {
        console.warn("Speech recognition warning:", err);
      }
    };

    recognition.onend = () => {
      isListeningRef.current = false;
      if (hudStateRef.current === "listening") {
        setHudState("idle");
      }

      // Only schedule restart if wake word is active and user didn't disable it
      if (isWakeWordRef.current) {
        scheduleRestart(1000);
      }
    };

    recognitionRef.current = recognition;

    return () => {
      if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
      try {
        recognition.abort();
      } catch {}
    };
  }, []);

  // Toggle Push-to-Talk (Click Core)
  const togglePushToTalk = () => {
    getAudioContext(); // Resume audio context on user click

    const recognition = recognitionRef.current;
    if (!recognition) {
      alert("Speech recognition is not supported in this browser. Please try Chrome or Edge.");
      return;
    }

    if (isListeningRef.current) {
      // Stop listening and process any pending transcript
      try {
        recognition.stop();
      } catch {}
      isListeningRef.current = false;
      setHudState("idle");
      if (currentTranscript.trim()) {
        executeCommand(currentTranscript, true);
      }
    } else {
      // Start listening
      try {
        playAudioChime("activate");
        setHudState("listening");
        setCurrentTranscript("");
        recognition.start();
      } catch (e) {
        console.warn("Recognition start notice:", e);
      }
    }
  };

  // Toggle Hands-Free Wake Word Mode
  const toggleWakeWord = () => {
    getAudioContext();
    const next = !isWakeWordActive;
    setIsWakeWordActive(next);
    isWakeWordRef.current = next;

    const recognition = recognitionRef.current;
    if (!recognition) return;

    if (next) {
      playAudioChime("activate");
      setMicStatusMsg("Wake Word mode activated. Listening for 'Hey Jarvis'...");
      if (!isListeningRef.current) {
        try {
          recognition.start();
        } catch {}
      }
    } else {
      setMicStatusMsg("Wake Word mode disabled. Click the Core to speak.");
      if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
      if (isListeningRef.current) {
        try {
          recognition.stop();
        } catch {}
      }
      setHudState("idle");
    }
  };

  // Keyboard shortcut: Spacebar toggles push-to-talk when not typing in input
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = document.activeElement?.tagName.toLowerCase();
      if (e.code === "Space" && activeTag !== "input" && activeTag !== "textarea") {
        e.preventDefault();
        togglePushToTalk();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Arc-Reactor Holographic Canvas Animation (Optimized: fixed dimensions, zero layout thrashing)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Set fixed canvas dimensions ONCE
    canvas.width = 380;
    canvas.height = 380;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let angle = 0;
    let pulse = 0;

    const render = () => {
      const width = 380;
      const height = 380;
      const centerX = width / 2;
      const centerY = height / 2;

      ctx.clearRect(0, 0, width, height);

      const currentState = hudStateRef.current;
      angle += currentState === "thinking" ? 0.045 : currentState === "listening" ? 0.03 : 0.015;
      pulse += 0.04;
      const pulseScale = Math.sin(pulse) * 4;

      let primaryColor = "rgba(0, 240, 255, ";
      let glowColor = "#00f0ff";
      if (currentState === "thinking") {
        primaryColor = "rgba(255, 185, 0, ";
        glowColor = "#ffb900";
      } else if (currentState === "speaking") {
        primaryColor = "rgba(30, 144, 255, ";
        glowColor = "#1e90ff";
      } else if (currentState === "listening") {
        primaryColor = "rgba(0, 255, 170, ";
        glowColor = "#00ffaa";
      }

      ctx.save();
      ctx.shadowBlur = 14;
      ctx.shadowColor = glowColor;

      // Outer Segmented Ring
      ctx.beginPath();
      ctx.arc(centerX, centerY, 150, 0, Math.PI * 2);
      ctx.strokeStyle = primaryColor + "0.15)";
      ctx.lineWidth = 1;
      ctx.stroke();

      // Outer Rotating Arc Segments
      const segments = 12;
      for (let i = 0; i < segments; i++) {
        const segAngle = angle + (i * Math.PI * 2) / segments;
        ctx.beginPath();
        ctx.arc(centerX, centerY, 140, segAngle, segAngle + 0.28);
        ctx.strokeStyle = primaryColor + (i % 2 === 0 ? "0.85)" : "0.35)");
        ctx.lineWidth = 3;
        ctx.stroke();
      }

      // Middle Ring with Tech Tick Marks
      ctx.beginPath();
      ctx.arc(centerX, centerY, 115, 0, Math.PI * 2);
      ctx.strokeStyle = primaryColor + "0.25)";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      const numTicks = 36;
      for (let i = 0; i < numTicks; i++) {
        const tickAngle = -angle * 0.75 + (i * Math.PI * 2) / numTicks;
        const r1 = 110;
        const r2 = i % 3 === 0 ? 122 : 116;
        ctx.beginPath();
        ctx.moveTo(centerX + Math.cos(tickAngle) * r1, centerY + Math.sin(tickAngle) * r1);
        ctx.lineTo(centerX + Math.cos(tickAngle) * r2, centerY + Math.sin(tickAngle) * r2);
        ctx.strokeStyle = primaryColor + (i % 3 === 0 ? "0.8)" : "0.25)");
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Inner Counter-Rotating Bracket Ring
      for (let i = 0; i < 4; i++) {
        const bracketAngle = -angle * 1.2 + (i * Math.PI) / 2;
        ctx.beginPath();
        ctx.arc(centerX, centerY, 85, bracketAngle, bracketAngle + Math.PI / 4);
        ctx.strokeStyle = primaryColor + "0.7)";
        ctx.lineWidth = 4;
        ctx.stroke();
      }

      // Core Glowing Arc Reactor Center
      const coreRadius = Math.max(
        30,
        42 + pulseScale + (currentState === "speaking" ? Math.sin(pulse * 3) * 8 : 0)
      );
      const gradient = ctx.createRadialGradient(centerX, centerY, 5, centerX, centerY, coreRadius);
      gradient.addColorStop(0, primaryColor + "1)");
      gradient.addColorStop(0.4, primaryColor + "0.55)");
      gradient.addColorStop(1, primaryColor + "0)");

      ctx.beginPath();
      ctx.arc(centerX, centerY, coreRadius, 0, Math.PI * 2);
      ctx.fillStyle = gradient;
      ctx.fill();

      // Center Core Dot
      ctx.beginPath();
      ctx.arc(centerX, centerY, 14, 0, Math.PI * 2);
      ctx.fillStyle = primaryColor + "0.95)";
      ctx.fill();

      ctx.restore();

      animationFrameId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  const handleFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (commandInput.trim()) {
      executeCommand(commandInput, false);
    }
  };

  return (
    <div className="jarvis-hud-container">
      {/* Top Telemetry Header */}
      <div className="jarvis-top-bar">
        <div className="jarvis-brand">
          <span className="jarvis-status-led" data-state={hudState}></span>
          <div>
            <div className="jarvis-title">J.A.R.V.I.S.</div>
            <div className="jarvis-subtitle">JUST A RATHER VERY INTELLIGENT SYSTEM · MARK VII</div>
          </div>
        </div>

        <div className="jarvis-telemetry-strip">
          <div className="telemetry-pill">
            <span className="pill-label">CPU</span>
            <span className="pill-val">{telemetry?.cpu_percent ? `${telemetry.cpu_percent}%` : "NOMINAL"}</span>
          </div>
          <div className="telemetry-pill">
            <span className="pill-label">RAM</span>
            <span className="pill-val">
              {telemetry?.memory_used_gb ? `${telemetry.memory_used_gb} / ${telemetry.memory_total_gb} GB` : "ACTIVE"}
            </span>
          </div>
          <div className="telemetry-pill">
            <span className="pill-label">POWER</span>
            <span className="pill-val">{telemetry?.battery_percent ? `${telemetry.battery_percent}%` : "100% AC"}</span>
          </div>
          <div className="telemetry-pill clock-pill">
            <span className="pill-val">{clock || "SYNCING..."}</span>
          </div>
        </div>

        <div className="jarvis-controls-strip">
          <button
            type="button"
            className={`hud-toggle-btn ${isWakeWordActive ? "active" : ""}`}
            onClick={toggleWakeWord}
            title="Toggle Hands-Free 'Hey Jarvis' listening"
          >
            {isWakeWordActive ? "◉ WAKE WORD: ON" : "○ WAKE WORD: OFF"}
          </button>
          <button
            type="button"
            className={`hud-toggle-btn ${isVoiceMuted ? "muted" : ""}`}
            onClick={() => setIsVoiceMuted(!isVoiceMuted)}
            title="Toggle Voice Speech Output"
          >
            {isVoiceMuted ? "🔇 VOICE: MUTED" : "🔊 VOICE: ON"}
          </button>
        </div>
      </div>

      {/* Main Grid: Visualizer Core + Terminal Log */}
      <div className="jarvis-main-viewport">
        {/* Left Column: Arc Reactor Core & Voice Controls */}
        <div className="jarvis-core-section">
          <div
            className="arc-reactor-wrapper"
            onClick={togglePushToTalk}
            title="Click to Talk / Spacebar"
          >
            <canvas ref={canvasRef} className="arc-reactor-canvas" />
            <div className="arc-reactor-overlay">
              <span className="core-state-badge" data-state={hudState}>
                {hudState.toUpperCase()}
              </span>
              <span className="core-hint">
                {hudState === "listening"
                  ? "LISTENING... (CLICK TO TRANSMIT)"
                  : hudState === "thinking"
                  ? "COMPUTING..."
                  : hudState === "speaking"
                  ? "SPEAKING..."
                  : "CLICK TO TALK (OR PRESS SPACE)"}
              </span>
            </div>
          </div>

          {/* Status & Live Voice Transcript Bar */}
          <div className="jarvis-live-transcript">
            <span className="transcript-prefix">VOICE:</span>
            <span className="transcript-text">
              {currentTranscript || micStatusMsg}
            </span>
          </div>

          {/* Quick Actions Chips */}
          <div className="jarvis-quick-chips">
            <span className="chips-title">RAPID DIRECTIVES:</span>
            <div className="chips-row">
              <button type="button" onClick={() => executeCommand("Hey Jarvis")}>
                ⚡ Wake Jarvis
              </button>
              <button type="button" onClick={() => executeCommand("System diagnostics")}>
                📊 Diagnostics
              </button>
              <button type="button" onClick={() => executeCommand("Open YouTube")}>
                ▶ YouTube
              </button>
              <button type="button" onClick={() => executeCommand("Open Google Chrome")}>
                🌐 Chrome
              </button>
              <button type="button" onClick={() => executeCommand("Mute audio")}>
                🔇 Mute
              </button>
              <button type="button" onClick={() => executeCommand("What time is it?")}>
                ⏱ Time
              </button>
              <button type="button" onClick={() => executeCommand("Lock workstation")}>
                🔒 Lock PC
              </button>
              <button type="button" onClick={() => executeCommand("Read my notes")}>
                📝 Notes
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Cyber Action Terminal & Directive Feed */}
        <div className="jarvis-terminal-section">
          <div className="terminal-header">
            <div className="terminal-title">
              <span className="terminal-dot"></span> DIRECTIVE LOG & SYSTEM PROTOCOLS
            </div>
            <div className="terminal-actions">
              <button
                type="button"
                className="terminal-clear"
                onClick={() =>
                  setLogs([
                    {
                      id: "cleared",
                      timestamp: new Date().toLocaleTimeString(),
                      type: "jarvis",
                      text: "Terminal log cleared, Sir. All background protocols running.",
                    },
                  ])
                }
              >
                CLEAR LOG
              </button>
            </div>
          </div>

          <div className="terminal-body">
            {logs.map((log) => (
              <div key={log.id} className={`terminal-entry entry-${log.type}`}>
                <div className="entry-meta">
                  <span className="entry-time">{log.timestamp}</span>
                  <span className="entry-sender">[{log.type === "user" ? "DEVANSH" : "JARVIS"}]</span>
                  {log.actionTag && <span className="entry-badge">{log.actionTag}</span>}
                </div>
                <div className="entry-content">{log.text}</div>
              </div>
            ))}
          </div>

          {/* Manual Input Command Bar */}
          <form className="terminal-input-bar" onSubmit={handleFormSubmit}>
            <span className="input-prompt">&gt;</span>
            <input
              type="text"
              placeholder="Enter voice command or type directive here (e.g. 'open notepad', 'volume up', 'search for AI news')..."
              value={commandInput}
              onChange={(e) => setCommandInput(e.target.value)}
            />
            <button type="submit" className="terminal-send-btn">
              TRANSMIT
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
