import { FormEvent, useEffect, useRef, useState } from "react";

type JarvisStatus = "idle" | "armed" | "listening" | "thinking" | "speaking";

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

export function JarvisHUD({ onNavigateModule }: { onNavigateModule?: (mod: string) => void } = {}) {
  const [hudState, setHudState] = useState<JarvisStatus>("armed");
  const [isVoiceMuted, setIsVoiceMuted] = useState<boolean>(false);
  const [isWakeWordActive, setIsWakeWordActive] = useState<boolean>(true);
  const [micStatusMsg, setMicStatusMsg] = useState<string>("Standby active. Say 'Hey Jarvis' anytime.");
  const [commandInput, setCommandInput] = useState<string>("");
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
  const [liveVolume, setLiveVolume] = useState<number>(0);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [clock, setClock] = useState<string>("");
  const [logs, setLogs] = useState<ActionLogItem[]>([
    {
      id: "init",
      timestamp: new Date().toLocaleTimeString(),
      type: "jarvis",
      text: "J.A.R.V.I.S. Core Online. Say 'Hey Jarvis' or click Core to talk.",
      actionTag: "SYSTEM_READY",
    },
  ]);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const hudStateRef = useRef<JarvisStatus>("armed");
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
  const ambientNoiseRef = useRef<number>(0.008);
  const audioLevelRef = useRef<number>(0);
  const pendingTranscriptRef = useRef<string>("");

  // Ref to allow safe callback from Web Audio onaudioprocess
  const finalizeAudioRef = useRef<() => void>(() => {});

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

  // Enumerate Microphones (Auto-select earphones/headset if connected)
  useEffect(() => {
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      navigator.mediaDevices.enumerateDevices().then((devices) => {
        const mics = devices.filter((d) => d.kind === "audioinput");
        setAudioDevices(mics);
        const headset = mics.find((m) =>
          /headset|earphone|headphone|bluetooth|airpod|usb/i.test(m.label)
        );
        if (headset) {
          setSelectedDeviceId(headset.deviceId);
        } else if (mics.length > 0) {
          setSelectedDeviceId(mics[0].deviceId);
        }
      }).catch(() => {});
    }
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

  // Instantly Abort Speech (Stop talking)
  const abortSpeechAndReset = () => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    isCapturingRef.current = false;
    recordedChunksRef.current = [];
    setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
    setMicStatusMsg(
      isWakeWordActiveRef.current
        ? "Speech stopped, Sir. Standby active."
        : "Speech stopped, Sir. Click Core to speak."
    );
    playAudioChime("alert");
  };

  // Web Speech Synthesis (JARVIS voice)
  const speakReply = (text: string) => {
    if (isVoiceMuted || !("speechSynthesis" in window) || !text.trim()) {
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      return;
    }

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

    utterance.onstart = () => {
      setHudState("speaking");
      setMicStatusMsg("Speaking directive response, Sir... (Click Core to stop)");
    };

    utterance.onend = () => {
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      setMicStatusMsg(
        isWakeWordActiveRef.current
          ? "Standby active. Say 'Hey Jarvis' anytime."
          : "Click Core or press Space to speak."
      );
    };

    utterance.onerror = () => {
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      setMicStatusMsg(
        isWakeWordActiveRef.current
          ? "Standby active. Say 'Hey Jarvis' anytime."
          : "Click Core or press Space to speak."
      );
    };

    window.speechSynthesis.speak(utterance);
  };

  // Put JARVIS into Active Listening state (Turns Core Green & starts recording command)
  const startActiveCommandListening = (status = "🟢 J.A.R.V.I.S. ACTIVATED — listening for your command now.") => {
    const ctx = getAudioContext();
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});

    playAudioChime("activate");
    recordedChunksRef.current = [];
    hasSpokenRef.current = false;
    silenceFramesRef.current = 0;
    totalFramesRef.current = 0;
    captureModeRef.current = "direct";
    isCapturingRef.current = true;
    setHudState("listening"); // TURNS CORE NEON GREEN!
    setMicStatusMsg(status);
  };

  // Submit Text Command to Backend
  const executeTextCommand = async (commandText: string) => {
    const trimmed = commandText.trim();
    if (!trimmed) return;

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
      const res = await fetch("/api/jarvis/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, voice_mode: false }),
      });

      if (!res.ok) throw new Error(`Server returned ${res.status}`);
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

      if (data.system_status) setTelemetry(data.system_status);

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
          type: "jarvis",
          text: `Command error: ${err.message || "Failed to execute"}. Please verify backend status, Sir.`,
          actionTag: "ERROR",
        },
      ]);
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      setMicStatusMsg(
        isWakeWordActiveRef.current
          ? "Standby active. Say 'Hey Jarvis' anytime."
          : "Click Core or press Space to speak."
      );
    }
  };

  // Transmit Audio to Backend (/api/jarvis/voice)
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
      const continuation = mode === "direct" ? pendingTranscriptRef.current : "";
      const continuationParam = continuation
        ? `&continuation_text=${encodeURIComponent(continuation)}`
        : "";

      const res = await fetch(`/api/jarvis/voice?wake_mode=${isWakeMode ? "true" : "false"}&interrupt_mode=${isInterruptMode ? "true" : "false"}${continuationParam}`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error(`Voice server returned ${res.status}`);
      const data = await res.json();

      // A spoken stop is monitored while TTS is playing. Handle it before
      // any normal response path so J.A.R.V.I.S. does not speak over it.
      if (isInterruptMode) {
        if (data.action_taken === "STOP_DIRECTIVE") abortSpeechAndReset();
        return;
      }

      if (data.action_taken === "CONTINUE_LISTENING") {
        pendingTranscriptRef.current = data.transcript || continuation;
        startActiveCommandListening("🟢 Still listening — please finish your request.");
        return;
      }

      // Case A: In wake_mode and utterance was not directed at Jarvis (no 'Jarvis' found)
      // Stay COMPLETELY silent and IDLE. Zero flicker, zero interruption!
      if (isWakeMode && data.action_taken === "WAKE_IGNORED") {
        pendingTranscriptRef.current = "";
        setHudState("armed");
        setMicStatusMsg("Standby active. Say 'Hey Jarvis' anytime.");
        return;
      }

      // Case B: User said ONLY "Hey Jarvis" -> AWAKEN & TURN GREEN IMMEDIATELY!
      if (data.action_taken === "WAKE_CONFIRMED") {
        pendingTranscriptRef.current = "";
        const jarvisLogId = Math.random().toString(36).substring(7);
        setLogs((prev) => [
          ...prev,
          {
            id: jarvisLogId,
            timestamp: new Date().toLocaleTimeString(),
            type: "jarvis",
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
        if (!isWakeMode) {
          playAudioChime("alert");
          setLogs((prev) => [
            ...prev,
            {
              id: Math.random().toString(36).substring(7),
              timestamp: new Date().toLocaleTimeString(),
              type: "jarvis",
              text: "I couldn't hear any distinct directive, Sir. Please try speaking again.",
              actionTag: "NO_SPEECH_DETECTED",
            },
          ]);
        }
        setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
        setMicStatusMsg(
          isWakeWordActiveRef.current
            ? "Standby active. Say 'Hey Jarvis' anytime."
            : "Click Core to retry."
        );
        return;
      }

      // Case C: Direct command or "Hey Jarvis + [command]" executed!
      pendingTranscriptRef.current = "";
      playAudioChime("confirm");

      const jarvisLogId = Math.random().toString(36).substring(7);
      setLogs((prev) => [
        ...prev,
        {
          id: jarvisLogId,
          timestamp: new Date().toLocaleTimeString(),
          type: "jarvis",
          text: data.reply,
          actionTag: data.action_taken ? data.action_taken.toUpperCase() : "VOICE_COMMAND",
        },
      ]);

      if (data.system_status) setTelemetry(data.system_status);

      speakReply(data.audio_text || data.reply);
    } catch (err: any) {
      if (isInterruptMode) return;
      if (!isWakeMode) {
        playAudioChime("alert");
        setLogs((prev) => [
          ...prev,
          {
            id: Math.random().toString(36).substring(7),
            timestamp: new Date().toLocaleTimeString(),
            type: "jarvis",
            text: `Voice notice: ${err.message || "Could not process audio"}.`,
            actionTag: "VOICE_ERROR",
          },
        ]);
      }
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      setMicStatusMsg(
        isWakeWordActiveRef.current
          ? "Standby active. Say 'Hey Jarvis' anytime."
          : "Click Core to retry."
      );
    }
  };

  // Finalize audio buffer and stop current capture
  const finalizeAudioAndSend = () => {
    if (!isCapturingRef.current) return;
    isCapturingRef.current = false;
    audioLevelRef.current = 0;

    const isWake = captureModeRef.current === "wake";
    const chunks = recordedChunksRef.current;
    recordedChunksRef.current = [];

    if (chunks.length === 0 || (!hasSpokenRef.current && !isWake)) {
      setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
      setMicStatusMsg(
        isWakeWordActiveRef.current
          ? "Standby active. Say 'Hey Jarvis' anytime."
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

    transmitRecordedAudio(wavBlob, captureModeRef.current);
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
          noiseSuppression: false,
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
        const source = ctx.createMediaStreamSource(stream);
        const processor = ctx.createScriptProcessor(4096, 1, 1);
        scriptProcessorRef.current = processor;

        processor.onaudioprocess = (e) => {
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
          audioLevelRef.current = rms;
          setLiveVolume(Math.min(100, Math.round(rms * 500)));

          // Dynamically track background noise floor smoothly
          ambientNoiseRef.current = ambientNoiseRef.current * 0.94 + rms * 0.06;

          // Calibrated speech trigger thresholds
          const wakeSpeechThreshold = Math.max(0.020, ambientNoiseRef.current * 2.0);
          const directSpeechThreshold = Math.max(0.014, ambientNoiseRef.current * 1.5);
          const silenceThreshold = Math.max(0.010, ambientNoiseRef.current * 1.25);

          if (hudStateRef.current === "speaking") {
            if (!isCapturingRef.current && rms > directSpeechThreshold) {
              isCapturingRef.current = true;
              captureModeRef.current = "interrupt";
              hasSpokenRef.current = true;
              silenceFramesRef.current = 0;
              totalFramesRef.current = 1;
              recordedChunksRef.current = [new Float32Array(inputData)];
              return;
            }
            if (isCapturingRef.current && captureModeRef.current === "interrupt") {
              recordedChunksRef.current.push(new Float32Array(inputData));
              totalFramesRef.current++;
              if (rms > directSpeechThreshold) silenceFramesRef.current = 0;
              else if (rms < silenceThreshold) silenceFramesRef.current++;
              if (silenceFramesRef.current >= 8 || totalFramesRef.current >= 35) {
                finalizeAudioRef.current();
              }
            }
            return;
          }

          // 1. Silent Hands-Free Wake-Word Standby Listening
          // Buffers silently in memory until "Hey Jarvis" is confirmed
          if (
            isWakeWordActiveRef.current &&
            !isCapturingRef.current &&
            hudStateRef.current === "armed"
          ) {
            if (rms > wakeSpeechThreshold) {
              isCapturingRef.current = true;
              captureModeRef.current = "wake";
              hasSpokenRef.current = true;
              silenceFramesRef.current = 0;
              totalFramesRef.current = 1;
              recordedChunksRef.current = [new Float32Array(inputData)];
              setMicStatusMsg("Wake phrase detected — checking for 'Hey Jarvis'...");
            }
            return;
          }

          // 2. Actively Capturing Voice (Direct Push-To-Talk or Background Wake phrase)
          if (isCapturingRef.current) {
            recordedChunksRef.current.push(new Float32Array(inputData));
            totalFramesRef.current++;

            const currentSpeechThreshold =
              captureModeRef.current === "wake" ? wakeSpeechThreshold : directSpeechThreshold;

            if (rms > currentSpeechThreshold) {
              hasSpokenRef.current = true;
              silenceFramesRef.current = 0;
              if (captureModeRef.current === "direct") {
                setMicStatusMsg("🎙️ Hearing your voice... Pause when finished or click Core.");
              }
            } else if (rms < silenceThreshold) {
              if (hasSpokenRef.current) {
                silenceFramesRef.current++;
              }
            }

            // NATURAL SILENCE ENDPOINTING:
            // Short acoustic hangover for the current batch-transcription flow.
            // Smarter end-of-turn detection should replace this fixed threshold.
            const silenceFrameLimit = captureModeRef.current === "wake" ? 10 : 18;
            if (hasSpokenRef.current && silenceFramesRef.current >= silenceFrameLimit) {
              finalizeAudioRef.current();
              return;
            }

            // SAFETY MAX LIMIT:
            // Keep wake detection responsive; command clips can run for about 13 seconds.
            const maxFrameLimit = captureModeRef.current === "wake" ? 35 : 140;
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
              setHudState(isWakeWordActiveRef.current ? "armed" : "idle");
              setMicStatusMsg(
                isWakeWordActiveRef.current
                  ? "Standby active. Say 'Hey Jarvis' anytime."
                  : "Click Core or press Space to Speak."
              );
            }
          }
        };

        source.connect(processor);
        processor.connect(ctx.destination);
      } catch (err) {
        console.warn("Microphone initialization notice:", err);
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
      setMicStatusMsg("Standby active. Say 'Hey Jarvis' anytime.");
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

  // Arc-Reactor Holographic Canvas Animation
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

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
      const micLevel = audioLevelRef.current;
      const dynamicBoost = micLevel * 80;

      angle += currentState === "thinking" ? 0.05 : currentState === "listening" ? 0.03 + micLevel * 0.1 : 0.015;
      pulse += 0.04;
      const pulseScale = Math.sin(pulse) * 4 + dynamicBoost;

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
      ctx.shadowBlur = 16 + dynamicBoost;
      ctx.shadowColor = glowColor;

      // Outer Segmented Ring
      ctx.beginPath();
      ctx.arc(centerX, centerY, 150, 0, Math.PI * 2);
      ctx.strokeStyle = primaryColor + "0.2)";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Outer Rotating Arc Segments (Turns Bright Green when Listening!)
      const segments = 12;
      for (let i = 0; i < segments; i++) {
        const segAngle = angle + (i * Math.PI * 2) / segments;
        ctx.beginPath();
        ctx.arc(centerX, centerY, 140, segAngle, segAngle + 0.32);
        ctx.strokeStyle = primaryColor + (i % 2 === 0 ? "0.95)" : "0.45)");
        ctx.lineWidth = currentState === "listening" ? 4 : 3;
        ctx.stroke();
      }

      // Middle Ring with Tech Tick Marks
      ctx.beginPath();
      ctx.arc(centerX, centerY, 115, 0, Math.PI * 2);
      ctx.strokeStyle = primaryColor + "0.3)";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      const numTicks = 36;
      for (let i = 0; i < numTicks; i++) {
        const tickAngle = -angle * 0.75 + (i * Math.PI * 2) / numTicks;
        const r1 = 110;
        const r2 = i % 3 === 0 ? 124 + dynamicBoost * 0.35 : 116;
        ctx.beginPath();
        ctx.moveTo(centerX + Math.cos(tickAngle) * r1, centerY + Math.sin(tickAngle) * r1);
        ctx.lineTo(centerX + Math.cos(tickAngle) * r2, centerY + Math.sin(tickAngle) * r2);
        ctx.strokeStyle = primaryColor + (i % 3 === 0 ? "0.9)" : "0.3)");
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Inner Counter-Rotating Bracket Ring
      for (let i = 0; i < 4; i++) {
        const bracketAngle = -angle * 1.2 + (i * Math.PI) / 2;
        ctx.beginPath();
        ctx.arc(centerX, centerY, 85, bracketAngle, bracketAngle + Math.PI / 4);
        ctx.strokeStyle = primaryColor + "0.85)";
        ctx.lineWidth = 4;
        ctx.stroke();
      }

      // Core Glowing Arc Reactor Center (Vibrant pulsing glow)
      const coreRadius = Math.max(
        32,
        44 + pulseScale + (currentState === "speaking" ? Math.sin(pulse * 3) * 8 : 0)
      );
      const gradient = ctx.createRadialGradient(centerX, centerY, 5, centerX, centerY, coreRadius);
      gradient.addColorStop(0, primaryColor + "1)");
      gradient.addColorStop(0.45, primaryColor + "0.65)");
      gradient.addColorStop(1, primaryColor + "0)");

      ctx.beginPath();
      ctx.arc(centerX, centerY, coreRadius, 0, Math.PI * 2);
      ctx.fillStyle = gradient;
      ctx.fill();

      // Center Core Dot
      ctx.beginPath();
      ctx.arc(centerX, centerY, 15, 0, Math.PI * 2);
      ctx.fillStyle = primaryColor + "1)";
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
      executeTextCommand(commandInput);
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
          {audioDevices.length > 0 && (
            <select
              className="mic-select-dropdown"
              value={selectedDeviceId}
              onChange={(e) => setSelectedDeviceId(e.target.value)}
              title="Select Microphone Input Device"
            >
              {audioDevices.map((d, i) => (
                <option key={d.deviceId || i} value={d.deviceId}>
                  🎙️ {d.label || `Microphone ${i + 1}`}
                </option>
              ))}
            </select>
          )}

          <button
            type="button"
            className={`hud-toggle-btn ${isWakeWordActive ? "active" : ""}`}
            onClick={toggleWakeWordMode}
            title="Toggle Continuous Hands-Free Wake Word ('Hey Jarvis')"
          >
            {isWakeWordActive ? "🟢 WAKE WORD: ON" : "⚪ WAKE WORD: OFF"}
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
        </div>
      </div>

      {/* Main Grid: Visualizer Core + Terminal Log */}
      <div className="jarvis-main-viewport">
        {/* Left Column: Arc Reactor Core & Voice Controls */}
        <div className="jarvis-core-section">
          <div
            className="arc-reactor-wrapper"
            onClick={toggleVoiceInput}
            title={hudState === "speaking" ? "Click to Stop Talking" : "Click to Talk / Spacebar"}
          >
            <canvas ref={canvasRef} className="arc-reactor-canvas" />
            <div className="arc-reactor-overlay">
              <span className="core-state-badge" data-state={hudState}>
                {hudState.toUpperCase()}
              </span>
              <span className="core-hint">
                {hudState === "armed"
                  ? "ARMED... SAY 'HEY JARVIS' TO ACTIVATE"
                  : hudState === "listening"
                  ? "J.A.R.V.I.S. ACTIVATED — SAY YOUR COMMAND"
                  : hudState === "thinking"
                  ? "COMPUTING WITH GROQ..."
                  : hudState === "speaking"
                  ? "SPEAKING... (CLICK TO STOP)"
                  : isWakeWordActive
                  ? "SAY 'HEY JARVIS' (OR CLICK TO TALK)"
                  : "CLICK TO TALK (OR PRESS SPACE)"}
              </span>
            </div>
          </div>

          {/* Status & Live Voice Transcript Bar */}
          <div className="jarvis-live-transcript">
            <span className="transcript-prefix">VOICE:</span>
            <span className="transcript-text">{micStatusMsg}</span>
            {hudState === "listening" && (
              <div className="live-vol-meter" title={`Mic Volume: ${liveVolume}%`}>
                <div className="live-vol-fill" style={{ width: `${Math.max(5, liveVolume)}%` }}></div>
              </div>
            )}
          </div>

          {/* Quick Actions Chips */}
          <div className="jarvis-quick-chips">
            <span className="chips-title">RAPID DIRECTIVES:</span>
            <div className="chips-row">
              <button type="button" onClick={() => executeTextCommand("Hey Jarvis")}>
                ⚡ Wake Jarvis
              </button>
              <button type="button" onClick={() => executeTextCommand("check my system")}>
                📊 Check System
              </button>
              <button type="button" onClick={() => executeTextCommand("Open YouTube")}>
                ▶ YouTube
              </button>
              <button type="button" onClick={() => executeTextCommand("Open Google Chrome")}>
                🌐 Chrome
              </button>
              <button type="button" onClick={() => executeTextCommand("Mute audio")}>
                🔇 Mute
              </button>
              <button type="button" onClick={() => executeTextCommand("What time is it?")}>
                ⏱ Time
              </button>
              <button type="button" onClick={() => executeTextCommand("Lock workstation")}>
                🔒 Lock PC
              </button>
              <button type="button" onClick={() => executeTextCommand("Read my notes")}>
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
              placeholder="Enter voice command or type directive here (e.g. 'check my system', 'open spotify', 'stop')..."
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
