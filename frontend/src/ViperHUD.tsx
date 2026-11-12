import { FormEvent, useEffect, useRef, useState } from "react";

export type ViperStatus = "idle" | "armed" | "listening" | "thinking" | "speaking" | "error";
export type ViperTheme = "cyan" | "purple" | "amber" | "green";

function generateWavePath(
  width: number,
  height: number,
  volume: number,
  state: ViperStatus,
  layer: number
): string {
  const midY = height / 2;
  const isL = state === "listening";
  const isS = state === "speaking";
  const isT = state === "thinking";

  const amp = isL
    ? Math.max(4, Math.min(14, (volume / 100) * 13 + 3))
    : isS
    ? 9
    : isT
    ? 5
    : 2;

  const points: [number, number][] = [];
  const steps = 24;
  const t = Date.now() * 0.006;
  const phase = layer === 1 ? t : t * 1.4 + 1.2;
  const freq = layer === 1 ? 0.07 : 0.09;

  for (let i = 0; i <= steps; i++) {
    const x = (i / steps) * width;
    const env = Math.sin((i / steps) * Math.PI);
    const y = midY + Math.sin(x * freq + phase) * amp * env;
    points.push([x, y]);
  }

  return points.reduce((acc, [x, y], idx) => {
    return idx === 0 ? `M ${x.toFixed(1)} ${y.toFixed(1)}` : `${acc} L ${x.toFixed(1)} ${y.toFixed(1)}`;
  }, "");
}

interface QuickAction {
  id: string;
  label: string;
  command: string;
  icon: string;
  category: "all" | "apps" | "system" | "web";
}

const DEFAULT_ACTIONS: QuickAction[] = [
  { id: "sys", label: "System status", command: "check my system", icon: "⚡", category: "system" },
  { id: "yt", label: "Open YouTube", command: "Open YouTube", icon: "▶", category: "web" },
  { id: "chrome", label: "Open Chrome", command: "Open Google Chrome", icon: "🌐", category: "apps" },
  { id: "time", label: "What time is it?", command: "What time is it?", icon: "⏱", category: "system" },
];

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
  type: "user" | "viper" | "action";
  text: string;
  actionTag?: string;
}

interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
}

function loadConversationHistory(): ConversationMessage[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem("viperConversationHistory") || "[]");
    if (!Array.isArray(saved)) return [];
    return saved
      .filter((item): item is ConversationMessage =>
        item && (item.role === "user" || item.role === "assistant") && typeof item.content === "string"
      )
      .slice(-20);
  } catch {
    return [];
  }
}

