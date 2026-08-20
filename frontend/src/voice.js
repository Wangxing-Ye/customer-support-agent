import { getMaxWords } from "./config.js";
import { wordCount } from "./utils.js";
import { fetchTranscribe } from "./api.js";

let voiceListening = false;
let mediaRecorder = null;
let mediaStream = null;
let audioChunks = [];

function setVoiceButtonRecording(recording) {
  const btn = document.getElementById("voice-btn");
  if (!btn) return;
  btn.setAttribute("aria-pressed", recording ? "true" : "false");
  btn.setAttribute(
    "aria-label",
    recording ? "Recording… click to stop" : "Voice input",
  );
  if (recording) {
    btn.classList.add("recording");
  } else {
    btn.classList.remove("recording");
  }
}

function pickAudioMimeType() {
  const c = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (let i = 0; i < c.length; i++) {
    if (MediaRecorder.isTypeSupported(c[i])) return c[i];
  }
  return "";
}

function bridge() {
  return window.__pstChat || null;
}

export async function toggleVoice() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("Recording is not supported in this browser.");
    return;
  }
  if (voiceListening && mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    alert("Microphone permission was denied or no microphone is available.");
    return;
  }

  audioChunks = [];
  const mimeType = pickAudioMimeType();
  try {
    mediaRecorder = mimeType
      ? new MediaRecorder(mediaStream, { mimeType })
      : new MediaRecorder(mediaStream);
  } catch {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
    alert("Could not start audio recorder.");
    return;
  }

  mediaRecorder.ondataavailable = (ev) => {
    if (ev.data && ev.data.size > 0) audioChunks.push(ev.data);
  };

  mediaRecorder.onerror = () => {
    voiceListening = false;
    setVoiceButtonRecording(false);
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = null;
    }
  };

  mediaRecorder.onstop = async () => {
    voiceListening = false;
    setVoiceButtonRecording(false);
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = null;
    }
    const blobType = mediaRecorder.mimeType || "audio/webm";
    const blob = new Blob(audioChunks, { type: blobType });
    audioChunks = [];
    const ui = bridge();
    if (blob.size < 512) {
      ui?.addMessage?.(
        "Recording too short. Hold the button, speak, then tap again to stop.",
        true,
      );
      return;
    }
    const ext = blobType.indexOf("mp4") !== -1 ? "mp4" : "webm";
    let transcribed = "";
    ui?.beginVoicePending?.();
    try {
      const res = await fetchTranscribe(blob, `recording.${ext}`);
      if (!res.ok) {
        let detail = "Transcription failed.";
        try {
          const errBody = await res.json();
          if (errBody.detail) detail = String(errBody.detail);
        } catch {
          /* ignore */
        }
        ui?.clearVoicePending?.();
        ui?.addMessage?.(detail, true);
        return;
      }
      const data = await res.json();
      transcribed = String(data.text || "").trim();
      if (!transcribed) {
        ui?.clearVoicePending?.();
        ui?.addMessage?.("No speech detected. Please try again.", true);
        return;
      }
      if (wordCount(transcribed) > getMaxWords()) {
        ui?.clearVoicePending?.();
        ui?.addMessage?.(
          `Voice input must be at most ${getMaxWords()} words. Please try a shorter question.`,
          true,
        );
        return;
      }
    } catch {
      ui?.clearVoicePending?.();
      ui?.addMessage?.("Sorry, transcription failed. Please try again.", true);
      return;
    }

    if (ui?.sendVoiceTranscript) {
      await ui.sendVoiceTranscript(transcribed);
    } else {
      ui?.clearVoicePending?.();
      ui?.addMessage?.(transcribed, false);
    }
  };

  mediaRecorder.start(250);
  voiceListening = true;
  setVoiceButtonRecording(true);
}