function prepareSpeechText(rawText: string): string {
  return rawText
    .replace(/\bV\s*\.?\s*I\s*\.?\s*P\s*\.?\s*E\s*\.?\s*R\.?\b/gi, "Viper")
    .replace(/```[\s\S]*?```/g, " Code block omitted. ")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s*/gm, "")
    .replace(/^\s*(?:[-*+]\s+|\d+[.)]\s+)/gm, "")
    .replace(/\*\*|__|~~|`|[*_#]/g, "")
    .replace(/\s*--+\s*/g, ", ")
    .replace(/[—–]/g, ", ")
    .replace(/\b(?:e\.g\.|eg)\s*/gi, "for example ")
    .replace(/\b(?:i\.e\.|ie)\s*/gi, "that is ")
    .replace(/\bvs\.?\s/gi, "versus ")
    .replace(/[|]/g, ", ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s*\n+/g, ". ")
    .replace(/\s+([,.;!?])/g, "$1")
    .replace(/([,;])(?=\S)/g, "$1 ")
    .trim();
}

function scoreSpeechVoice(voice: SpeechSynthesisVoice): number {
  const language = voice.lang.toLowerCase().replace("_", "-");
  const name = voice.name.toLowerCase();
  let score = 0;
  if (/natural|neural|online/.test(name)) score += 100;
  if (/en-in/.test(language)) score += 30;
  else if (/en-gb/.test(language)) score += 20;
  else if (/en-us/.test(language)) score += 15;
  else if (/^en/.test(language)) score += 10;
  if (/compact|mobile/.test(name)) score -= 20;
  return score;
}

// Global AudioContext singleton
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

// Downsample audio to 16,000 Hz and auto-normalize gain
function prepareAudioForSTT(samples: Float32Array, inputRate: number): { pcm16k: Float32Array; rate: number } {
  const targetRate = 16000;
  let pcm: Float32Array;

  if (inputRate === targetRate) {
    pcm = new Float32Array(samples);
  } else {
    const ratio = inputRate / targetRate;
    const newLen = Math.round(samples.length / ratio);
    pcm = new Float32Array(newLen);
    for (let i = 0; i < newLen; i++) {
      const origIndex = i * ratio;
      const i1 = Math.floor(origIndex);
      const i2 = Math.min(i1 + 1, samples.length - 1);
      const frac = origIndex - i1;
      pcm[i] = samples[i1] * (1 - frac) + samples[i2] * frac;
    }
  }

  // Peak Normalization: amplify quiet earphone/mic audio up to 12x
  let maxAmp = 0;
  for (let i = 0; i < pcm.length; i++) {
    const abs = Math.abs(pcm[i]);
    if (abs > maxAmp) maxAmp = abs;
  }

  if (maxAmp > 0.003) {
    const boost = Math.min(0.85 / maxAmp, 12.0);
    for (let i = 0; i < pcm.length; i++) {
      pcm[i] *= boost;
    }
  }

  return { pcm16k: pcm, rate: targetRate };
}

// Convert Float32 audio samples into standard 16-bit PCM WAV Blob at 16kHz
function encodeWav(rawSamples: Float32Array, inputSampleRate: number): Blob {
  const { pcm16k: samples, rate: sampleRate } = prepareAudioForSTT(rawSamples, inputSampleRate);

  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  function writeString(offset: number, string: string) {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // Mono channel
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // 16-bit per sample
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

function playAudioChime(type: "activate" | "confirm" | "alert") {
  const ctx = getAudioContext();
  if (!ctx) return;

  try {
    if (type === "activate") {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.14);
      gain.gain.setValueAtTime(0.14, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.24);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.24);
    } else if (type === "confirm") {
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

interface ViperHUDProps {
  onNavigateModule?: (mod: string) => void;
  onStateChange?: (state: ViperStatus) => void;
}

export function ViperHUD({ onNavigateModule, onStateChange }: ViperHUDProps = {}) {
  const [hudState, setHudState] = useState<ViperStatus>("armed");

  useEffect(() => {
    onStateChange?.(hudState);
  }, [hudState, onStateChange]);
  const [isVoiceMuted, setIsVoiceMuted] = useState<boolean>(false);
  const [isWakeWordActive, setIsWakeWordActive] = useState<boolean>(true);
  const [micStatusMsg, setMicStatusMsg] = useState<string>("Standby active. Say 'Hey Viper' anytime.");
  const [commandInput, setCommandInput] = useState<string>("");
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
  const [activeMicLabel, setActiveMicLabel] = useState<string>("");
  const [speechVoices, setSpeechVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoiceURI, setSelectedVoiceURI] = useState<string>("ai:troy");
  const [liveVolume, setLiveVolume] = useState<number>(0);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [clock, setClock] = useState<string>("");
  const [logs, setLogs] = useState<ActionLogItem[]>([
    {
      id: "init",
      timestamp: new Date().toLocaleTimeString(),
      type: "viper",
      text: "V.I.P.E.R. Core Online. Say 'Hey Viper' or click Core to talk.",
      actionTag: "SYSTEM_READY",
    },
  ]);

  const [theme, setTheme] = useState<ViperTheme>(() => {
    return (localStorage.getItem("viper_theme") as ViperTheme) || "cyan";
  });
  const themeRef = useRef<ViperTheme>(theme);
  themeRef.current = theme;

  const [lastCommand, setLastCommand] = useState<string>("");

  const [quickActions, setQuickActions] = useState<QuickAction[]>(() => {
    try {
      const saved = localStorage.getItem("viper_quick_actions");
      return saved ? JSON.parse(saved) : DEFAULT_ACTIONS;
    } catch {
      return DEFAULT_ACTIONS;
    }
  });
  const [selectedCategory, setSelectedCategory] = useState<"all" | "apps" | "system" | "web">("all");
  const [isAddingAction, setIsAddingAction] = useState<boolean>(false);
  const [newActionLabel, setNewActionLabel] = useState<string>("");
  const [newActionCommand, setNewActionCommand] = useState<string>("");
  const [newActionCategory, setNewActionCategory] = useState<"apps" | "system" | "web">("apps");
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [wakeSensitivity, setWakeSensitivity] = useState<number>(1.0);

  // Expose setState('idle'|'listening'|'thinking'|'speaking'|'error') globally for debugging & triggers
  useEffect(() => {
    (window as any).setViperState = (state: ViperStatus) => {
      setHudState(state);
      if (state === "error") {
        setTimeout(() => {
          setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
        }, 1800);
      }
    };
    return () => {
      delete (window as any).setViperState;
    };
  }, []);

  const chatOrbCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const naturalAudioRef = useRef<HTMLAudioElement | null>(null);
  const naturalAudioUrlRef = useRef<string | null>(null);
  const ttsRequestRef = useRef<AbortController | null>(null);
  const hudStateRef = useRef<ViperStatus>("armed");
  hudStateRef.current = hudState;

  const isWakeWordActiveRef = useRef<boolean>(true);
  isWakeWordActiveRef.current = isWakeWordActive;

  // Real-time Audio & VAD Engine Refs
  const audioStreamRef = useRef<MediaStream | null>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const recordedChunksRef = useRef<Float32Array[]>([]);
  const isCapturingRef = useRef<boolean>(false);
  const captureModeRef = useRef<"wake" | "direct" | "interrupt">("direct");
  const hasSpokenRef = useRef<boolean>(false);
  const silenceFramesRef = useRef<number>(0);
  const totalFramesRef = useRef<number>(0);
  const speechOnsetChunksRef = useRef<Float32Array[]>([]);
  const ambientNoiseRef = useRef<number>(0.008);
  const audioLevelRef = useRef<number>(0);
  const pendingTranscriptRef = useRef<string>("");
  const isConversationActiveRef = useRef<boolean>(false);
  const isBargeInPendingRef = useRef<boolean>(false);
  const conversationHistoryRef = useRef<ConversationMessage[] | null>(null);
  if (conversationHistoryRef.current === null) {
    conversationHistoryRef.current = loadConversationHistory();
  }

  const rememberConversationTurn = (userText: string, assistantText: string) => {
    const entries = conversationHistoryRef.current || [];
    const next = [
      ...entries,
      { role: "user" as const, content: userText.trim() },
      { role: "assistant" as const, content: assistantText.trim() },
    ].filter((message) => message.content).slice(-20);
    conversationHistoryRef.current = next;
    try {
      sessionStorage.setItem("viperConversationHistory", JSON.stringify(next));
    } catch {
      // Conversation remains available in memory for the current page session.
    }
  };
  const userSelectedMicRef = useRef<boolean>(false);

  // Ref to allow safe callback from Web Audio onaudioprocess
  const finalizeAudioRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!("speechSynthesis" in window)) return;
    const refreshVoices = () => {
      setSpeechVoices(window.speechSynthesis.getVoices().filter((voice) => /^en([_-]|$)/i.test(voice.lang)));
    };
    refreshVoices();
    window.speechSynthesis.addEventListener("voiceschanged", refreshVoices);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", refreshVoices);
  }, []);

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

  // Enumerate microphones. Labels are often hidden until getUserMedia grants
  // permission, so actual headset selection happens after the first stream opens.
  useEffect(() => {
    if (!navigator.mediaDevices?.enumerateDevices) return;

    let disposed = false;
    const refreshDevices = async () => {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        if (disposed) return;
        const mics = devices.filter((device) => device.kind === "audioinput");
        setAudioDevices(mics);
        const headset = mics.find((mic) =>
          /headset|earphone|headphone|bluetooth|airpod|hands.?free|\busb\b/i.test(mic.label)
        );
        if (headset && !userSelectedMicRef.current) {
          setSelectedDeviceId(headset.deviceId);
        }
      } catch {
        // The microphone setup below reports permission and device errors.
      }
    };

    void refreshDevices();
    navigator.mediaDevices.addEventListener?.("devicechange", refreshDevices);
    return () => {
      disposed = true;
      navigator.mediaDevices.removeEventListener?.("devicechange", refreshDevices);
    };
  }, []);

  // Poll Telemetry
  useEffect(() => {
    const fetchTelemetry = () => {
      fetch("/api/viper/telemetry")
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

  // Instantly Abort Speech (Stop talking)
  const cancelSpeechOutput = () => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    ttsRequestRef.current?.abort();
    ttsRequestRef.current = null;
    if (naturalAudioRef.current) {
      naturalAudioRef.current.onended = null;
      naturalAudioRef.current.onerror = null;
      naturalAudioRef.current.pause();
      naturalAudioRef.current.removeAttribute("src");
      naturalAudioRef.current.load();
      naturalAudioRef.current = null;
    }
    if (naturalAudioUrlRef.current) {
      URL.revokeObjectURL(naturalAudioUrlRef.current);
      naturalAudioUrlRef.current = null;
    }
  };

  const abortSpeechAndReset = () => {
    cancelSpeechOutput();
    isCapturingRef.current = false;
    recordedChunksRef.current = [];
    if (isConversationActiveRef.current) {
      setHudState("listening");
      setMicStatusMsg("Speech stopped. I'm still listening for your next request.");
    } else {
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      setMicStatusMsg(
        isWakeWordActiveRef.current
          ? "Speech stopped, Sir. Standby active."
          : "Speech stopped, Sir. Click Core to speak."
      );
    }
    playAudioChime("alert");
  };

  const finishSpeechPlayback = () => {
    if (isBargeInPendingRef.current) return;
    if (isConversationActiveRef.current) {
      startConversationListening();
    } else {
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      setMicStatusMsg(
        isWakeWordActiveRef.current
          ? "Standby active. Say 'Viper' anytime."
          : "Click Core or press Space to speak."
      );
    }
  };

  const speakWithSystemVoice = (cleanText: string) => {
    if (!("speechSynthesis" in window)) {
      finishSpeechPlayback();
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleanText);
    const voices = window.speechSynthesis.getVoices();
    const englishVoices = voices.filter((voice) => /^en([_-]|$)/i.test(voice.lang));
    const nativeURI = selectedVoiceURI.startsWith("native:")
      ? selectedVoiceURI.slice("native:".length)
      : "";
    const chosenVoice =
      englishVoices.find((voice) => voice.voiceURI === nativeURI) ||
      [...englishVoices].sort((a, b) => scoreSpeechVoice(b) - scoreSpeechVoice(a))[0];
    if (chosenVoice) {
      utterance.voice = chosenVoice;
      utterance.lang = chosenVoice.lang;
    }
    utterance.pitch = 1;
    utterance.rate = 0.96;
    utterance.volume = 1;
    utterance.onstart = () => {
      setHudState("speaking");
      setMicStatusMsg("Speaking response...");
    };
    utterance.onend = finishSpeechPlayback;
    utterance.onerror = finishSpeechPlayback;
    window.speechSynthesis.speak(utterance);
  };

  // Use Groq's neural Orpheus voice by default; fall back to the selected system voice.
  const speakReply = async (text: string) => {
    const cleanText = prepareSpeechText(text).slice(0, 4000).trim();
    if (isVoiceMuted || !cleanText) {
      finishSpeechPlayback();
      return;
    }

    cancelSpeechOutput();
    if (!selectedVoiceURI.startsWith("ai:")) {
      speakWithSystemVoice(cleanText);
      return;
    }

    const controller = new AbortController();
    ttsRequestRef.current = controller;
    setHudState("speaking");
    setMicStatusMsg("Preparing natural voice...");
    let fallbackUsed = false;
    const fallback = () => {
      if (fallbackUsed || controller.signal.aborted) return;
      fallbackUsed = true;
      ttsRequestRef.current = null;
      setMicStatusMsg("Natural voice unavailable; using the system voice.");
      speakWithSystemVoice(cleanText);
    };

    try {
      const response = await fetch("/api/viper/speech", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: cleanText, voice: selectedVoiceURI.slice(3) }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Speech provider returned ${response.status}`);
      const audioBlob = await response.blob();
      if (controller.signal.aborted) return;

      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      naturalAudioUrlRef.current = audioUrl;
      naturalAudioRef.current = audio;
      const releaseAudio = () => {
        if (naturalAudioRef.current === audio) naturalAudioRef.current = null;
        if (naturalAudioUrlRef.current === audioUrl) {
          URL.revokeObjectURL(audioUrl);
          naturalAudioUrlRef.current = null;
        }
        ttsRequestRef.current = null;
      };
      audio.onended = () => {
        releaseAudio();
        finishSpeechPlayback();
      };
      audio.onerror = () => {
        releaseAudio();
        fallback();
      };
      await audio.play();
    } catch {
      if (controller.signal.aborted) return;
      if (naturalAudioRef.current) {
        naturalAudioRef.current.onended = null;
        naturalAudioRef.current.onerror = null;
        naturalAudioRef.current = null;
      }
      if (naturalAudioUrlRef.current) {
        URL.revokeObjectURL(naturalAudioUrlRef.current);
        naturalAudioUrlRef.current = null;
      }
      fallback();
    }
  };

  // Put VIPER into Active Listening state (Turns Core Green & starts recording command)
  const startActiveCommandListening = (status = "🟢 V.I.P.E.R. ACTIVATED — listening for your command now.") => {
    const ctx = getAudioContext();
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});

    playAudioChime("activate");
    recordedChunksRef.current = [];
    hasSpokenRef.current = false;
    silenceFramesRef.current = 0;
    totalFramesRef.current = 0;
    speechOnsetChunksRef.current = [];
    captureModeRef.current = "direct";
    isConversationActiveRef.current = true;
    isCapturingRef.current = true;
    setHudState("listening"); // TURNS CORE NEON GREEN!
    setMicStatusMsg(status);
  };

  // Leave the mic armed for the next turn without buffering silence.
  const startConversationListening = () => {
    recordedChunksRef.current = [];
    hasSpokenRef.current = false;
    silenceFramesRef.current = 0;
    totalFramesRef.current = 0;
    speechOnsetChunksRef.current = [];
    captureModeRef.current = "direct";
    isCapturingRef.current = false;
    setHudState("listening");
    setMicStatusMsg("🟢 V.I.P.E.R. is listening. Continue speaking, or say 'stop listening' to leave conversation mode.");
  };

  // Submit Text Command to Backend
  const executeTextCommand = async (commandText: string) => {
    const trimmed = commandText.trim();
    if (!trimmed) return;
    setLastCommand(trimmed);

    if (trimmed.toLowerCase() === "stop") {
      abortSpeechAndReset();
      return;
    }

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
    setHudState("thinking");
    setMicStatusMsg("Computing directive with AI engine...");

    try {
      const res = await fetch("/api/viper/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          voice_mode: false,
          history: conversationHistoryRef.current || [],
        }),
      });

      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      playAudioChime("confirm");

      const viperLogId = Math.random().toString(36).substring(7);
      setLogs((prev) => [
        ...prev,
        {
          id: viperLogId,
          timestamp: new Date().toLocaleTimeString(),
          type: "viper",
          text: data.reply,
          actionTag: data.action_taken ? data.action_taken.toUpperCase() : undefined,
        },
      ]);

      if (data.system_status) setTelemetry(data.system_status);
      rememberConversationTurn(trimmed, data.audio_text || data.reply);

      const lower = trimmed.toLowerCase();
      if (lower.includes("show tasks") || lower.includes("open lifeos")) {
        onNavigateModule?.("LifeOS");
      }

      speakReply(data.audio_text || data.reply);
    } catch (err: any) {
      playAudioChime("alert");
      setLogs((prev) => [
        ...prev,
        {
          id: Math.random().toString(36).substring(7),
          timestamp: new Date().toLocaleTimeString(),
          type: "viper",
          text: `Command error: ${err.message || "Failed to execute"}. Please verify backend status, Sir.`,
          actionTag: "ERROR",
        },
      ]);
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      setMicStatusMsg(
        isWakeWordActiveRef.current
          ? "Standby active. Say 'Hey Viper' anytime."
          : "Click Core or press Space to speak."
      );
    }
  };

  // Transmit Audio to Backend (/api/viper/voice)
  const transmitRecordedAudio = async (wavBlob: Blob, mode: "wake" | "direct" | "interrupt") => {
    const isWakeMode = mode === "wake";
    const isInterruptMode = mode === "interrupt";
    if (!isWakeMode && !isInterruptMode) {
      setHudState("thinking");
      setMicStatusMsg("Processing voice directive with Groq Whisper...");
    }

    try {
      const formData = new FormData();
      formData.append("file", wavBlob, "command.wav");
      formData.append("history_json", JSON.stringify(conversationHistoryRef.current || []));
      const continuation = mode === "direct" ? pendingTranscriptRef.current : "";
      const continuationParam = continuation
        ? `&continuation_text=${encodeURIComponent(continuation)}`
        : "";

      const res = await fetch(`/api/viper/voice?wake_mode=${isWakeMode ? "true" : "false"}&interrupt_mode=${isInterruptMode ? "true" : "false"}${continuationParam}`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error(`Voice server returned ${res.status}`);
      const data = await res.json();

      // A spoken stop is monitored while TTS is playing. Handle it before
      // any normal response path so V.I.P.E.R. does not speak over it.
      if (isInterruptMode) {
        isBargeInPendingRef.current = false;
        if (data.interrupted) {
          isConversationActiveRef.current = true;
          setHudState("thinking");
          setMicStatusMsg("I heard you. Let me answer that...");
          if (data.transcript) {
            setLogs((prev) => [
              ...prev,
              {
                id: Math.random().toString(36).substring(7),
                timestamp: new Date().toLocaleTimeString(),
                type: "user",
                text: data.transcript,
              },
            ]);
          }
        } else {
          if (data.action_taken === "STOP_LISTENING") isConversationActiveRef.current = false;
          if (data.action_taken === "STOP_DIRECTIVE" || data.action_taken === "STOP_LISTENING") {
            abortSpeechAndReset();
          } else if (isConversationActiveRef.current) {
            startConversationListening();
          }
          return;
        }
      }

      if (data.action_taken === "CONTINUE_LISTENING") {
        pendingTranscriptRef.current = data.transcript || continuation;
        startActiveCommandListening("🟢 Still listening — please finish your request.");
        return;
      }

      if (data.action_taken === "ECHO_IGNORED") {
        pendingTranscriptRef.current = "";
        if (isConversationActiveRef.current) startConversationListening();
        else setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
        return;
      }

      // Case A: In wake_mode and utterance was not directed at V.I.P.E.R.
      // Stay COMPLETELY silent and IDLE. Zero flicker, zero interruption!
      if (isWakeMode && data.action_taken === "WAKE_IGNORED") {
        pendingTranscriptRef.current = "";
        setHudState("armed");
        setMicStatusMsg("Standby active. Say 'Hey Viper' anytime.");
        return;
      }

      // Case B: User said ONLY "Hey Viper" -> AWAKEN & TURN GREEN IMMEDIATELY!
      if (data.action_taken === "WAKE_CONFIRMED") {
        pendingTranscriptRef.current = "";
        const viperLogId = Math.random().toString(36).substring(7);
        setLogs((prev) => [
          ...prev,
          {
            id: viperLogId,
            timestamp: new Date().toLocaleTimeString(),
            type: "viper",
            text: "Yes, Sir? Standing by for your directive.",
            actionTag: "WAKE_CONFIRMED",
          },
        ]);

        // Instantly transition into active listening without delay!
        startActiveCommandListening();
        return;
      }

      if (data.action_taken === "NO_SPEECH_DETECTED") {
        pendingTranscriptRef.current = "";
        if (isConversationActiveRef.current) {
          startConversationListening();
          return;
        }
        if (!isWakeMode) {
          playAudioChime("alert");
          setLogs((prev) => [
            ...prev,
            {
              id: Math.random().toString(36).substring(7),
              timestamp: new Date().toLocaleTimeString(),
              type: "viper",
              text: "I couldn't hear any distinct directive, Sir. Please try speaking again.",
              actionTag: "NO_SPEECH_DETECTED",
            },
          ]);
        }
        setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
        setMicStatusMsg(
          isWakeWordActiveRef.current
            ? "Standby active. Say 'Hey Viper' anytime."
            : "Click Core to retry."
        );
        return;
      }

      if (data.action_taken === "STOP_DIRECTIVE") {
        isConversationActiveRef.current = false;
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
        setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
        setMicStatusMsg(
          isWakeWordActiveRef.current
            ? "Conversation ended. Say 'Viper' to start again."
            : "Conversation ended. Click Core or press Space to start again."
        );
        return;
      }

      // Case C: Direct command or "Hey Viper + [command]" executed!
      pendingTranscriptRef.current = "";
      isConversationActiveRef.current = true;
      const userTurn = String(data.transcript || "").trim();
      if (userTurn) setLastCommand(userTurn);
      const assistantTurn = String(data.audio_text || data.reply || "").trim();
      if (userTurn && assistantTurn) rememberConversationTurn(userTurn, assistantTurn);
      playAudioChime("confirm");

      const viperLogId = Math.random().toString(36).substring(7);
      setLogs((prev) => [
        ...prev,
        {
          id: viperLogId,
          timestamp: new Date().toLocaleTimeString(),
          type: "viper",
          text: data.reply,
          actionTag: data.action_taken ? data.action_taken.toUpperCase() : "VOICE_COMMAND",
        },
      ]);

      if (data.system_status) setTelemetry(data.system_status);

      speakReply(data.audio_text || data.reply);
    } catch (err: any) {
      if (isInterruptMode) {
        isBargeInPendingRef.current = false;
        if (isConversationActiveRef.current) startConversationListening();
        return;
      }
      if (!isWakeMode) {
        playAudioChime("alert");
        setLogs((prev) => [
          ...prev,
          {
            id: Math.random().toString(36).substring(7),
            timestamp: new Date().toLocaleTimeString(),
            type: "viper",
            text: `Voice notice: ${err.message || "Could not process audio"}.`,
            actionTag: "VOICE_ERROR",
          },
        ]);
      }
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      setMicStatusMsg(
        isWakeWordActiveRef.current
          ? "Standby active. Say 'Hey Viper' anytime."
          : "Click Core to retry."
      );
    }
  };

  // Finalize audio buffer and stop current capture
  const finalizeAudioAndSend = () => {
    if (!isCapturingRef.current) return;
    isCapturingRef.current = false;
    audioLevelRef.current = 0;

    const mode = captureModeRef.current;
    const isWake = mode === "wake";
    const chunks = recordedChunksRef.current;
    recordedChunksRef.current = [];

    if (chunks.length === 0 || (!hasSpokenRef.current && !isWake)) {
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      setMicStatusMsg(
        isWakeWordActiveRef.current
          ? "Standby active. Say 'Hey Viper' anytime."
          : "Click Core or press Space to Speak."
      );
      return;
    }

    let totalLength = 0;
    for (const chunk of chunks) totalLength += chunk.length;

    const mergedSamples = new Float32Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
      mergedSamples.set(chunk, offset);
      offset += chunk.length;
    }

    const ctx = getAudioContext();
    const sampleRate = ctx ? ctx.sampleRate : 44100;
    const wavBlob = encodeWav(mergedSamples, sampleRate);

    if (mode === "interrupt") {
      setHudState("thinking");
      setMicStatusMsg("Processing your interruption...");
    }
    transmitRecordedAudio(wavBlob, mode);
  };

  finalizeAudioRef.current = finalizeAudioAndSend;

  // Audio Pipeline & VAD Stream Setup
  useEffect(() => {
    let isCancelled = false;
    const ctx = getAudioContext();
    if (!ctx) return;

    const setupMicPipeline = async () => {
      try {
        if (audioStreamRef.current) {
          audioStreamRef.current.getTracks().forEach((t) => t.stop());
        }
        if (scriptProcessorRef.current) {
          try {
            scriptProcessorRef.current.disconnect();
          } catch {}
        }

        const audioConstraints: MediaTrackConstraints = {
          channelCount: 1,
          autoGainControl: true,
          echoCancellation: true,
          noiseSuppression: true,
        };
        if (selectedDeviceId) {
          audioConstraints.deviceId = { exact: selectedDeviceId };
        }

        const stream = await navigator.mediaDevices.getUserMedia({
          audio: audioConstraints,
        });

        if (isCancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        audioStreamRef.current = stream;
        const activeTrack = stream.getAudioTracks()[0];
        const activeSettings = activeTrack?.getSettings();
        const activeLabel = activeTrack?.label || "Default microphone";
        setActiveMicLabel(activeLabel);

        // Permission reveals real device labels. Prefer a named headset when
        // available; otherwise pin the device the browser actually opened.
        try {
          const devices = await navigator.mediaDevices.enumerateDevices();
          const mics = devices.filter((device) => device.kind === "audioinput");
          setAudioDevices(mics);
          if (!userSelectedMicRef.current) {
            const headset = mics.find((mic) =>
              /headset|earphone|headphone|bluetooth|airpod|hands.?free|\busb\b/i.test(mic.label)
            );
            const preferredDeviceId = headset?.deviceId || activeSettings?.deviceId;
            if (preferredDeviceId) setSelectedDeviceId(preferredDeviceId);
          }
        } catch {
          // Keep the active stream; the device selector can still be used manually.
        }

        const source = ctx.createMediaStreamSource(stream);
        const processor = ctx.createScriptProcessor(4096, 1, 1);
        scriptProcessorRef.current = processor;

        processor.onaudioprocess = (e) => {
          // Keep the processor active without routing microphone input to speakers.
          e.outputBuffer.getChannelData(0).fill(0);

          // Don't collect commands while a request is processing. During speech,
          // keep a short VAD capture active so a spoken "stop" can interrupt TTS.
          if (hudStateRef.current === "thinking") {
            return;
          }

          const inputData = e.inputBuffer.getChannelData(0);

          // Compute Root Mean Square (RMS) energy
          let sum = 0;
          for (let i = 0; i < inputData.length; i++) {
            sum += inputData[i] * inputData[i];
          }
          const rms = Math.sqrt(sum / inputData.length);
          let zeroCrossings = 0;
          for (let i = 1; i < inputData.length; i++) {
            if ((inputData[i - 1] >= 0) !== (inputData[i] >= 0)) zeroCrossings++;
          }
          const zeroCrossingRate = zeroCrossings / inputData.length;
          // Broadly reject steady tones (horns) and isolated broadband clicks.
          const speechLikeFrame = zeroCrossingRate >= 0.015 && zeroCrossingRate <= 0.32;
          audioLevelRef.current = rms;
          setLiveVolume(Math.min(100, Math.round(rms * 500)));

          // Dynamically track background noise floor smoothly
          ambientNoiseRef.current = ambientNoiseRef.current * 0.94 + rms * 0.06;

          // Calibrated speech trigger thresholds
          const wakeSpeechThreshold = Math.max(0.020, ambientNoiseRef.current * 2.0);
          const directSpeechThreshold = Math.max(0.014, ambientNoiseRef.current * 1.5);
          const interruptSpeechThreshold = Math.max(0.008, ambientNoiseRef.current * 1.3);
          const silenceThreshold = Math.max(0.010, ambientNoiseRef.current * 1.25);

          if (hudStateRef.current === "speaking") {
            if (!isCapturingRef.current) {
              if (rms > interruptSpeechThreshold && speechLikeFrame) {
                speechOnsetChunksRef.current.push(new Float32Array(inputData));
                if (speechOnsetChunksRef.current.length > 4) speechOnsetChunksRef.current.shift();
                if (speechOnsetChunksRef.current.length >= 3) {
                  isCapturingRef.current = true;
                  captureModeRef.current = "interrupt";
                  hasSpokenRef.current = true;
                  silenceFramesRef.current = 0;
                  totalFramesRef.current = speechOnsetChunksRef.current.length;
                  recordedChunksRef.current = speechOnsetChunksRef.current;
                  speechOnsetChunksRef.current = [];
                  isBargeInPendingRef.current = true;
                  setMicStatusMsg("I heard you. Interrupting my response...");
                  cancelSpeechOutput();
                }
              } else {
                speechOnsetChunksRef.current = [];
              }
              return;
            }
            if (isCapturingRef.current && captureModeRef.current === "interrupt") {
              recordedChunksRef.current.push(new Float32Array(inputData));
              totalFramesRef.current++;
              if (rms > interruptSpeechThreshold && speechLikeFrame) silenceFramesRef.current = 0;
              else if (rms < silenceThreshold) silenceFramesRef.current++;
              // Let a short hesitation between words pass before submitting an
              // interruption; ScriptProcessor buffers are about 85–93 ms.
              if (silenceFramesRef.current >= 14 || totalFramesRef.current >= 140) {
                finalizeAudioRef.current();
              }
            }
            return;
          }

          // In conversation mode, wait for speech onset without recording silence.
          if (
            isConversationActiveRef.current &&
            hudStateRef.current === "listening" &&
            !isCapturingRef.current
          ) {
            const conversationThreshold = Math.max(0.009, ambientNoiseRef.current * 1.35);
            if (rms > conversationThreshold && speechLikeFrame) {
              speechOnsetChunksRef.current.push(new Float32Array(inputData));
              if (speechOnsetChunksRef.current.length > 4) speechOnsetChunksRef.current.shift();
              if (speechOnsetChunksRef.current.length >= 3) {
                isCapturingRef.current = true;
                captureModeRef.current = "direct";
                hasSpokenRef.current = true;
                silenceFramesRef.current = 0;
                totalFramesRef.current = speechOnsetChunksRef.current.length;
                recordedChunksRef.current = speechOnsetChunksRef.current;
                speechOnsetChunksRef.current = [];
                setMicStatusMsg("🎙️ Hearing you — speak naturally; I’m following the conversation.");
              }
            } else {
              speechOnsetChunksRef.current = [];
            }
            return;
          }

          // 1. Silent Hands-Free Wake-Word Standby Listening
          // Buffers silently in memory until "Hey Viper" is confirmed
          if (
            isWakeWordActiveRef.current &&
            !isCapturingRef.current &&
            hudStateRef.current === "armed"
          ) {
            if (rms > wakeSpeechThreshold && speechLikeFrame) {
              speechOnsetChunksRef.current.push(new Float32Array(inputData));
              if (speechOnsetChunksRef.current.length > 4) speechOnsetChunksRef.current.shift();
              if (speechOnsetChunksRef.current.length >= 3) {
                isCapturingRef.current = true;
                captureModeRef.current = "wake";
                hasSpokenRef.current = true;
                silenceFramesRef.current = 0;
                totalFramesRef.current = speechOnsetChunksRef.current.length;
                recordedChunksRef.current = speechOnsetChunksRef.current;
                speechOnsetChunksRef.current = [];
                setMicStatusMsg("Wake phrase detected — checking for 'Hey Viper'...");
              }
            } else {
              speechOnsetChunksRef.current = [];
            }
            return;
          }

          // 2. Actively Capturing Voice (Direct Push-To-Talk or Background Wake phrase)
          if (isCapturingRef.current) {
            recordedChunksRef.current.push(new Float32Array(inputData));
            totalFramesRef.current++;

            const currentSpeechThreshold = captureModeRef.current === "wake"
              ? wakeSpeechThreshold
              : captureModeRef.current === "interrupt"
              ? interruptSpeechThreshold
              : directSpeechThreshold;

            if (rms > currentSpeechThreshold && speechLikeFrame) {
              if (!hasSpokenRef.current) {
                speechOnsetChunksRef.current.push(new Float32Array(inputData));
                if (speechOnsetChunksRef.current.length > 4) speechOnsetChunksRef.current.shift();
                if (speechOnsetChunksRef.current.length >= 3) {
                  hasSpokenRef.current = true;
                  speechOnsetChunksRef.current = [];
                }
              }
              if (hasSpokenRef.current) {
                silenceFramesRef.current = 0;
                if (captureModeRef.current === "direct") {
                  setMicStatusMsg("🎙️ Hearing your voice... Pause when finished or click Core.");
                }
              }
            } else if (rms < silenceThreshold) {
              if (hasSpokenRef.current) {
                silenceFramesRef.current++;
              }
            }

            // End the turn only after sustained silence. Calculate from actual
            // audio buffer duration so a one-second hesitation does not submit
            // the command, even when the browser's audio sample rate differs.
            const silenceDurationMs =
              (silenceFramesRef.current * inputData.length * 1000) / ctx.sampleRate;
            const silenceLimitMs = captureModeRef.current === "wake" ? 2800 : 3200;
            if (hasSpokenRef.current && silenceDurationMs >= silenceLimitMs) {
              finalizeAudioRef.current();
              return;
            }

            // SAFETY MAX LIMIT:
            // Keep wake detection responsive; command clips can run for about 13 seconds.
            const maxFrameLimit = captureModeRef.current === "wake" ? 35 : 320;
            if (totalFramesRef.current >= maxFrameLimit) {
              finalizeAudioRef.current();
              return;
            }

            // AUTO-CANCEL for Direct click if user did not speak for 4.5 seconds
            if (
              captureModeRef.current === "direct" &&
              !hasSpokenRef.current &&
              totalFramesRef.current >= 48
            ) {
              isCapturingRef.current = false;
              recordedChunksRef.current = [];
              pendingTranscriptRef.current = "";
              if (isConversationActiveRef.current) {
                setHudState("listening");
                setMicStatusMsg("I’m still listening. Say your request whenever you’re ready.");
              } else {
                setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
                setMicStatusMsg(
                  isWakeWordActiveRef.current
                    ? "Standby active. Say 'Viper' anytime."
                    : "Click Core or press Space to Speak."
                );
              }
            }
          }
        };

        source.connect(processor);
        processor.connect(ctx.destination);
      } catch (err) {
        console.warn("Microphone initialization notice:", err);
        if (isCancelled) return;
        setActiveMicLabel("Microphone unavailable");
        setMicStatusMsg("Microphone unavailable. Check browser permission and select an input device.");
      }
    };

    setupMicPipeline();

    return () => {
      isCancelled = true;
      if (scriptProcessorRef.current) {
        try {
          scriptProcessorRef.current.disconnect();
        } catch {}
      }
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, [selectedDeviceId]);

  // Toggle Push-To-Talk Voice Input (Core Click / Spacebar)
  const toggleVoiceInput = () => {
    // If speaking, clicking the Core STOPS speech immediately!
    if (hudStateRef.current === "speaking") {
      abortSpeechAndReset();
      return;
    }

    if (isCapturingRef.current && captureModeRef.current === "direct") {
      // User clicked again: immediately stop and send!
      finalizeAudioAndSend();
    } else {
      startActiveCommandListening();
    }
  };

  // Toggle Wake-Word hands-free mode
  const toggleWakeWordMode = () => {
    const nextVal = !isWakeWordActive;
    setIsWakeWordActive(nextVal);
    isWakeWordActiveRef.current = nextVal;
    if (nextVal) {
      setHudState("armed");
      setMicStatusMsg("Standby active. Say 'Hey Viper' anytime.");
      playAudioChime("confirm");
    } else {
      if (hudStateRef.current === "armed") setHudState("idle");
      setMicStatusMsg("Wake word standby disabled. Click Core to speak.");
    }
  };

  // Keyboard shortcut: Spacebar toggles voice input, Escape cancels/stops speech
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = document.activeElement?.tagName.toLowerCase();
      if (e.code === "Escape") {
        abortSpeechAndReset();
        return;
      }
      if (e.code === "Space" && activeTag !== "input" && activeTag !== "textarea") {
        e.preventDefault();
        toggleVoiceInput();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Glowing Arc Reactor Orb Canvas (Claude Idea 1 & 2)
  // Dynamic scaling: ~180px in empty state -> ~48px in header when messages arrive
  useEffect(() => {
    const canvas = chatOrbCanvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let angle = 0;
    let pulse = 0;

    // 3D Orbital Rings relative configuration
    const orbitalRings = [
      { rRel: 0.82, tiltX: 1.05, tiltY: 0.42, speed: 0.016, nodes: 3 },
      { rRel: 0.92, tiltX: -0.80, tiltY: -0.65, speed: -0.013, nodes: 2 },
      { rRel: 0.70, tiltX: 1.25, tiltY: 0.88, speed: 0.021, nodes: 3 },
      { rRel: 1.00, tiltX: -0.40, tiltY: 1.15, speed: -0.018, nodes: 4 },
      { rRel: 0.56, tiltX: 0.86, tiltY: -0.42, speed: 0.027, nodes: 2 },
    ];

    const projectPoint = (
      x: number,
      y: number,
      z: number,
      rotX: number,
      rotY: number,
      rotZ: number,
      cx: number,
      cy: number,
      fov: number
    ) => {
      const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
      const y1 = y * cosX - z * sinX;
      const z1 = y * sinX + z * cosX;

      const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
      const x2 = x * cosY + z1 * sinY;
      const z2 = -x * sinY + z1 * cosY;

      const cosZ = Math.cos(rotZ), sinZ = Math.sin(rotZ);
      const x3 = x2 * cosZ - y1 * sinZ;
      const y3 = x2 * sinZ + y1 * cosZ;

      const scale = fov / (fov + z2);
      return {
        x: cx + x3 * scale,
        y: cy + y3 * scale,
        z: z2,
        scale,
      };
    };

    let lastW = 0;
    let lastH = 0;

    const render = () => {
      const width = canvas.clientWidth || 180;
      const height = canvas.clientHeight || 180;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);

      if (width !== lastW || height !== lastH) {
        lastW = width;
        lastH = height;
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }

      ctx.clearRect(0, 0, width, height);

      const centerX = width / 2;
      const centerY = height / 2;
      const baseR = Math.min(width, height) * 0.40;
      const fov = baseR * 2.8;

      const currentState = hudStateRef.current;
      const micLevel = audioLevelRef.current || 0;
      const dynamicBoost = micLevel * (baseR * 0.4);

      const speedMult = currentState === "thinking"
        ? 2.8
        : currentState === "listening"
        ? 1.5 + micLevel * 2.2
        : currentState === "error"
        ? 0.4
        : 1.0;

      angle += (currentState === "thinking" ? 0.048 : currentState === "listening" ? 0.025 + micLevel * 0.1 : 0.014) * speedMult;
      pulse += 0.04;
      const pulseScale = Math.sin(pulse) * (baseR * 0.04) + dynamicBoost;

      const curTheme = themeRef.current;
      let primaryColor = "rgba(0, 240, 255, ";
      let glowColor = "#00f0ff";
      let hotspotColor = "#ffffff";

      if (curTheme === "purple") {
        primaryColor = "rgba(192, 132, 252, ";
        glowColor = "#c084fc";
        hotspotColor = "#fdf4ff";
      } else if (curTheme === "amber") {
        primaryColor = "rgba(245, 158, 11, ";
        glowColor = "#f59e0b";
        hotspotColor = "#fffbeb";
      } else if (curTheme === "green") {
        primaryColor = "rgba(0, 255, 170, ";
        glowColor = "#00ffaa";
        hotspotColor = "#ecfdf5";
      }

      // Dynamic State-based color overrides
      if (currentState === "error") {
        primaryColor = "rgba(239, 68, 68, ";
        glowColor = "#ef4444";
        hotspotColor = "#fff1f2";
      } else if (currentState === "thinking") {
        primaryColor = "rgba(255, 185, 0, ";
        glowColor = "#ffb900";
        hotspotColor = "#fff8e1";
      } else if (currentState === "speaking") {
        primaryColor = curTheme === "purple" ? "rgba(232, 121, 249, " : "rgba(56, 189, 248, ";
        glowColor = curTheme === "purple" ? "#e879f9" : "#38bdf8";
        hotspotColor = "#f0f9ff";
      } else if (currentState === "listening") {
        primaryColor = curTheme === "green" ? "rgba(52, 211, 153, " : "rgba(0, 255, 170, ";
        glowColor = "#00ffaa";
        hotspotColor = "#e6fff4";
      }

      // 1. Ambient Dynamic Core Glow
      const ambientGrad = ctx.createRadialGradient(centerX, centerY, 2, centerX, centerY, baseR * 1.25);
      ambientGrad.addColorStop(0, primaryColor + (currentState === "error" ? "0.45)" : "0.35)"));
      ambientGrad.addColorStop(0.35, primaryColor + "0.15)");
      ambientGrad.addColorStop(0.7, primaryColor + "0.03)");
      ambientGrad.addColorStop(1, "rgba(2, 6, 14, 0)");
      ctx.fillStyle = ambientGrad;
      ctx.fillRect(0, 0, width, height);

      ctx.save();
      ctx.shadowBlur = Math.max(6, baseR * 0.22 + dynamicBoost * 0.4);
      ctx.shadowColor = glowColor;

      // 2. Radial Starburst Photon Beams
      const rayCount = width > 80 ? 42 : 20;
      for (let i = 0; i < rayCount; i++) {
        const rayAngle = angle * 0.14 + (i * Math.PI * 2) / rayCount;
        const isMajor = i % (width > 80 ? 6 : 4) === 0;
        const isSemi = i % 2 === 0;

        const rStart = baseR * 0.22 + Math.sin(pulse * 2.5 + i * 0.6) * (baseR * 0.02);
        const harmonic = Math.abs(Math.sin(i * 3.1 + pulse * 1.2)) * (baseR * 0.12);
        const stateBoost = currentState === "listening"
          ? dynamicBoost * 1.2
          : currentState === "speaking"
          ? Math.sin(pulse * 4 + i) * (baseR * 0.15) + (baseR * 0.1)
          : dynamicBoost * 0.3;

        const rayLen = (isMajor ? baseR * 0.45 : isSemi ? baseR * 0.28 : baseR * 0.16) + harmonic + stateBoost;
        const rEnd = Math.min(baseR * 1.2, rStart + rayLen);

        const cosA = Math.cos(rayAngle);
        const sinA = Math.sin(rayAngle);

        ctx.beginPath();
        ctx.moveTo(centerX + cosA * rStart, centerY + sinA * rStart);
        ctx.lineTo(centerX + cosA * rEnd, centerY + sinA * rEnd);
        ctx.strokeStyle = primaryColor + (isMajor ? "0.9)" : isSemi ? "0.5)" : "0.22)");
        ctx.lineWidth = Math.max(0.6, (isMajor ? 1.6 : isSemi ? 1.0 : 0.6) * (baseR / 60));
        ctx.stroke();

        if (width > 60) {
          ctx.beginPath();
          ctx.arc(centerX + cosA * rEnd, centerY + sinA * rEnd, Math.max(0.8, (isMajor ? 2.0 : 1.0) * (baseR / 60)), 0, Math.PI * 2);
          ctx.fillStyle = isMajor ? hotspotColor : primaryColor + "0.85)";
          ctx.fill();
        }
      }

      // 3. Technical Outer Compass Ring
      const outerR = baseR * 1.15;
      ctx.beginPath();
      ctx.arc(centerX, centerY, outerR, 0, Math.PI * 2);
      ctx.strokeStyle = primaryColor + "0.28)";
      ctx.lineWidth = Math.max(0.6, 1.0 * (baseR / 60));
      ctx.stroke();

      if (width > 80) {
        const numTicks = 48;
        for (let i = 0; i < numTicks; i++) {
          const tickAngle = -angle * 0.3 + (i * Math.PI * 2) / numTicks;
          const isMajorTick = i % 6 === 0;
          const tickLen = isMajorTick ? baseR * 0.08 : baseR * 0.04;
          const t1 = outerR - tickLen;
          const t2 = outerR;
          ctx.beginPath();
          ctx.moveTo(centerX + Math.cos(tickAngle) * t1, centerY + Math.sin(tickAngle) * t1);
          ctx.lineTo(centerX + Math.cos(tickAngle) * t2, centerY + Math.sin(tickAngle) * t2);
          ctx.strokeStyle = primaryColor + (isMajorTick ? "0.85)" : "0.26)");
          ctx.lineWidth = isMajorTick ? 1.4 : 0.8;
          ctx.stroke();
        }
      }

      // Segmented Rotating Bracket Ring
      const bracketR = baseR * 1.05;
      const bracketSegments = width > 80 ? 10 : 6;
      for (let i = 0; i < bracketSegments; i++) {
        const bAngle = angle * 0.5 + (i * Math.PI * 2) / bracketSegments;
        ctx.beginPath();
        ctx.arc(centerX, centerY, bracketR, bAngle, bAngle + 0.32);
        ctx.strokeStyle = primaryColor + (i % 2 === 0 ? "0.92)" : "0.45)");
        ctx.lineWidth = Math.max(0.8, (currentState === "listening" ? 2.4 : 1.6) * (baseR / 60));
        ctx.stroke();
      }

      // 4. 3D Gyroscopic Orbital Rings with Orbiting Satellites
      orbitalRings.forEach((ring) => {
        const currentR = baseR * ring.rRel;
        const ringRot = angle * (ring.speed / 0.015);
        const segCount = width > 80 ? 48 : 28;
        const projected: { x: number; y: number; z: number; scale: number }[] = [];

        for (let m = 0; m < segCount; m++) {
          const theta = (m * Math.PI * 2) / segCount;
          const x0 = currentR * Math.cos(theta);
          const y0 = currentR * Math.sin(theta);
          projected.push(projectPoint(x0, y0, 0, ring.tiltX, ring.tiltY, ringRot, centerX, centerY, fov));
        }

        for (let m = 0; m < segCount; m++) {
          const p1 = projected[m];
          const p2 = projected[(m + 1) % segCount];
          const avgZ = (p1.z + p2.z) / 2;
          const avgScale = (p1.scale + p2.scale) / 2;

          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(p2.x, p2.y);

          const scaleRatio = Math.max(0.6, baseR / 60);
          if (avgZ < 0) {
            ctx.strokeStyle = primaryColor + Math.min(0.95, 0.72 + 0.28 * (avgScale - 0.7)) + ")";
            ctx.lineWidth = Math.max(0.8, 1.6 * avgScale * scaleRatio);
          } else {
            ctx.strokeStyle = primaryColor + Math.max(0.2, 0.28 * avgScale) + ")";
            ctx.lineWidth = Math.max(0.5, 0.9 * avgScale * scaleRatio);
          }
          ctx.stroke();
        }

        // Orbiting photon nodes
        if (width > 80) {
          for (let j = 0; j < ring.nodes; j++) {
            const nodeAngle = ringRot * 2.2 + (j * Math.PI * 2) / ring.nodes;
            const nx = currentR * Math.cos(nodeAngle);
            const ny = currentR * Math.sin(nodeAngle);
            const nodePt = projectPoint(nx, ny, 0, ring.tiltX, ring.tiltY, ringRot, centerX, centerY, fov);

            ctx.beginPath();
            ctx.arc(nodePt.x, nodePt.y, Math.max(1, 4.5 * nodePt.scale * (baseR / 60)), 0, Math.PI * 2);
            ctx.fillStyle = primaryColor + "0.35)";
            ctx.fill();

            ctx.beginPath();
            ctx.arc(nodePt.x, nodePt.y, Math.max(0.8, 2.0 * nodePt.scale * (baseR / 60)), 0, Math.PI * 2);
            ctx.fillStyle = hotspotColor;
            ctx.fill();
          }
        }
      });

      // 5. Inner Reference & Audio Waveform Ring
      ctx.beginPath();
      ctx.arc(centerX, centerY, baseR * 0.38, 0, Math.PI * 2);
      ctx.strokeStyle = primaryColor + "0.35)";
      ctx.lineWidth = Math.max(0.6, 1.0 * (baseR / 60));
      ctx.stroke();

      const wavePoints = width > 80 ? 44 : 24;
      ctx.beginPath();
      for (let w = 0; w <= wavePoints; w++) {
        const theta = (w * Math.PI * 2) / wavePoints;
        const waveAmp = (currentState === "listening" ? dynamicBoost * 0.45 : currentState === "speaking" ? (baseR * 0.08) : (baseR * 0.025)) *
          Math.sin(theta * 6 + pulse * 4);
        const wr = baseR * 0.44 + waveAmp;
        const wx = centerX + Math.cos(theta) * wr;
        const wy = centerY + Math.sin(theta) * wr;
        if (w === 0) ctx.moveTo(wx, wy);
        else ctx.lineTo(wx, wy);
      }
      ctx.closePath();
      ctx.strokeStyle = primaryColor + (currentState === "listening" ? "0.95)" : "0.55)");
      ctx.lineWidth = Math.max(0.8, (currentState === "listening" ? 2.2 : 1.2) * (baseR / 60));
      ctx.stroke();

      // 6. Central Core & Energy Singularity
      const baseCoreRadius = (currentState === "thinking"
        ? baseR * 0.22
        : currentState === "listening"
        ? baseR * 0.25 + dynamicBoost * 0.4
        : baseR * 0.20);
      const coreRadius = Math.max(4, baseCoreRadius + pulseScale);

      const coreGrad = ctx.createRadialGradient(centerX, centerY, 1, centerX, centerY, coreRadius * 2.2);
      coreGrad.addColorStop(0, hotspotColor);
      coreGrad.addColorStop(0.25, primaryColor + "1.0)");
      coreGrad.addColorStop(0.55, primaryColor + "0.65)");
      coreGrad.addColorStop(0.85, primaryColor + "0.22)");
      coreGrad.addColorStop(1, primaryColor + "0)");

      ctx.beginPath();
      ctx.arc(centerX, centerY, coreRadius * 2.2, 0, Math.PI * 2);
      ctx.fillStyle = coreGrad;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(centerX, centerY, Math.max(3, coreRadius * 0.75), 0, Math.PI * 2);
      ctx.strokeStyle = primaryColor + "0.95)";
      ctx.lineWidth = Math.max(0.8, 1.8 * (baseR / 60));
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(centerX, centerY, Math.max(2, baseR * 0.08), 0, Math.PI * 2);
      ctx.fillStyle = hotspotColor;
      ctx.fill();

      // Speaking sonic shockwaves
      if (currentState === "speaking") {
        for (let w = 0; w < 3; w++) {
          const waveR = ((pulse * 30 + w * (baseR * 0.35)) % (baseR * 0.9)) + (baseR * 0.15);
          const waveAlpha = Math.max(0, 1 - waveR / (baseR * 0.9)) * 0.7;
          ctx.beginPath();
          ctx.arc(centerX, centerY, waveR, 0, Math.PI * 2);
          ctx.strokeStyle = primaryColor + waveAlpha + ")";
          ctx.lineWidth = Math.max(0.6, 1.4 * (baseR / 60));
          ctx.stroke();
        }
      }

      ctx.restore();
      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
    };
  }, []);

  const handleFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (commandInput.trim()) {
      executeTextCommand(commandInput);
    }
  };

  const hasMessages = logs.filter((log) => log.id !== "init").length > 0;

  return (
    <div className="viper-hud-container" data-theme={theme}>

      {/* Top Controls Header */}
      <div className="viper-top-bar">
        <div className="viper-brand">
          <span className="viper-status-led" data-state={hudState}></span>
          <div>
            <div className="viper-title">V.I.P.E.R.</div>
            <div className="viper-subtitle">VIRTUAL INTELLIGENT PERSONAL ELECTRONIC RESPONDENT</div>
          </div>
        </div>

        <div className="viper-controls-strip">
          {audioDevices.length > 0 && (
            <select
              className="mic-select-dropdown"
              value={selectedDeviceId}
              onChange={(e) => {
                userSelectedMicRef.current = true;
                setSelectedDeviceId(e.target.value);
                const selected = audioDevices.find((device) => device.deviceId === e.target.value);
                setMicStatusMsg(`Switching microphone to ${selected?.label || "selected input"}...`);
              }}
              title={activeMicLabel ? `Microphone: ${activeMicLabel}` : "Select Microphone Input Device"}
            >
              <option value="" disabled>Choose microphone</option>
              {audioDevices.map((d, i) => (
                <option key={d.deviceId || i} value={d.deviceId} title={d.label || `Microphone ${i + 1}`}>
                  🎙️ {d.label || `Microphone ${i + 1}`}
                </option>
              ))}
            </select>
          )}

          <select
            className="speech-voice-select"
            value={selectedVoiceURI}
            onChange={(event) => setSelectedVoiceURI(event.target.value)}
            title={`Speaking voice: ${selectedVoiceURI}`}
          >
            <optgroup label="Natural AI voices">
              <option value="ai:troy">AI Natural — Troy</option>
              <option value="ai:daniel">AI Natural — Daniel</option>
              <option value="ai:austin">AI Natural — Austin</option>
              <option value="ai:autumn">AI Natural — Autumn</option>
              <option value="ai:diana">AI Natural — Diana</option>
              <option value="ai:hannah">AI Natural — Hannah</option>
            </optgroup>
            {speechVoices.length > 0 && (
              <optgroup label="System voices">
                {[...speechVoices]
                  .sort((a, b) => scoreSpeechVoice(b) - scoreSpeechVoice(a))
                  .map((voice) => (
                    <option key={voice.voiceURI} value={`native:${voice.voiceURI}`} title={`${voice.name} (${voice.lang})`}>
                      {voice.name} ({voice.lang})
                    </option>
                  ))}
              </optgroup>
            )}
          </select>

          {/* Theme Switcher Pills */}
          <div className="theme-selector-pills" title="Select holographic accent color theme">
            {(["cyan", "purple", "amber", "green"] as const).map((t) => (
              <button
                key={t}
                type="button"
                className={`theme-pill-btn theme-${t} ${theme === t ? "active" : ""}`}
                onClick={() => {
                  setTheme(t);
                  localStorage.setItem("viper_theme", t);
                }}
                title={`Switch to ${t.toUpperCase()} theme`}
              >
                <span className="theme-dot" />
                {t.toUpperCase()}
              </button>
            ))}
          </div>

          <button
            type="button"
            className={`hud-toggle-btn ${isWakeWordActive ? "active" : ""}`}
            onClick={toggleWakeWordMode}
            title="Toggle Continuous Hands-Free Wake Word ('Hey Viper')"
          >
            {isWakeWordActive ? "🟢 WAKE: ON" : "⚪ WAKE: OFF"}
          </button>

          {hudState === "speaking" && (
            <button
              type="button"
              className="hud-toggle-btn muted"
              onClick={abortSpeechAndReset}
              title="Stop Speech Immediately (or press Escape / click Core)"
            >
              ⏹ STOP TALKING
            </button>
          )}

          <button
            type="button"
            className={`hud-toggle-btn ${isVoiceMuted ? "muted" : ""}`}
            onClick={() => setIsVoiceMuted(!isVoiceMuted)}
            title="Toggle Voice Speech Output"
          >
            {isVoiceMuted ? "🔇 VOICE: MUTED" : "🔊 VOICE: ON"}
          </button>

          <button
            type="button"
            className={`hud-toggle-btn ${isSettingsOpen ? "active" : ""}`}
            onClick={() => setIsSettingsOpen(!isSettingsOpen)}
            title="Open V.I.P.E.R. settings & state tester"
          >
            ⚙️ SETTINGS
          </button>
        </div>
      </div>

      {/* Permanent Live System Telemetry Strip (Claude Idea 4) */}
      <div className="viper-hud-telemetry-strip">
        <div className="telemetry-hud-item">
          <span className="telemetry-hud-label">CPU</span>
          <div className="telemetry-gauge-bar">
            <div className="telemetry-gauge-fill" style={{ width: `${Math.min(100, telemetry?.cpu_percent || 18)}%` }} />
          </div>
          <span className="telemetry-hud-val">{telemetry?.cpu_percent ? `${telemetry.cpu_percent}%` : "18%"}</span>
        </div>
        <div className="telemetry-hud-item">
          <span className="telemetry-hud-label">RAM</span>
          <div className="telemetry-gauge-bar">
            <div className="telemetry-gauge-fill" style={{ width: `${Math.min(100, telemetry?.memory_percent || 42)}%` }} />
          </div>
          <span className="telemetry-hud-val">
            {telemetry?.memory_used_gb ? `${telemetry.memory_used_gb}G` : "4.2G"}
          </span>
        </div>
        <div className="telemetry-hud-item">
          <span className="telemetry-hud-label">POWER</span>
          <span className="telemetry-hud-val">{telemetry?.battery_percent ? `${telemetry.battery_percent}%` : "100% AC"}</span>
        </div>
        <div className="telemetry-hud-item">
          <span className="telemetry-hud-label">NET</span>
          <span className="telemetry-hud-val status-online">● ONLINE</span>
        </div>
        <div className="telemetry-hud-item clock-hud-item">
          <span className="telemetry-hud-val">{clock || new Date().toLocaleTimeString()}</span>
        </div>
      </div>

      {/* Main Grid: Visualizer Core + Terminal Log */}
      <div className="viper-main-viewport">
        {/* Left Column: Arc Reactor Core & Voice Controls */}
        <div className="viper-core-section">
          {/* Enhanced Status & Trigger Panel */}
          <div
            className={`hud-core-trigger-card ${hudState === "listening" ? "is-scanning" : ""}`}
            data-state={hudState}
            onClick={toggleVoiceInput}
            title={hudState === "speaking" ? "Click to Stop Talking" : "Click to Talk / Spacebar"}
          >
            {hudState === "listening" && <div className="scanning-laser-line" />}

            <div className="hud-card-top-row">
              <span className="hud-connection-pill">
                <span className="connection-dot" /> ONLINE
              </span>
              <div className="hud-mic-level-pill" title={`Microphone volume: ${Math.round(liveVolume || 0)}%`}>
                <span className="mic-bars-container" aria-hidden="true">
                  {[0.4, 0.7, 1.0, 0.8, 0.5].map((factor, i) => (
                    <span
                      key={i}
                      className="mic-eq-bar"
                      style={{
                        height: `${Math.max(3, Math.min(14, (liveVolume || 4) * factor * 0.22 + 3))}px`,
                      }}
                    />
                  ))}
                </span>
                <span className="mic-pct-val">{Math.min(100, Math.round(liveVolume || 0))}%</span>
              </div>
            </div>

            <div className="hud-core-status-badge-wrap">
              <span className="core-state-badge" data-state={hudState}>
                <span className="core-state-led" data-state={hudState} />
                {hudState === "armed" || hudState === "idle" ? "STANDBY" : hudState.toUpperCase()}
              </span>
            </div>

            <span className="core-hint">
              {hudState === "armed" || hudState === "idle"
                ? "Say 'Hey Viper' to activate"
                : hudState === "listening"
                ? "Listening..."
                : hudState === "thinking"
                ? "Processing..."
                : hudState === "speaking"
                ? "Speaking..."
                : hudState === "error"
                ? "Error..."
                : isWakeWordActive
                ? "Say 'Hey Viper' to activate"
                : "Click anywhere to talk"}
            </span>

            {lastCommand && (
              <div className="last-command-tag" title={`Last directive: ${lastCommand}`}>
                <span className="last-cmd-label">LAST:</span> "{lastCommand}"
              </div>
            )}

            <div className="hud-click-hint">Click anywhere to Talk • Spacebar</div>
          </div>

          {/* Status & Live Voice Transcript Bar */}
          <div className="viper-live-transcript">
            <span className="transcript-prefix">VOICE:</span>
            <span className="transcript-text">{micStatusMsg}</span>
            {hudState === "listening" && (
              <div className="live-vol-meter" title={`Mic Volume: ${liveVolume}%`}>
                <div className="live-vol-fill" style={{ width: `${Math.max(5, liveVolume)}%` }}></div>
              </div>
            )}
          </div>

          {/* Categorized & Customizable Quick Actions */}
          <div className="viper-quick-chips">
            <div className="chips-header-row">
              <span className="chips-title">QUICK ACTIONS</span>
              <div className="chips-category-filter">
                {(["all", "apps", "system", "web"] as const).map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    className={`cat-btn ${selectedCategory === cat ? "active" : ""}`}
                    onClick={() => setSelectedCategory(cat)}
                  >
                    {cat.toUpperCase()}
                  </button>
                ))}
                <button
                  type="button"
                  className={`cat-btn ${isAddingAction ? "active" : ""}`}
                  onClick={() => setIsAddingAction(!isAddingAction)}
                  title="Add custom quick action button"
                >
                  +
                </button>
              </div>
            </div>

            {isAddingAction && (
              <div className="add-action-form">
                <input
                  type="text"
                  placeholder="Label (e.g. Spotify)..."
                  value={newActionLabel}
                  onChange={(e) => setNewActionLabel(e.target.value)}
                />
                <input
                  type="text"
                  placeholder="Directive (e.g. Open Spotify)..."
                  value={newActionCommand}
                  onChange={(e) => setNewActionCommand(e.target.value)}
                />
                <div className="add-action-row">
                  <select
                    value={newActionCategory}
                    onChange={(e) => setNewActionCategory(e.target.value as any)}
                  >
                    <option value="apps">Apps</option>
                    <option value="system">System</option>
                    <option value="web">Web</option>
                  </select>
                  <button
                    type="button"
                    className="save-action-btn"
                    onClick={() => {
                      if (newActionLabel.trim() && newActionCommand.trim()) {
                        const updated: QuickAction[] = [
                          ...quickActions,
                          {
                            id: String(Date.now()),
                            label: newActionLabel.trim(),
                            command: newActionCommand.trim(),
                            icon: "⚡",
                            category: newActionCategory,
                          },
                        ];
                        setQuickActions(updated);
                        localStorage.setItem("viper_quick_actions", JSON.stringify(updated));
                        setNewActionLabel("");
                        setNewActionCommand("");
                        setIsAddingAction(false);
                      }
                    }}
                  >
                    Save
                  </button>
                </div>
              </div>
            )}

            <div className="chips-row">
              {quickActions
                .filter((a) => selectedCategory === "all" || a.category === selectedCategory)
                .map((action) => (
                  <button
                    key={action.id}
                    type="button"
                    className="chip-action-btn"
                    onClick={() => executeTextCommand(action.command)}
                    title={`Run: ${action.command}`}
                  >
                    <span className="chip-icon">{action.icon}</span>
                    <span className="chip-label">{action.label}</span>
                  </button>
                ))}
              <button
                type="button"
                className="chip-action-btn chip-add-card"
                onClick={() => setIsAddingAction(true)}
                title="Add custom action card"
              >
                <span className="chip-icon">+</span>
                <span className="chip-label">Custom Action</span>
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Cyber Action Terminal & Directive Feed */}
        <div className={`viper-terminal-section ${hasMessages ? "has-messages" : "is-empty"}`}>
          {/* HUD Corner Brackets */}
          <span className="hud-corner hud-corner-tl" aria-hidden="true" />
          <span className="hud-corner hud-corner-tr" aria-hidden="true" />
          <span className="hud-corner hud-corner-bl" aria-hidden="true" />
          <span className="hud-corner hud-corner-br" aria-hidden="true" />

          {/* Glowing Arc Reactor Orb (180px in Empty State -> 48px Header on Message) */}
          <div className={`chat-orb-wrapper ${hasMessages ? "in-header" : "in-empty-state"}`} aria-hidden="true">
            <canvas ref={chatOrbCanvasRef} className="chat-orb-canvas" />
          </div>

          <div className="terminal-header">
            <div className="terminal-title">
              {!hasMessages && <span className="terminal-dot"></span>}
              CONVERSATION FEED
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
                      type: "viper",
                      text: "Terminal log cleared, Sir. All background protocols running.",
                    },
                  ])
                }
              >
                Clear
              </button>
            </div>
          </div>

          <div className="terminal-body">
            {logs.filter((log) => log.id !== "init").map((log) => (
              <div key={log.id} className={`terminal-entry entry-${log.type}`}>
                {log.type === "viper" && (
                  <span className="entry-viper-avatar" aria-hidden="true">V</span>
                )}
                <div className="entry-bubble">
                  <div className="entry-meta">
                    <span className="entry-sender">[{log.type === "user" ? "DEVANSH" : "V.I.P.E.R."}]</span>
                    <span className="entry-time">{log.timestamp}</span>
                    {log.actionTag && <span className="entry-badge">{log.actionTag}</span>}
                  </div>
                  <div className="entry-content">{log.text}</div>
                </div>
              </div>
            ))}

            {/* Live Typing / Computing Animation */}
            {hudState === "thinking" && (
              <div className="terminal-entry entry-viper entry-computing">
                <span className="entry-viper-avatar" aria-hidden="true">V</span>
                <div className="entry-bubble">
                  <div className="entry-meta">
                    <span className="entry-sender">[V.I.P.E.R.]</span>
                    <span className="entry-time">{new Date().toLocaleTimeString()}</span>
                    <span className="entry-badge">COMPUTING</span>
                  </div>
                  <div className="entry-content computing-indicator">
                    <span className="computing-dot" />
                    <span className="computing-dot" />
                    <span className="computing-dot" />
                    <span className="computing-text">Synthesizing response with Groq LPU...</span>
                  </div>
                </div>
              </div>
            )}

            {logs.filter((log) => log.id !== "init").length === 0 && (
              <div className="conversation-empty-state">
                <div className="empty-state-orb-spacer" aria-hidden="true" />
                <strong className="empty-state-title">How can I help, Sir?</strong>
                <span className="empty-state-subtitle">Ask a question, give a voice command, or type below.</span>
              </div>
            )}
          </div>

          {/* Real Animated Waveform Bar Above Input */}
          <div className="terminal-audio-wave-bar">
            <div className="wave-status-left">
              <span className="live-wave-label">
                {hudState === "listening"
                  ? "🎙️ LIVE MIC STREAM"
                  : hudState === "speaking"
                  ? "🔊 VOICE SYNTHESIS"
                  : hudState === "thinking"
                  ? "⚡ NEURAL PROCESSING"
                  : "⚡ AUDIO READY"}
              </span>
            </div>
            {/* Real Fluid SVG Waveform */}
            <div className="live-fluid-waveform-wrapper">
              <svg className="live-fluid-wave-svg" viewBox="0 0 280 32" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="waveGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="var(--theme-accent, #00f0ff)" stopOpacity="0.2" />
                    <stop offset="50%" stopColor="var(--theme-accent, #00f0ff)" stopOpacity="0.95" />
                    <stop offset="100%" stopColor="#00ffaa" stopOpacity="0.3" />
                  </linearGradient>
                  <linearGradient id="waveGlow" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#ffffff" stopOpacity="0.1" />
                    <stop offset="50%" stopColor="#ffffff" stopOpacity="0.8" />
                    <stop offset="100%" stopColor="var(--theme-accent, #00f0ff)" stopOpacity="0.2" />
                  </linearGradient>
                </defs>
                <path
                  d={generateWavePath(280, 32, liveVolume, hudState, 1)}
                  fill="none"
                  stroke="url(#waveGrad)"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                />
                <path
                  d={generateWavePath(280, 32, liveVolume, hudState, 2)}
                  fill="none"
                  stroke="url(#waveGlow)"
                  strokeWidth="1.2"
                  strokeLinecap="round"
                />
              </svg>
            </div>
            <span className="live-wave-val">{Math.round(liveVolume || 0)}%</span>
          </div>

          {/* Manual Input Command Bar with Voice Mic Button */}
          <form className="terminal-input-bar" onSubmit={handleFormSubmit}>
            <span className="input-prompt">&gt;</span>
            <input
              type="text"
              placeholder="Type a message or voice command..."
              value={commandInput}
              onChange={(e) => setCommandInput(e.target.value)}
            />
            <button
              type="button"
              className={`terminal-mic-btn ${hudState === "listening" ? "listening" : ""}`}
              onClick={toggleVoiceInput}
              title={hudState === "listening" ? "Listening... click to stop" : "Click to speak voice directive"}
            >
              🎙️
            </button>
            <button type="submit" className="terminal-send-btn">
              Send
            </button>
          </form>
        </div>
      </div>

      {/* Settings Modal Panel */}
      {isSettingsOpen && (
        <div className="viper-settings-modal-backdrop" onClick={() => setIsSettingsOpen(false)}>
          <div className="viper-settings-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="settings-modal-header">
              <span className="settings-modal-title">⚙️ V.I.P.E.R. SYSTEM SETTINGS</span>
              <button
                type="button"
                className="settings-modal-close"
                onClick={() => setIsSettingsOpen(false)}
              >
                ✕
              </button>
            </div>

            <div className="settings-modal-body">
              {/* Voice section */}
              <div className="settings-row">
                <label className="settings-label">SYNTHESIS VOICE</label>
                <select
                  className="settings-select"
                  value={selectedVoiceURI}
                  onChange={(e) => setSelectedVoiceURI(e.target.value)}
                >
                  <optgroup label="Natural AI voices">
                    <option value="ai:troy">AI Natural — Troy</option>
                    <option value="ai:daniel">AI Natural — Daniel</option>
                    <option value="ai:austin">AI Natural — Austin</option>
                    <option value="ai:autumn">AI Natural — Autumn</option>
                    <option value="ai:diana">AI Natural — Diana</option>
                    <option value="ai:hannah">AI Natural — Hannah</option>
                  </optgroup>
                  {speechVoices.length > 0 && (
                    <optgroup label="System voices">
                      {[...speechVoices]
                        .sort((a, b) => scoreSpeechVoice(b) - scoreSpeechVoice(a))
                        .map((voice) => (
                          <option key={voice.voiceURI} value={`native:${voice.voiceURI}`}>
                            {voice.name} ({voice.lang})
                          </option>
                        ))}
                    </optgroup>
                  )}
                </select>
              </div>

              {/* Theme section */}
              <div className="settings-row">
                <label className="settings-label">HOLOGRAPHIC ACCENT THEME</label>
                <div className="settings-theme-grid">
                  {(["cyan", "purple", "amber", "green"] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      className={`settings-theme-btn theme-${t} ${theme === t ? "active" : ""}`}
                      onClick={() => {
                        setTheme(t);
                        localStorage.setItem("viper_theme", t);
                      }}
                    >
                      <span className="theme-dot" />
                      {t.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>

              {/* Wake Word Sensitivity */}
              <div className="settings-row">
                <div className="settings-row-between">
                  <label className="settings-label">WAKE WORD SENSITIVITY</label>
                  <span className="settings-val-badge">{wakeSensitivity}x</span>
                </div>
                <input
                  type="range"
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  className="settings-slider"
                  value={wakeSensitivity}
                  onChange={(e) => setWakeSensitivity(parseFloat(e.target.value))}
                />
              </div>

              {/* State Tester Row */}
              <div className="settings-row">
                <label className="settings-label">TEST ORB REACTIVE STATES</label>
                <div className="settings-states-row">
                  {(["idle", "listening", "thinking", "speaking", "error"] as const).map((st) => (
                    <button
                      key={st}
                      type="button"
                      className={`state-test-btn state-${st} ${hudState === st ? "active" : ""}`}
                      onClick={() => {
                        (window as any).setViperState?.(st);
                      }}
                    >
                      {st.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
