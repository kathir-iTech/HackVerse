"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001/report";
const API_BASE = API.replace(/\/report$/, "");

interface ReportSummary {
  report_id: string;
  business_type: string | null;
  assessment_band: string;
  generated_at: string;
}

type Band = "Low" | "Moderate" | "Strong";

interface Report {
  business_type: string | null;
  revenue_consistency_band: Band;
  inventory_observation_band: Band;
  digital_activity_band: Band;
  relevant_scheme_note: string;
  assessment_band: string;
  evidence_summary: string[];
  missing_inputs: string[];
  discrepancy_flags: string[];
  source_agreement: Record<string, string>;
  photo_reuse_flag?: string | null;
  report_id?: string;
  vendor_name?: string;
  sources_cited?: string[];
  evidence_completeness?: { sources_provided: number; sources_total: number; discrepancies_found: boolean };
  input_errors?: string[];
  total_inflow?: number;
  total_outflow?: number;
  transaction_count?: number;
  average_transaction?: number;
  volatility?: string;
  trend?: string;
  date_range_days?: number;
  earliest_date?: string;
  latest_date?: string;
  format_notes?: string;
  location_verification?: {
    location_found: boolean;
    matched_name?: string;
    coordinates?: { lat: string; lon: string };
    address?: string;
    error?: string;
  };
  risk_indicators?: {
    indicators: {
      high_transaction_volatility: boolean;
      unverifiable_location: boolean;
      cross_source_conflicts: boolean;
      possible_photo_reuse: boolean;
      incomplete_evidence: boolean;
    };
    indicators_triggered: number;
    risk_summary: string;
  };
  onboarding_pathway?: string[];
  vendor_formal_status?: {
    has_savings_account: string;
    annual_turnover: number | null;
    udyam_number: string | null;
    gst_required: boolean | null;
  };
  officer_guidance?: string;
  reasoning_trace?: {
    revenue_consistency_reasoning?: string;
    inventory_observation_reasoning?: string;
    digital_activity_reasoning?: string;
  };
  document_analysis?: {
    documents_processed: string[];
    documents_missing: string[];
    extracted: Record<string, { raw_text: string; document_type: string; key_fields: Record<string, any> }>;
    verification_signals: Record<string, boolean>;
  };
  profile_completeness?: {
    completeness_score: number;
    completeness_tier: string;
    missing_for_next_tier: string[];
    label: string;
  };
}

type ReasonKey =
  | "revenue_consistency_reasoning"
  | "inventory_observation_reasoning"
  | "digital_activity_reasoning";

const AGREEMENT_COLORS: Record<string, string> = {
  agree: "bg-green-100 text-green-700 border-green-300",
  conflict: "bg-amber-100 text-amber-700 border-amber-300",
  insufficient_data: "bg-slate-50 text-slate-400 border-slate-200",
};

const PAIR_LABELS: Record<string, string> = {
  photo_voice: "Photo ⇄ Voice",
  photo_transactions: "Photo ⇄ Transactions",
  voice_transactions: "Voice ⇄ Transactions",
};

// Phase 3 — P3-ST1a: filled pill colours
function bandColor(b: Band | string) {
  switch (b) {
    case "Low":
      return "text-red-800 bg-red-100 border-red-200";
    case "Moderate":
      return "text-yellow-800 bg-yellow-100 border-yellow-200";
    case "Strong":
      return "text-green-800 bg-green-100 border-green-200";
    default:
      return "text-slate-600 bg-slate-50 border-slate-200";
  }
}

const BAND_ORDER: Record<string, number> = { Low: 0, Moderate: 1, Strong: 2 };

function bandTrend(current: string, past: string): "Improved" | "Declined" | "Stable" {
  const c = BAND_ORDER[current] ?? -1;
  const p = BAND_ORDER[past] ?? -1;
  if (c > p) return "Improved";
  if (c < p) return "Declined";
  return "Stable";
}

function formatLat(lat: number) {
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? "N" : "S"}`;
}

function formatLon(lon: number) {
  return `${Math.abs(lon).toFixed(2)}°${lon >= 0 ? "E" : "W"}`;
}

function needsRetry(data: Report): boolean {
  const errors = Array.isArray(data.input_errors) ? data.input_errors : [];
  const missing = Array.isArray(data.missing_inputs) ? data.missing_inputs : [];
  const affected = new Set<string>(missing);
  errors.forEach((e) => {
    if (/^Shop photos/i.test(e)) affected.add("photos");
    else if (/^Voice note/i.test(e)) affected.add("voice");
    else if (/^Transaction data/i.test(e)) affected.add("transactions");
  });
  return affected.size >= 3;
}

// Phase 3 — P3-ST2 + Phase 2 — P2-ST1: verdict card colour helper
function verdictStyle(band: string): string {
  if (band === "Suitable") return "bg-green-600 text-white border-green-700";
  if (/needs|review/i.test(band)) return "bg-amber-500 text-white border-amber-600";
  return "bg-red-600 text-white border-red-700";
}

// Phase 2 — P2-ST2: chip colour helper
function chipColor(value: string | undefined): string {
  if (!value || value === "—") return "bg-slate-50 text-slate-500 border-slate-200";
  const v = value.toLowerCase();
  if (["strong", "high", "yes", "increasing"].includes(v)) return "bg-green-100 text-green-800 border-green-200";
  if (["moderate", "medium", "unknown", "stable"].includes(v)) return "bg-yellow-100 text-yellow-800 border-yellow-200";
  if (["low", "further", "no", "decreasing"].includes(v)) return "bg-red-100 text-red-800 border-red-200";
  return "bg-slate-50 text-slate-500 border-slate-200";
}

export default function Page() {
  // Phase 1 — P1-ST1: initial screen is "upload", pin/pinError removed
  const [screen, setScreen] = useState<"upload" | "report" | "history" | "retry">("upload");
  const [photos, setPhotos] = useState<File[]>([]);
  const [audio, setAudio] = useState<File | null>(null);
  const [csv, setCsv] = useState<File | null>(null);
  const [manualVoiceText, setManualVoiceText] = useState("");
  const [voiceLanguage, setVoiceLanguage] = useState("");
  const [recording, setRecording] = useState(false);
  const [recordingSaved, setRecordingSaved] = useState<number | null>(null);
  const [recordingElapsed, setRecordingElapsed] = useState(0);
  const recordingElapsedRef = useRef(0);

  useEffect(() => {
    if (!recording) return;
    setRecordingElapsed(0);
    recordingElapsedRef.current = 0;
    const id = setInterval(() => {
      recordingElapsedRef.current += 1;
      setRecordingElapsed((s) => s + 1);
    }, 1000);
    return () => clearInterval(id);
  }, [recording]);

  const [showMap, setShowMap] = useState(false);
  const [pinnedLocation, setPinnedLocation] = useState<{ lat: number; lon: number } | null>(null);
  const [expandedReason, setExpandedReason] = useState<ReasonKey | null>(null);
  const [activeStep, setActiveStep] = useState<1 | 2 | 3 | 4 | 5>(1);
  const [visionFill, setVisionFill] = useState(0);
  const [troubleExpanded, setTroubleExpanded] = useState(false);
  const [retryFocus, setRetryFocus] = useState<"photos" | "voice" | "transactions" | "location" | "documents" | null>(null);
  const [precomputedVision, setPrecomputedVision] = useState<any>(null);
  const [precomputedVoice, setPrecomputedVoice] = useState<any>(null);
  const [precomputedVisionLoading, setPrecomputedVisionLoading] = useState(false);
  const [precomputedVoiceLoading, setPrecomputedVoiceLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingPhase, setLoadingPhase] = useState<"finishing" | "generating" | "checking">("generating");
  const [processingSteps, setProcessingSteps] = useState<{ id: string; label: string; status: "waiting" | "active" | "done" }[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [vendorName, setVendorName] = useState("");
  const [shopAddress, setShopAddress] = useState("");
  const [vendorHistory, setVendorHistory] = useState<any[] | null>(null);
  const [vendorHistoryLoading, setVendorHistoryLoading] = useState(false);
  const [hasSavingsAccount, setHasSavingsAccount] = useState("");
  const [annualTurnover, setAnnualTurnover] = useState("");
  const [udyamNumber, setUdyamNumber] = useState("");
  const [documents, setDocuments] = useState<Record<string, File | null>>({
    gst_certificate: null,
    udyam_certificate: null,
    bank_statement: null,
    aadhaar_card: null,
    rent_agreement: null,
    trade_license: null,
  });
  // Phase 2 — P2-ST5: showDetails state for collapsible section
  const [showDetails, setShowDetails] = useState(false);

  const audioRef = useRef<HTMLInputElement>(null);
  const csvRef = useRef<HTMLInputElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const docRefs: Record<string, React.RefObject<HTMLInputElement | null>> = {
    gst_certificate: useRef<HTMLInputElement>(null),
    udyam_certificate: useRef<HTMLInputElement>(null),
    bank_statement: useRef<HTMLInputElement>(null),
    aadhaar_card: useRef<HTMLInputElement>(null),
    rent_agreement: useRef<HTMLInputElement>(null),
    trade_license: useRef<HTMLInputElement>(null),
  };
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordChunksRef = useRef<Blob[]>([]);
  const recordStartRef = useRef(0);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const mapRef = useRef<any>(null);
  const markerRef = useRef<any>(null);
  const precomputedVisionLoadingRef = useRef(false);
  const precomputedVoiceLoadingRef = useRef(false);
  const precomputedVisionRef = useRef<any>(null);
  const precomputedVoiceRef = useRef<any>(null);

  useEffect(() => {
    if (!loading) { setElapsed(0); return; }
    const id = setInterval(() => setElapsed(prev => prev + 1), 1000);
    return () => clearInterval(id);
  }, [loading]);

  const canSubmit = photos.length > 0 || audio !== null || csv !== null || Object.values(documents).some(Boolean);

  // Phase 1 — P1-ST1: authHeaders + handleAuthFailure removed

  const handleDocuments = useCallback((docType: string, file: File | null) => {
    setDocuments(prev => ({ ...prev, [docType]: file }));
  }, []);

  const recordingSupported =
    typeof window !== "undefined" &&
    typeof MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia;

  const handlePhotos = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const rawFiles = Array.from(e.target.files ?? []);
    const oversized = rawFiles.filter(f => f.size > 10 * 1024 * 1024);
    if (oversized.length > 0) {
      setError(`Photo too large (max 10MB): ${oversized.map(f => f.name).join(", ")}`);
      return;
    }
    setError(null);
    const files = rawFiles;
    setPhotos(files);
    if (files.length === 0) {
      setPrecomputedVision(null);
      precomputedVisionRef.current = null;
      return;
    }
    setPrecomputedVisionLoading(true);
    precomputedVisionLoadingRef.current = true;
    const fd = new FormData();
    files.forEach(f => fd.append("files", f));
    try {
      const res = await fetch(API_BASE + "/agents/vision", { method: "POST", body: fd });
      const data = await res.json();
      setPrecomputedVision(data);
      precomputedVisionRef.current = data;
    } catch {
      setPrecomputedVision(null);
      precomputedVisionRef.current = null;
    } finally {
      setPrecomputedVisionLoading(false);
      precomputedVisionLoadingRef.current = false;
    }
  }, []);

  const handleAudio = useCallback(async (file: File | null) => {
    if (file && file.size > 25 * 1024 * 1024) {
      setError("Audio file too large (max 25MB)");
      return;
    }
    setError(null);
    setAudio(file);
    if (!file) {
      setPrecomputedVoice(null);
      precomputedVoiceRef.current = null;
      return;
    }
    setPrecomputedVoiceLoading(true);
    precomputedVoiceLoadingRef.current = true;
    const fd = new FormData();
    fd.append("file", file);
    if (voiceLanguage) fd.append("language", voiceLanguage);
    try {
      const res = await fetch(API_BASE + "/agents/voice", { method: "POST", body: fd });
      const data = await res.json();
      setPrecomputedVoice(data);
      precomputedVoiceRef.current = data;
    } catch {
      setPrecomputedVoice(null);
      precomputedVoiceRef.current = null;
    } finally {
      setPrecomputedVoiceLoading(false);
      precomputedVoiceLoadingRef.current = false;
    }
  }, [voiceLanguage]);

  const toggleRecording = useCallback(async () => {
    if (recording) {
      if (mediaRecorderRef.current) {
        mediaRecorderRef.current.stop();
        mediaRecorderRef.current = null;
      }
      setRecording(false);
      return;
    }
    if (precomputedVoiceLoading) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioStreamRef.current = stream;
      const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg", "audio/mp4"];
      const mime = candidates.find((c) => MediaRecorder.isTypeSupported(c)) ?? "";
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      recordChunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data.size > 0) recordChunksRef.current.push(e.data); };
      rec.onstop = () => {
        const blob = new Blob(recordChunksRef.current, { type: rec.mimeType || "audio/webm" });
        const ext = blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "m4a" : "webm";
        const file = new File([blob], `recording.${ext}`, { type: blob.type });
        const secs = Math.max(1, recordingElapsedRef.current);
        handleAudio(file);
        setRecordingSaved(secs);
        audioStreamRef.current?.getTracks().forEach((t) => t.stop());
        audioStreamRef.current = null;
      };
      recordStartRef.current = Date.now();
      rec.start();
      mediaRecorderRef.current = rec;
      setRecording(true);
      setRecordingSaved(null);
    } catch {
      setError("Microphone access was denied — use the file upload instead.");
    }
  }, [recording, handleAudio, precomputedVoiceLoading]);

  useEffect(() => {
    if (!showMap) return;
    const doc = document;
    if (!doc.getElementById("leaflet-css")) {
      const link = doc.createElement("link");
      link.id = "leaflet-css";
      link.rel = "stylesheet";
      link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      doc.head.appendChild(link);
    }
    let cancelled = false;
    const init = () => {
      if (cancelled || !showMap) return;
      const L = (window as any).L;
      const mapEl = doc.getElementById("leaflet-map");
      if (!L || !mapEl || mapRef.current) return;
      const map = L.map(mapEl).setView([20.5937, 78.9629], 5);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
      }).addTo(map);
      if (pinnedLocation) {
        markerRef.current = L.marker([pinnedLocation.lat, pinnedLocation.lon]).addTo(map);
      }
      map.on("click", (e: any) => { setPinnedLocation({ lat: e.latlng.lat, lon: e.latlng.lng }); });
      setTimeout(() => map.invalidateSize(), 50);
      mapRef.current = map;
    };
    if (!doc.getElementById("leaflet-js")) {
      const s = doc.createElement("script");
      s.id = "leaflet-js";
      s.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      s.onload = init;
      doc.head.appendChild(s);
    } else { init(); }
    return () => {
      cancelled = true;
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
      markerRef.current = null;
    };
  }, [showMap]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !pinnedLocation) return;
    const L = (window as any).L;
    if (!L) return;
    if (markerRef.current) markerRef.current.remove();
    markerRef.current = L.marker([pinnedLocation.lat, pinnedLocation.lon]).addTo(map);
  }, [pinnedLocation]);

  useEffect(() => {
    if (precomputedVisionLoading) {
      setVisionFill(0);
      const id = setTimeout(() => setVisionFill(95), 150);
      return () => clearTimeout(id);
    }
    setVisionFill(100);
  }, [precomputedVisionLoading]);

  const [photoUrls, setPhotoUrls] = useState<string[]>([]);
  useEffect(() => {
    const urls = photos.map(f => URL.createObjectURL(f));
    setPhotoUrls(urls);
    return () => { urls.forEach(url => URL.revokeObjectURL(url)); };
  }, [photos]);

  // Phase 1 — P1-ST5: auto-advance useEffect removed
  // Phase 1 — P1-ST2: stepStatus updated — Location removed, Formal Status added
  const stepStatus = [
    { label: "Photos", done: photos.length > 0, required: true },
    { label: "Status", done: hasSavingsAccount !== "" || annualTurnover !== "" || udyamNumber.trim() !== "", required: false },
    { label: "Voice", done: audio !== null || manualVoiceText.trim() !== "", required: false },
    { label: "Transactions", done: csv !== null, required: false },
    { label: "Documents", done: Object.values(documents).some(Boolean), required: false },
  ];

  const handleSubmit = useCallback(async () => {
    if (precomputedVisionLoadingRef.current || precomputedVoiceLoadingRef.current) {
      setLoading(true);
      setLoadingPhase("finishing");
      while (precomputedVisionLoadingRef.current || precomputedVoiceLoadingRef.current) {
        await new Promise(r => setTimeout(r, 200));
      }
    }
    setLoading(true);
    setLoadingPhase("generating");
    setError(null);
    setVendorHistory(null);

    const hasPhotos = photos.length > 0;
    const hasVoice = audio !== null || manualVoiceText.trim() !== "";
    const hasTxns = csv !== null;
    const hasLocation = shopAddress.trim() !== "" || pinnedLocation !== null;
    const hasDocs = Object.values(documents).some(Boolean);

    const steps = [
      { id: "photos", label: "📸 Analyzing shop photos", status: (hasPhotos && precomputedVision && !precomputedVisionLoading) ? "done" as const : hasPhotos ? "active" as const : "waiting" as const },
      { id: "voice", label: "🎙 Processing voice note", status: (hasVoice && precomputedVoice && !precomputedVoiceLoading) ? "done" as const : hasVoice ? "active" as const : "waiting" as const },
      { id: "transactions", label: "📊 Calculating transaction patterns", status: hasTxns ? "active" as const : "waiting" as const },
      { id: "location", label: "📍 Verifying location", status: hasLocation ? "active" as const : "waiting" as const },
      { id: "documents", label: "📄 Reading official documents", status: hasDocs ? "active" as const : "waiting" as const },
      { id: "rag", label: "📚 Searching regulatory documents", status: "active" as const },
      { id: "synthesis", label: "🧠 Generating report with Granite", status: "waiting" as const },
    ];
    setProcessingSteps(steps);

    setTimeout(() => { setProcessingSteps(prev => prev.map(s => s.id === "transactions" ? { ...s, status: "done" as const } : s)); }, 600);
    setTimeout(() => { setProcessingSteps(prev => prev.map(s => s.id === "location" ? { ...s, status: "done" as const } : s)); }, hasLocation ? 800 : 200);
    setTimeout(() => { setProcessingSteps(prev => prev.map(s => s.id === "rag" ? { ...s, status: "done" as const, label: "📚 Searching regulatory documents ✓" } : s)); }, 1200);
    setTimeout(() => { setProcessingSteps(prev => prev.map(s => s.id === "synthesis" ? { ...s, status: "active" as const } : s)); }, 1400);

    try {
      let res;
      const visionResult = precomputedVisionRef.current;
      const voiceResult = precomputedVoiceRef.current;
      if (visionResult || voiceResult) {
        const fd = new FormData();
        if (visionResult) fd.append("vision_result", JSON.stringify(visionResult));
        if (voiceResult) fd.append("voice_result", JSON.stringify(voiceResult));
        if (manualVoiceText.trim()) fd.append("manual_voice_text", manualVoiceText);
        if (voiceLanguage) fd.append("voice_language", voiceLanguage);
        if (pinnedLocation) { fd.append("pin_lat", String(pinnedLocation.lat)); fd.append("pin_lon", String(pinnedLocation.lon)); }
        if (csv) fd.append("transactions", csv);
        for (const [, file] of Object.entries(documents)) { if (file) fd.append("documents", file, file.name); }
        if (vendorName) fd.append("vendor_name", vendorName);
        if (shopAddress) fd.append("shop_address", shopAddress);
        if (hasSavingsAccount) fd.append("has_savings_account", hasSavingsAccount);
        if (annualTurnover !== "") fd.append("annual_turnover", annualTurnover);
        if (udyamNumber) fd.append("udyam_number", udyamNumber);
        // Phase 1 — P1-ST1: no authHeaders
        res = await fetch(API_BASE + "/report/synthesize", { method: "POST", body: fd });
      } else {
        const fd = new FormData();
        for (const f of photos) fd.append("photos", f);
        if (audio) fd.append("voice", audio);
        if (manualVoiceText.trim()) fd.append("manual_voice_text", manualVoiceText);
        if (voiceLanguage) fd.append("voice_language", voiceLanguage);
        if (pinnedLocation) { fd.append("pin_lat", String(pinnedLocation.lat)); fd.append("pin_lon", String(pinnedLocation.lon)); }
        if (csv) fd.append("transactions", csv);
        for (const [, file] of Object.entries(documents)) { if (file) fd.append("documents", file, file.name); }
        if (vendorName) fd.append("vendor_name", vendorName);
        if (shopAddress) fd.append("shop_address", shopAddress);
        if (hasSavingsAccount) fd.append("has_savings_account", hasSavingsAccount);
        if (annualTurnover !== "") fd.append("annual_turnover", annualTurnover);
        if (udyamNumber) fd.append("udyam_number", udyamNumber);
        res = await fetch(API, { method: "POST", body: fd });
      }
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data: Report = await res.json();
      setReport(data);
      setLoadingPhase("checking");
      await new Promise((r) => setTimeout(r, 2000));
      setScreen(needsRetry(data) ? "retry" : "report");
      if (vendorName) {
        setVendorHistoryLoading(true);
        try {
          const vr = await fetch(API_BASE + "/vendors/" + encodeURIComponent(vendorName) + "/history");
          if (vr.ok) { const history = await vr.json(); setVendorHistory(history); }
        } catch { } finally { setVendorHistoryLoading(false); }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setProcessingSteps(prev => [...prev.map(s => ({ ...s, status: "done" as const })), { id: "ready", label: "✅ Report ready", status: "done" as const }]);
      setLoading(false);
    }
  }, [photos, audio, csv, precomputedVision, precomputedVoice, vendorName, shopAddress, manualVoiceText, voiceLanguage, pinnedLocation, documents]);

  const fetchReports = useCallback(async () => {
    setHistoryLoading(true);
    setError(null);
    try {
      const res = await fetch(API_BASE + "/reports");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ReportSummary[] = await res.json();
      setReports(data);
      setScreen("history");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    } finally { setHistoryLoading(false); }
  }, []);

  const viewReport = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(API_BASE + "/reports/" + id);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Report = await res.json();
      setReport(data);
      setScreen("report");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load report");
    } finally { setLoading(false); }
  }, []);

  const reset = useCallback(() => {
    setScreen("upload");
    setPhotos([]);
    setAudio(null);
    setCsv(null);
    setManualVoiceText("");
    setVoiceLanguage("");
    setRecording(false);
    setRecordingSaved(null);
    setRecordingElapsed(0);
    recordingElapsedRef.current = 0;
    setPinnedLocation(null);
    setShowMap(false);
    setRetryFocus(null);
    setActiveStep(1);
    setTroubleExpanded(false);
    setPrecomputedVision(null);
    setPrecomputedVoice(null);
    precomputedVisionRef.current = null;
    precomputedVoiceRef.current = null;
    setDocuments({ gst_certificate: null, udyam_certificate: null, bank_statement: null, aadhaar_card: null, rent_agreement: null, trade_license: null });
    setReport(null);
    setError(null);
    setShowDetails(false);
  }, []);


  // ─── REPORT SCREEN ────────────────────────────────────────────────────────
  if (screen === "report" && report) {
    const hasFinancial = report.transaction_count !== undefined;
    const ec = report.evidence_completeness;
    const docConfidence = !report.document_analysis?.documents_processed?.length
      ? "—"
      : report.document_analysis.documents_processed.length >= 3 ? "High"
      : report.document_analysis.documents_processed.length >= 1 ? "Medium"
      : "Low";
    const activityValue = report.trend ?? report.volatility ?? "—";
    const savingsVal = report.vendor_formal_status?.has_savings_account ?? "—";

    return (
      <main className="max-w-2xl mx-auto px-4 py-10">
        {/* Print CSS */}
        <style dangerouslySetInnerHTML={{ __html: `
          @media print {
            .no-print { display: none !important; }
            .print-show { display: block !important; }
            .print-header { display: block !important; }
            .print-footer { display: block !important; }
            .report-card { page-break-inside: avoid; break-inside: avoid; }
            body { font-size: 11pt; font-family: sans-serif; }
            @page { margin: 1.5cm; }
            * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
          }
          .print-header { display: none; }
          .print-footer { display: none; }
        ` }} />

        {/* Print-only header */}
        <div className="print-header mb-4">
          <p className="text-base font-bold">THELIGAI — Microenterprise Credit Assessment Report</p>
          {report.report_id && <p className="text-xs text-slate-500 font-mono">ID: {report.report_id}</p>}
          <p className="text-xs text-slate-500">Generated: {new Date().toLocaleDateString()}</p>
        </div>

        {/* 1. Header: Theligai title + Report ID + New Report button */}
        <div className="flex items-center justify-between mb-4 no-print">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Theligai</h1>
            {report.report_id && <p className="text-[11px] text-slate-400 font-mono">ID: {report.report_id}</p>}
          </div>
          <div className="flex items-center gap-2 no-print">
            <button
              type="button"
              onClick={() => window.print()}
              className="no-print flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition"
            >
              📄 Download PDF
            </button>
            <button onClick={reset} className="no-print text-sm text-slate-500 hover:text-slate-700 underline">
              New Report
            </button>
          </div>
        </div>

        <div className="space-y-4">

          {/* 2. ASSESSMENT BAND — large, prominent, colored box */}
          <div className={`report-card rounded-xl border p-4 md:p-6 ${verdictStyle(report.assessment_band)}`}>
            <p className="text-xs font-semibold uppercase tracking-wide opacity-80">Overall Assessment</p>
            <p className="mt-2 text-3xl font-bold leading-tight">{report.assessment_band}</p>
            <p className="mt-2 text-sm opacity-80">Assessed by Theligai — Officer review required before any credit decision</p>
          </div>

          {/* 3. PROFILE COMPLETENESS INDEX */}
          {report.profile_completeness && (
            <div className="report-card bg-indigo-50 rounded-xl border border-indigo-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">Profile Completeness Index</span>
              <p className="text-[10px] text-indigo-400 mt-0.5">{report.profile_completeness.label ?? "Reflects evidence gathered, not creditworthiness"}</p>
              <div className="mt-3 flex items-center gap-4">
                <span className="text-2xl font-bold text-indigo-900">{report.profile_completeness.completeness_tier}</span>
                <span className="text-sm text-indigo-600">{report.profile_completeness.completeness_score}%</span>
              </div>
              <div className="mt-2 h-2.5 rounded-full bg-indigo-100 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 to-indigo-400 rounded-full transition-all duration-500"
                  style={{ width: `${report.profile_completeness.completeness_score}%` }}
                />
              </div>
              {Array.isArray(report.profile_completeness.missing_for_next_tier) && report.profile_completeness.missing_for_next_tier.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {report.profile_completeness.missing_for_next_tier.map((item, i) => (
                    <li key={i} className="text-xs text-indigo-700 flex gap-1.5">
                      <span className="text-indigo-400 mt-0.5 shrink-0">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* 4. RISK INDICATORS */}
          {report.risk_indicators && (
            <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Risk Indicators</span>
              <p className={`mt-2 text-sm font-medium ${report.risk_indicators.indicators_triggered === 0 ? "text-emerald-700" : "text-amber-800"}`}>
                {report.risk_indicators.risk_summary}
              </p>
              {report.risk_indicators.indicators && typeof report.risk_indicators.indicators === "object" && report.risk_indicators.indicators_triggered > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {report.risk_indicators.indicators.high_transaction_volatility && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200">High transaction volatility</span>
                  )}
                  {report.risk_indicators.indicators.unverifiable_location && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200">Unverifiable location</span>
                  )}
                  {report.risk_indicators.indicators.cross_source_conflicts && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200">Cross-source conflicts detected</span>
                  )}
                  {report.risk_indicators.indicators.possible_photo_reuse && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200">Possible photo reuse</span>
                  )}
                  {report.risk_indicators.indicators.incomplete_evidence && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200">Incomplete evidence</span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 5. OFFICER GUIDANCE */}
          {report.officer_guidance && (
            <div className="report-card bg-blue-50 rounded-xl border border-blue-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Officer Guidance</span>
              <p className="mt-2 text-sm text-blue-900 leading-relaxed">{report.officer_guidance}</p>
            </div>
          )}

          {/* 6. ONBOARDING PATHWAY */}
          {Array.isArray(report.onboarding_pathway) && report.onboarding_pathway.length > 0 && (
            <div className="report-card bg-blue-50 rounded-xl border border-blue-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Onboarding Pathway</span>
              <p className="mt-1 text-base font-semibold text-blue-900">Recommended Next Steps for This Vendor</p>
              <p className="text-xs text-blue-500 mt-0.5">These steps help this vendor become eligible for formal credit disbursement.</p>
              <ul className="mt-3 space-y-1.5">
                {report.onboarding_pathway.map((step, i) => (
                  <li key={i} className="text-sm text-blue-900 flex gap-2">
                    <span className="text-blue-400 mt-0.5 shrink-0">→</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 7. BUSINESS TYPE */}
          {report.business_type && (
            <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Business Type</span>
              <p className="mt-1 text-lg font-semibold text-slate-900">{report.business_type}</p>
            </div>
          )}

          {/* 8. EVIDENCE BANDS — Revenue/Inventory/Digital with Why? */}
          {report.reasoning_trace && (
            report.reasoning_trace.revenue_consistency_reasoning ||
            report.reasoning_trace.inventory_observation_reasoning ||
            report.reasoning_trace.digital_activity_reasoning
          ) && (
            <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Evidence Bands</span>
              <div className="mt-3 divide-y divide-slate-100">
                {[
                  { label: "Revenue Consistency", value: report.revenue_consistency_band, reason: "revenue_consistency_reasoning" as ReasonKey },
                  { label: "Inventory Observation", value: report.inventory_observation_band, reason: "inventory_observation_reasoning" as ReasonKey },
                  { label: "Digital Activity", value: report.digital_activity_band, reason: "digital_activity_reasoning" as ReasonKey },
                ].map((row) => {
                  const reasonText = report.reasoning_trace?.[row.reason];
                  if (!reasonText) return null;
                  return (
                    <div key={row.label} className="py-2.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">{row.label}</span>
                          <span className={`px-2.5 py-0.5 text-[11px] font-semibold border rounded-full ${bandColor(row.value)}`}>
                            {row.value}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setExpandedReason(expandedReason === row.reason ? null : row.reason)}
                          className="no-print text-[11px] font-medium text-indigo-600 hover:text-indigo-800 underline underline-offset-2"
                        >
                          {expandedReason === row.reason ? "▲ Hide" : "▼ Why?"}
                        </button>
                      </div>
                      {expandedReason === row.reason && (
                        <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">{reasonText}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 9. CROSS-VERIFICATION MATRIX */}
          {report.source_agreement && (
            <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 px-4 pt-4 pb-3 md:px-6 md:pt-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Cross-Verification Matrix</span>
              <div className="mt-3 flex flex-col items-center select-none">
                <div className="flex items-center gap-0 w-full max-w-xs">
                  <div className="flex-1 text-center">
                    <div className="inline-flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-700">
                      <span className="text-base">📷</span> Photo
                    </div>
                  </div>
                  <div className="flex items-center gap-1 px-1">
                    <div className={`w-10 h-0.5 ${report.source_agreement.photo_voice === "agree" ? "bg-green-400" : report.source_agreement.photo_voice === "conflict" ? "bg-amber-400" : "bg-slate-200"}`} />
                    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold border ${AGREEMENT_COLORS[report.source_agreement.photo_voice || "insufficient_data"] || AGREEMENT_COLORS.insufficient_data}`}>
                      {report.source_agreement.photo_voice === "agree" ? "✓" : report.source_agreement.photo_voice === "conflict" ? "⚠" : "—"}
                    </span>
                    <div className={`w-10 h-0.5 ${report.source_agreement.photo_voice === "agree" ? "bg-green-400" : report.source_agreement.photo_voice === "conflict" ? "bg-amber-400" : "bg-slate-200"}`} />
                  </div>
                  <div className="flex-1 text-center">
                    <div className="inline-flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-700">
                      <span className="text-base">🎙️</span> Voice
                    </div>
                  </div>
                </div>
                <div className="flex justify-between w-full max-w-xs h-6">
                  <div className="flex flex-col items-center w-1/3">
                    <div className={`w-0.5 h-3 ${report.source_agreement.photo_transactions === "agree" ? "bg-green-400" : report.source_agreement.photo_transactions === "conflict" ? "bg-amber-400" : "bg-slate-200"}`} />
                  </div>
                  <div className="flex flex-col items-center w-1/3">
                    <div className={`w-0.5 h-3 ${report.source_agreement.voice_transactions === "agree" ? "bg-green-400" : report.source_agreement.voice_transactions === "conflict" ? "bg-amber-400" : "bg-slate-200"}`} />
                  </div>
                </div>
                <div className="flex justify-between w-full max-w-xs -mt-0.5">
                  <div className="flex justify-center w-1/3">
                    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold border ${AGREEMENT_COLORS[report.source_agreement.photo_transactions || "insufficient_data"] || AGREEMENT_COLORS.insufficient_data}`}>
                      {report.source_agreement.photo_transactions === "agree" ? "✓" : report.source_agreement.photo_transactions === "conflict" ? "⚠" : "—"}
                    </span>
                  </div>
                  <div className="flex justify-center w-1/3">
                    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold border ${AGREEMENT_COLORS[report.source_agreement.voice_transactions || "insufficient_data"] || AGREEMENT_COLORS.insufficient_data}`}>
                      {report.source_agreement.voice_transactions === "agree" ? "✓" : report.source_agreement.voice_transactions === "conflict" ? "⚠" : "—"}
                    </span>
                  </div>
                </div>
                <div className="mt-1 flex justify-center w-full max-w-xs">
                  <div className="inline-flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-700">
                    <span className="text-base">💰</span> Transactions
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 10. NEEDS OFFICER REVIEW — discrepancy flags */}
          {(report.photo_reuse_flag || (report.discrepancy_flags && report.discrepancy_flags.length > 0)) && (
            <div className="report-card bg-amber-50 rounded-xl border border-amber-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Needs Officer Review</span>
              <ul className="mt-2 space-y-1">
                {(Array.isArray(report.discrepancy_flags) ? report.discrepancy_flags : []).map((s, i) => (
                  <li key={i} className="text-sm text-amber-800 flex gap-2">
                    <span className="text-amber-400 mt-0.5 shrink-0">•</span>
                    <span>{s}</span>
                  </li>
                ))}
                {report.photo_reuse_flag && (
                  <li className="text-sm text-amber-800 flex gap-2">
                    <span className="text-amber-400 mt-0.5 shrink-0">•</span>
                    <span>{report.photo_reuse_flag}</span>
                  </li>
                )}
              </ul>
            </div>
          )}

          {/* 11. FINANCIAL EVIDENCE */}
          {hasFinancial && (
            <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Financial Evidence</span>
              <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-500">Total Inflow</span>
                  <span className="font-semibold text-slate-800">₹{report.total_inflow?.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Total Outflow</span>
                  <span className="font-semibold text-slate-800">₹{report.total_outflow?.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Transactions</span>
                  <span className="font-semibold text-slate-800">{report.transaction_count?.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Avg Transaction</span>
                  <span className="font-semibold text-slate-800">₹{report.average_transaction?.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Volatility</span>
                  <span className="font-semibold text-slate-800">{report.volatility ?? "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Trend</span>
                  <span className="font-semibold text-slate-800">{report.trend ?? "—"}</span>
                </div>
                <div className="flex justify-between col-span-2">
                  <span className="text-slate-500">Date Range</span>
                  <span className="font-semibold text-slate-800">
                    {report.earliest_date ?? "—"} &ndash; {report.latest_date ?? "—"}
                    {report.date_range_days != null && <span className="font-normal text-slate-400"> ({report.date_range_days} days)</span>}
                  </span>
                </div>
              </div>
              {report.format_notes && <p className="mt-3 text-[11px] text-slate-400">{report.format_notes}</p>}
            </div>
          )}

          {/* 12. DOCUMENT ANALYSIS */}
          {report.document_analysis && report.document_analysis.documents_processed?.length > 0 && (
            <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Document Analysis</span>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="text-xs text-slate-500 mr-1">Provided:</span>
                {report.document_analysis.documents_processed.map((doc) => (
                  <span key={doc} className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                    ✓ {doc.replace(/_/g, " ")}
                  </span>
                ))}
                {report.document_analysis.documents_missing.map((doc) => (
                  <span key={doc} className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-50 text-slate-500 border border-slate-200">
                    — {doc.replace(/_/g, " ")}
                  </span>
                ))}
                <span className={`ml-auto inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
                  (report.document_analysis as any)?.verification_signals
                    ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                    : "bg-slate-50 text-slate-500 border-slate-200"
                }`}>
                  Confidence: {docConfidence}
                </span>
              </div>
            </div>
          )}

          {/* 13. VENDOR FORMAL STATUS */}
          {report.vendor_formal_status && (
            <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Vendor Formal Status</span>
              <div className="mt-3 space-y-3">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-slate-600">Savings Account:</span>
                  <span className={`flex items-center gap-1.5 text-sm font-medium ${
                    report.vendor_formal_status.has_savings_account === "yes" ? "text-emerald-600"
                    : report.vendor_formal_status.has_savings_account === "no" ? "text-amber-600"
                    : "text-slate-600"
                  }`}>
                    {report.vendor_formal_status.has_savings_account === "yes" && "✅ Yes"}
                    {report.vendor_formal_status.has_savings_account === "no" && "⚠️ No"}
                    {report.vendor_formal_status.has_savings_account === "unknown" && "❓ Unknown"}
                  </span>
                </div>
                {report.vendor_formal_status.annual_turnover !== null && report.vendor_formal_status.annual_turnover !== undefined && (
                  <div className="pt-2 border-t border-slate-100">
                    <span className="text-sm text-slate-600">GST Status: </span>
                    <span className="text-sm font-semibold">
                      {report.vendor_formal_status.gst_required
                        ? "GST registration required (turnover ≥ ₹40 lakh)"
                        : report.vendor_formal_status.annual_turnover < 2000000
                        ? "GST registration not required (turnover < ₹20 lakh)"
                        : "GST required for service businesses only (₹20–40 lakh turnover)"}
                    </span>
                  </div>
                )}
                {report.vendor_formal_status.udyam_number && (
                  <div>
                    <span className="text-sm text-slate-600">Udyam Reg.: </span>
                    <span className="text-sm font-mono text-slate-800">{report.vendor_formal_status.udyam_number}</span>
                  </div>
                )}
                <p className="text-xs text-slate-500">Verification at <a href="https://udyamregistration.gov.in" target="_blank" rel="noopener noreferrer" className="underline text-blue-600">udyamregistration.gov.in</a></p>
              </div>
            </div>
          )}

          {/* 14. LOCATION VERIFICATION */}
          {report.location_verification && (
            <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Location Verification</span>
              <div className="mt-2">
                {report.location_verification.location_found ? (
                  <div>
                    <p className="text-sm text-emerald-700 flex items-center gap-1.5">
                      <span className="w-2 h-2 bg-emerald-500 rounded-full" />
                      Address verified against public map records
                    </p>
                    {report.location_verification.address && <p className="mt-1 text-xs text-slate-400">{report.location_verification.address}</p>}
                  </div>
                ) : (
                  <p className="text-sm text-slate-500">
                    Address could not be verified against public records
                    {report.location_verification.error && <span className="text-xs text-slate-400"> ({report.location_verification.error})</span>}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* hr divider */}
          <hr className="border-0 border-t border-gray-200 my-2" />

          {/* Collapsible: Scheme Note, Evidence Summary, Assessment History, Evidence Completeness */}
          <button
            type="button"
            onClick={() => setShowDetails(s => !s)}
            className="no-print w-full py-3 px-4 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition flex items-center justify-center gap-2"
          >
            {showDetails ? "Hide Report Details ▲" : "Show Report Details ▼"}
          </button>

          <div className={`${showDetails ? "block" : "hidden"} print-show space-y-4`}>

            {/* 15. SCHEME NOTE + Sources */}
            <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Scheme Note</span>
              <p className="mt-2 text-sm text-slate-700 leading-relaxed">{report.relevant_scheme_note}</p>
              {(Array.isArray(report.sources_cited) ? report.sources_cited : []).length > 0 && (
                <p className="mt-3 text-[11px] text-slate-400">Sources referenced: {(report.sources_cited ?? []).join(", ")}</p>
              )}
            </div>

            {/* 16. EVIDENCE SUMMARY */}
            <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 p-4 md:p-6">
              <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Evidence Summary</span>
              <ul className="mt-2 space-y-1">
                {(Array.isArray(report.evidence_summary) ? report.evidence_summary : []).map((s, i) => (
                  <li key={i} className="text-sm text-slate-700 flex gap-2">
                    <span className="text-slate-300 mt-0.5 shrink-0">•</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* 17. ASSESSMENT HISTORY */}
            {vendorHistory && vendorHistory.length > 0 && report.vendor_name && (
              <div className="report-card bg-white rounded-xl shadow-sm border border-slate-200 p-4 md:p-6">
                <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Assessment History for {report.vendor_name}</span>
                <div className="mt-3 space-y-1.5 text-sm">
                  {(Array.isArray(vendorHistory) ? vendorHistory : []).map((entry, i) => {
                    const trend = i === vendorHistory!.length - 1 ? "Stable" : bandTrend(report.assessment_band, entry.assessment_band);
                    const trendColor = trend === "Improved" ? "text-emerald-600" : trend === "Declined" ? "text-red-600" : "text-slate-400";
                    const trendArrow = trend === "Improved" ? "↑" : trend === "Declined" ? "↓" : "→";
                    return (
                      <div key={entry.report_id} className="flex items-center justify-between text-sm">
                        <span className="text-slate-500 text-xs">{new Date(entry.generated_at).toLocaleDateString()}</span>
                        <span className={`px-2 py-0.5 text-[11px] font-semibold border rounded-full ${bandColor(entry.assessment_band as Band)}`}>
                          {entry.assessment_band}
                        </span>
                        {i < vendorHistory!.length - 1 && (
                          <span className={`text-xs font-medium ${trendColor}`}>{trendArrow} {trend}</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Evidence completeness dots */}
            {ec && (
              <div className="report-card bg-slate-50 rounded-xl border border-slate-200 p-3 md:p-5">
                <div className="flex items-center gap-3">
                  <div className="flex gap-1">
                    {Array.from({ length: ec.sources_total }, (_, i) => (
                      <span key={i} className={`w-3 h-3 rounded-full border-2 ${i < ec.sources_provided ? "bg-indigo-500 border-indigo-500" : "bg-white border-slate-300"}`} />
                    ))}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-700">{ec.sources_provided} of {ec.sources_total} evidence sources provided</p>
                    <p className="text-xs text-slate-500">{ec.discrepancies_found ? "Discrepancies flagged — see above" : "No discrepancies found"}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">Reflects how much evidence was available, not business quality.</p>
                  </div>
                </div>
              </div>
            )}

            {/* Input errors */}
            {Array.isArray(report.input_errors) && report.input_errors.length > 0 && (
              <div className="report-card bg-red-50 rounded-xl border border-red-200 p-4 md:p-6 text-sm">
                <span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">Input Errors</span>
                <ul className="mt-2 space-y-1">
                  {report.input_errors.map((e, i) => (
                    <li key={i} className="text-red-800 flex gap-2">
                      <span className="text-red-400 mt-0.5 shrink-0">•</span>
                      <span>{e}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Missing inputs */}
            {report.missing_inputs.length > 0 && (
              <div className="report-card bg-amber-50 rounded-xl border border-amber-200 p-4 text-sm text-amber-800">
                Note: no{" "}
                {report.missing_inputs.map((m) => m.replace("photos", "shop photos").replace("voice", "voice note")).join(" or ")}{" "}
                were provided for this assessment.
              </div>
            )}

            {/* 18. Footer: PII notice + disclaimer */}
            {report.report_id && <p className="text-[11px] font-mono text-slate-400 text-center">Report ID: {report.report_id}</p>}
            <p className="text-[11px] text-slate-400 text-center">🔒 Voice data PII-masked before AI processing (DPDPA 2023)</p>
            <p className="text-[11px] text-slate-300 text-center">This report was generated by an AI pipeline. All outputs should be verified by a field officer before decision-making.</p>
          </div>

          {/* Print footer */}
          <div className="print-footer mt-6 pt-4 border-t border-gray-200">
            <p className="text-xs text-slate-500">This report is for officer reference only. Not a credit decision. Human officer review required.</p>
          </div>

        </div>
      </main>
    );
  }

  // ─── HISTORY SCREEN ───────────────────────────────────────────────────────
  if (screen === "history") {
    return (
      <main className="max-w-2xl mx-auto px-4 py-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Theligai</h1>
            <p className="text-xs text-slate-400">Business Readiness Report for MSME Field Assessment</p>
          </div>
          <button onClick={() => setScreen("upload")} className="text-sm text-slate-500 hover:text-slate-700 underline">Back</button>
        </div>
        <div className="space-y-4">
          {historyLoading ? (
            <div className="flex items-center justify-center gap-2 py-20 text-sm text-slate-500">
              <span className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <span>Loading reports…</span>
            </div>
          ) : reports.length === 0 ? (
            <div className="text-center py-20 text-sm text-slate-400">No past assessments found.</div>
          ) : (
            reports.map((r) => (
              <div key={r.report_id} className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900 truncate">{r.business_type ?? "Not specified"}</p>
                  <p className="text-[11px] text-slate-400 mt-0.5">{new Date(r.generated_at).toLocaleDateString()} at {new Date(r.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className={`px-2.5 py-0.5 text-[11px] font-semibold border rounded-full ${bandColor(r.assessment_band as Band)}`}>{r.assessment_band}</span>
                  <button onClick={() => viewReport(r.report_id)} className="text-xs font-medium text-indigo-600 hover:text-indigo-800 underline underline-offset-2">View Full Report</button>
                </div>
              </div>
            ))
          )}
          {error && screen === "history" && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{error}</div>
          )}
        </div>
        <p className="mt-8 text-[11px] text-slate-300 text-center">Showing all cached assessments.</p>
      </main>
    );
  }

  // ─── RETRY SCREEN ─────────────────────────────────────────────────────────
  if (screen === "retry" && report) {
    const inputErrors = Array.isArray(report.input_errors) ? report.input_errors : [];
    const missing = Array.isArray(report.missing_inputs) ? report.missing_inputs : [];
    const MISSING_LABELS: Record<string, string> = { photos: "Shop photos", voice: "Voice note", transactions: "Transaction data" };
    const MISSING_HELP: Record<string, string> = {
      photos: "Shop photos help verify the premises and inventory — adding them strengthens the inventory observation band.",
      voice: "A voice note adds your field observations — adding it strengthens the business context and cross-verification.",
      transactions: "No transaction data provided — adding this improves the financial evidence section.",
    };
    const retryInput = (e: string): "photos" | "voice" | "transactions" | null => {
      if (/^Shop photos/i.test(e)) return "photos";
      if (/^Voice note/i.test(e)) return "voice";
      if (/^Transaction data/i.test(e)) return "transactions";
      return null;
    };
    const uploadLabel = (k: "photos" | "voice" | "transactions") =>
      k === "photos" ? "photos" : k === "voice" ? "a voice note or typed field notes" : "the transaction CSV";

    return (
      <main className="max-w-xl mx-auto px-4 py-10">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Theligai</h1>
            <p className="text-xs text-slate-400">Business Readiness Report for MSME Field Assessment</p>
          </div>
          <button onClick={reset} className="text-sm text-slate-500 hover:text-slate-700 underline">New Report</button>
        </div>
        <div className="mt-8 bg-amber-50 rounded-xl border border-amber-200 p-5">
          <h2 className="text-base font-semibold text-amber-900">Some inputs need attention</h2>
          <p className="mt-1 text-sm text-amber-800">The assessment couldn&apos;t use any of the three evidence sources. Fix the items below, or generate a report with what you have.</p>
        </div>
        <div className="mt-6 space-y-4">
          {inputErrors.map((e, i) => {
            const input = retryInput(e);
            return (
              <div key={i} className="bg-red-50 rounded-xl border border-red-200 p-4">
                <p className="text-sm text-red-800">{e}</p>
                {input && (
                  <button
                    type="button"
                    onClick={() => {
                      setRetryFocus(input);
                      // Phase 1 P1-ST2: updated step numbers — voice→3, transactions→4
                      setActiveStep(input === "photos" ? 1 : input === "voice" ? 3 : 4);
                      setScreen("upload");
                    }}
                    className="mt-2.5 text-xs font-medium text-red-600 hover:text-red-800 underline underline-offset-2"
                  >
                    Re-upload {uploadLabel(input)}
                  </button>
                )}
              </div>
            );
          })}
          {missing.map((m) => (
            <div key={m} className="bg-yellow-50 rounded-xl border border-yellow-200 p-4">
              <p className="text-sm font-medium text-yellow-900">{MISSING_LABELS[m] ?? "Input"} not provided</p>
              <p className="mt-1 text-xs text-yellow-800">{MISSING_HELP[m] ?? "Adding this input improves the report."}</p>
            </div>
          ))}
          <div className="flex flex-col gap-2 pt-2">
            <button onClick={() => setScreen("report")} className="w-full py-3 px-6 rounded-xl text-sm font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition">
              Generate with available inputs
            </button>
            <button onClick={() => { setRetryFocus(null); setScreen("upload"); setActiveStep(1); }} className="w-full py-3 px-6 rounded-xl text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition">
              Fix and regenerate
            </button>
          </div>
        </div>
      </main>
    );
  }

  // ─── UPLOAD SCREEN ────────────────────────────────────────────────────────
  return (
    <main className="max-w-2xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Theligai</h1>
          <p className="text-xs text-slate-400">Business Readiness Report for MSME Field Assessment</p>
        </div>
        <button onClick={fetchReports} className="text-sm text-slate-400 hover:text-slate-600 underline underline-offset-2">
          View Past Assessments
        </button>
      </div>

      {/* Phase 1 P1-ST2: Step nav — Photos · Status · Voice · Transactions · Documents */}
      <div className="mt-6 grid grid-cols-5 gap-1.5">
        {[
          { n: 1 as const, label: "Photos", icon: "📷" },
          { n: 2 as const, label: "Status", icon: "📋" },
          { n: 3 as const, label: "Voice", icon: "🎙" },
          { n: 4 as const, label: "Transactions", icon: "💰" },
          { n: 5 as const, label: "Documents", icon: "📄" },
        ].map((s) => {
          const isActive = activeStep === s.n;
          const st = stepStatus[s.n - 1];
          return (
            <button
              key={s.n}
              type="button"
              onClick={() => setActiveStep(s.n)}
              className={`rounded-xl border p-2 text-center transition ${
                isActive
                  ? "border-indigo-300 bg-indigo-50 shadow-sm"
                  : "border-slate-200 bg-white hover:border-indigo-200 hover:bg-indigo-50/50"
              }`}
            >
              <span className="block text-lg leading-none">{s.icon}</span>
              <span className="block text-[11px] font-medium text-slate-700 mt-1">{s.label}</span>
              <span className={`mt-1 inline-flex w-2 h-2 rounded-full ${st.done ? "bg-emerald-500" : st.required ? "bg-red-400" : "bg-amber-400"}`} />
            </button>
          );
        })}
      </div>

      {retryFocus && (
        <div className="mt-4 bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-800 flex items-center justify-between gap-3">
          <span>Fix the highlighted input ({retryFocus === "photos" ? "Shop Photos" : retryFocus === "voice" ? "Voice Note" : "Transaction Export"}) below, then click Generate Report again.</span>
          <button type="button" onClick={() => setRetryFocus(null)} className="shrink-0 underline text-red-700 hover:text-red-900">dismiss</button>
        </div>
      )}

      <div className="mt-4 space-y-6">

        {/* ── STEP 1: Shop Photos ─────────────────────────────────────────── */}
        {activeStep === 1 && (
          <div className={`bg-white rounded-xl shadow-sm border p-6 ${retryFocus === "photos" ? "border-red-300 ring-2 ring-red-200" : "border-slate-200"}`}>
            <div className="flex items-center gap-3">
              <span className="flex items-center justify-center w-10 h-10 rounded-full bg-indigo-600 text-white text-base font-bold">1</span>
              <h2 className="text-lg font-semibold text-slate-900">Upload Shop Photos</h2>
              {photos.length > 0 && <span className="ml-auto text-sm font-medium text-emerald-600">✓ {photos.length} selected</span>}
            </div>
            <p className="mt-1 text-sm text-gray-500">Photos help us identify the business and check evidence.</p>
            <div className="mt-4">
              <label className="flex flex-col items-center justify-center min-h-24 px-4 py-6 rounded-xl border-2 border-dashed border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer transition">
                <span className="text-2xl">🖼</span>
                <span className="block text-base font-semibold mt-2">Upload Shop Photos</span>
                <span className="block text-xs text-gray-500 mt-0.5">Choose files from your device</span>
                <input ref={photoInputRef} type="file" accept="image/*" multiple onChange={handlePhotos} className="hidden" />
              </label>
            </div>
            {photos.length > 0 && (
              <>
                <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
                  {photos.map((f, i) => (
                    <div key={i} className="relative group shrink-0">
                      <img src={photoUrls[i]} alt="" className="w-24 h-24 object-cover rounded-lg border border-slate-200" />
                      <button
                        type="button"
                        onClick={() => { const np = photos.filter((_, j) => j !== i); setPhotos(np); if (np.length === 0) setPrecomputedVision(null); }}
                        className="absolute -top-1.5 -right-1.5 w-6 h-6 bg-red-500 text-white text-xs rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition"
                      >×</button>
                    </div>
                  ))}
                </div>
                {/* Phase 1 P1-ST4: Change re-picker for photos */}
                <button
                  type="button"
                  onClick={() => photoInputRef.current?.click()}
                  className="mt-2 text-xs text-indigo-600 hover:text-indigo-800 underline underline-offset-2"
                >
                  Change photos
                </button>
              </>
            )}
            {precomputedVisionLoading && (
              <div className="mt-4">
                <p className="text-xs text-indigo-600 flex items-center gap-1.5">
                  <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
                  🔍 Analyzing photos...
                </p>
                <div className="mt-2 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-indigo-500 via-indigo-400 to-teal-400 animate-pulse" style={{ width: `${visionFill}%`, transition: "width 20s linear" }} />
                </div>
              </div>
            )}
            {!precomputedVisionLoading && precomputedVision && photos.length > 0 && (
              <div className="mt-4">
                <div className="h-1.5 rounded-full bg-emerald-500" />
                <p className="mt-2 text-xs text-emerald-600">
                  ✅ Photos analyzed — {photos.length} photo{photos.length === 1 ? "" : "s"} processed
                  {precomputedVision.summary ? ` — ${String(precomputedVision.summary).slice(0, 60)}${String(precomputedVision.summary).length > 60 ? "…" : ""}` : ""}
                </p>
              </div>
            )}
            {/* Phase 1 P1-ST5: Next button always enabled, no disabled prop */}
            <button type="button" onClick={() => setActiveStep(2)} className="mt-4 w-full py-3.5 rounded-xl text-base font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition">
              Next: Vendor Status →
            </button>
          </div>
        )}

        {/* ── STEP 2: Vendor Formal Status ────────────────────────────────── */}
        {activeStep === 2 && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            {/* Phase 1 P1-ST3: Back button */}
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => setActiveStep(1)} className="mr-1 text-sm text-gray-500 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition shrink-0">← Back</button>
              <span className="flex items-center justify-center w-10 h-10 rounded-full bg-indigo-600 text-white text-base font-bold">2</span>
              <h2 className="text-lg font-semibold text-slate-900">Vendor Formal Status</h2>
              <span className="text-sm text-gray-500">optional</span>
            </div>
            <div className="mt-5 bg-slate-50 rounded-xl border border-slate-200 p-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                <label className="block text-xs font-medium text-slate-600">Does this vendor have a savings account?</label>
                <div className="flex gap-3">
                  {["yes", "no", "unknown"].map((val) => (
                    <label key={val} className="flex items-center gap-1.5 cursor-pointer">
                      <input type="radio" name="savings_account" value={val} className="accent-indigo-600" checked={hasSavingsAccount === val} onChange={() => setHasSavingsAccount(val)} />
                      <span className="text-sm text-gray-700 capitalize">{val}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="mb-3">
                <label className="block text-xs font-medium text-slate-600">Estimated annual turnover (₹)</label>
                <input
                  type="number"
                  value={annualTurnover}
                  onChange={(e) => setAnnualTurnover(e.target.value)}
                  placeholder="e.g., 1500000"
                  className="mt-1 block w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
                <p className="mt-1 text-xs text-gray-500">
                  {(() => {
                    const val = parseFloat(annualTurnover);
                    if (!val || val === 0) return "Enter turnover to see GST requirement";
                    if (val < 2000000) return "GST registration not required at this turnover level";
                    if (val < 4000000) return "GST required for service businesses, not required for goods traders";
                    return "GST registration required";
                  })()}
                </p>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600">Udyam Registration Number</label>
                <input
                  type="text"
                  value={udyamNumber}
                  onChange={(e) => setUdyamNumber(e.target.value)}
                  placeholder="UDYAM-XX-00-0000000"
                  className="mt-1 block w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              </div>
            </div>
            <button type="button" onClick={() => setActiveStep(3)} className="mt-4 w-full py-3.5 rounded-xl text-base font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition">
              Next: Voice Notes →
            </button>
          </div>
        )}

        {/* ── STEP 3: Voice Note ──────────────────────────────────────────── */}
        {activeStep === 3 && (
          <div className={`bg-white rounded-xl shadow-sm border p-6 ${retryFocus === "voice" ? "border-red-300 ring-2 ring-red-200" : "border-slate-200"}`}>
            {/* Phase 1 P1-ST3: Back button */}
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => setActiveStep(2)} className="mr-1 text-sm text-gray-500 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition shrink-0">← Back</button>
              <span className="flex items-center justify-center w-10 h-10 rounded-full bg-indigo-600 text-white text-base font-bold">3</span>
              <h2 className="text-lg font-semibold text-slate-900">Voice or Text Field Notes</h2>
              <span className="text-sm text-gray-500">optional</span>
            </div>
            <div className="mt-5 flex flex-col items-center">
              {recordingSupported ? (
                <>
                  <div className="relative">
                    {recording && <span className="absolute -inset-1.5 rounded-full bg-red-400/40 animate-ping" />}
                    <button
                      type="button"
                      onClick={toggleRecording}
                      disabled={precomputedVoiceLoading}
                      className={`relative flex items-center justify-center w-24 h-24 rounded-full text-3xl font-semibold transition ${
                        recording ? "bg-red-600 text-white"
                        : precomputedVoiceLoading ? "bg-slate-200 text-slate-400 cursor-not-allowed"
                        : "bg-indigo-600 text-white hover:bg-indigo-700"
                      }`}
                    >🎙</button>
                  </div>
                  <p className="mt-3 text-base font-medium text-slate-800">{recording ? "Recording... tap to stop" : "Tap to Record"}</p>
                  {recording && (
                    <p className="mt-1 text-xs font-medium text-red-600 flex items-center gap-1.5">
                      <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                      Recording... {recordingElapsed}s
                    </p>
                  )}
                  {!recording && recordingSaved !== null && (
                    <div className="mt-2 flex items-center gap-3">
                      <p className="text-xs text-emerald-600">✓ Recording saved ({recordingSaved}s)</p>
                      <button type="button" onClick={() => { setRecordingSaved(null); handleAudio(null); }} className="text-xs text-indigo-600 hover:text-indigo-800 underline underline-offset-2">Re-record</button>
                      {/* Phase 1 P1-ST4: Upload file instead */}
                      <button type="button" onClick={() => audioRef.current?.click()} className="text-xs text-indigo-600 hover:text-indigo-800 underline underline-offset-2">Upload file instead</button>
                    </div>
                  )}
                </>
              ) : (
                <p className="mt-2 text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">Recording requires HTTPS — please upload an audio file below.</p>
              )}
              {precomputedVoiceLoading && (
                <p className="mt-2 text-xs text-indigo-600 flex items-center gap-1.5">
                  <span className="w-3 h-3 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                  ⏳ Transcribing...
                </p>
              )}
              {!precomputedVoiceLoading && precomputedVoice && audio && !precomputedVoice.transcription_failed && (
                <div className="mt-2 text-center">
                  <p className="text-xs text-emerald-600 font-medium">✅ Voice note ready</p>
                  {(precomputedVoice.transcript_pii_scrubbed || precomputedVoice.transcript) && (
                    <p className="mt-1 text-xs text-slate-500 italic max-w-xs">
                      &quot;{String(precomputedVoice.transcript_pii_scrubbed || precomputedVoice.transcript).slice(0, 60)}{String(precomputedVoice.transcript_pii_scrubbed || precomputedVoice.transcript).length > 60 ? "…" : ""}&quot;
                    </p>
                  )}
                </div>
              )}
              {!precomputedVoiceLoading && precomputedVoice?.transcription_failed && (
                <p className="mt-2 text-xs text-amber-600 text-center">Couldn&apos;t transcribe this voice note — try again, upload a file, or type your notes below.</p>
              )}
            </div>
            <p className="mt-5 text-xs text-gray-500 uppercase tracking-wide">Or upload an audio file</p>
            <input ref={audioRef} type="file" accept="audio/*" onChange={(e) => handleAudio(e.target.files?.[0] ?? null)} className="mt-1.5 block w-full text-sm text-gray-500 file:mr-3 file:py-3 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer" />
            {audio && (
              <p className="mt-2 text-sm text-slate-600 flex items-center gap-2">
                <span>✓ {audio.name}</span>
                <button type="button" onClick={() => { handleAudio(null); if (audioRef.current) audioRef.current.value = ""; }} className="text-red-500 hover:text-red-700 text-xs">remove</button>
                {/* Phase 1 P1-ST4: Change audio file */}
                <button type="button" onClick={() => { if (audioRef.current) { audioRef.current.value = ""; audioRef.current.click(); } }} className="text-xs text-indigo-600 hover:text-indigo-800 underline underline-offset-2 ml-1">Change</button>
              </p>
            )}
            {audio && (
              <>
                <label htmlFor="voice-language" className="mt-4 block text-sm font-medium text-slate-700">Voice language</label>
                <select id="voice-language" value={voiceLanguage} onChange={(e) => setVoiceLanguage(e.target.value)} className="mt-1.5 block w-full min-h-12 rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400">
                  <option value="">Auto-detect</option>
                  <option value="en">English</option>
                  <option value="ta">Tamil</option>
                  <option value="hi">Hindi</option>
                  <option value="kn">Kannada</option>
                  <option value="te">Telugu</option>
                  <option value="mr">Marathi</option>
                </select>
              </>
            )}
            <div className="mt-4">
              <button type="button" onClick={() => setTroubleExpanded(!troubleExpanded)} className="py-2 text-sm font-medium text-indigo-600 hover:text-indigo-800 underline underline-offset-2">Having trouble recording?</button>
              {(troubleExpanded || precomputedVoice?.transcription_failed) && (
                <div className="mt-2">
                  <label htmlFor="manual-voice" className="block text-sm font-medium text-slate-700">Type your field notes instead:</label>
                  <textarea id="manual-voice" value={manualVoiceText} onChange={(e) => setManualVoiceText(e.target.value)} rows={3} placeholder="e.g. Kirana shop, selling groceries and snacks, 3 years running, near the bus stand" className="mt-1.5 block w-full rounded-lg border border-slate-200 px-3 py-3 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400" />
                </div>
              )}
            </div>
            <button type="button" onClick={() => setActiveStep(4)} className="mt-4 w-full py-3.5 rounded-xl text-base font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition">
              Next: Transaction Records →
            </button>
          </div>
        )}

        {/* ── STEP 4: Transaction Records ─────────────────────────────────── */}
        {activeStep === 4 && (
          <div className={`bg-white rounded-xl shadow-sm border p-6 ${retryFocus === "transactions" ? "border-red-300 ring-2 ring-red-200" : "border-slate-200"}`}>
            {/* Phase 1 P1-ST3: Back button */}
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => setActiveStep(3)} className="mr-1 text-sm text-gray-500 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition shrink-0">← Back</button>
              <span className="flex items-center justify-center w-10 h-10 rounded-full bg-indigo-600 text-white text-base font-bold">4</span>
              <h2 className="text-lg font-semibold text-slate-900">Transaction Records</h2>
              <span className="text-sm text-gray-500">optional</span>
            </div>
            <p className="mt-1 text-sm text-gray-500">Format: date, type (credit/debit), amount</p>
            <input ref={csvRef} type="file" accept=".csv,.xlsx" onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              if (f && f.size > 5 * 1024 * 1024) { setError("CSV too large (max 5MB)"); return; }
              setError(null);
              setCsv(f);
            }} className="mt-2 block w-full text-sm text-gray-500 file:mr-3 file:py-3 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer" />
            {csv && (
              <p className="mt-2 text-xs text-emerald-600 flex items-center gap-1.5">
                <span className="w-2 h-2 bg-emerald-500 rounded-full" />
                ✅ Ready — {csv.name}
                <button type="button" onClick={() => { setCsv(null); if (csvRef.current) csvRef.current.value = ""; }} className="text-red-500 hover:text-red-700 underline ml-1">remove</button>
                {/* Phase 1 P1-ST4: Change CSV */}
                <button type="button" onClick={() => { if (csvRef.current) { csvRef.current.value = ""; csvRef.current.click(); } }} className="text-xs text-indigo-600 hover:text-indigo-800 underline underline-offset-2 ml-1">Change</button>
              </p>
            )}
            <a href="data:text/csv;charset=utf-8,date,type,amount%0A2026-05-01,credit,1200%0A2026-05-03,debit,450%0A2026-05-07,credit,1800%0A2026-05-12,debit,600%0A2026-05-15,credit,2100%0A2026-05-20,debit,750" download="sample_transactions.csv" className="mt-3 inline-block py-2 text-sm font-medium text-indigo-600 hover:text-indigo-800 underline underline-offset-2">Download sample CSV</a>
            <button type="button" onClick={() => setActiveStep(5)} className="mt-4 w-full py-3.5 rounded-xl text-base font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition">
              Next: Official Documents →
            </button>
          </div>
        )}

        {/* ── STEP 5: Official Documents + Location ───────────────────────── */}
        {activeStep === 5 && (
          <div className={`bg-white rounded-xl shadow-sm border p-6 ${retryFocus === "documents" ? "border-red-300 ring-2 ring-red-200" : "border-slate-200"}`}>
            {/* Phase 1 P1-ST3: Back button */}
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => setActiveStep(4)} className="mr-1 text-sm text-gray-500 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition shrink-0">← Back</button>
              <span className="flex items-center justify-center w-10 h-10 rounded-full bg-indigo-600 text-white text-base font-bold">5</span>
              <h2 className="text-lg font-semibold text-slate-900">Official Documents</h2>
              <span className="text-sm text-gray-500">All optional</span>
            </div>
            <p className="mt-1 text-sm text-gray-500">Upload any available documents — more documents improve report confidence.</p>
            {(() => {
              const docCount = Object.values(documents).filter(Boolean).length;
              const confidence = docCount === 0 ? "Low" : docCount <= 2 ? "Medium" : "High";
              const confColor = confidence === "High" ? "text-emerald-700 bg-emerald-50" : confidence === "Medium" ? "text-amber-700 bg-amber-50" : "text-slate-500 bg-slate-50";
              return <p className={`mt-2 text-xs font-medium inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full ${confColor}`}>📄 {docCount} of 6 documents — {confidence} confidence</p>;
            })()}
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
              {([
                { key: "gst_certificate", label: "GST Certificate", help: "Verifies tax compliance and business legitimacy", accept: ".pdf,.jpg,.jpeg,.png" },
                { key: "udyam_certificate", label: "Udyam/MSME Certificate", help: "Confirms formal MSME registration", accept: ".pdf,.jpg,.jpeg,.png" },
                { key: "bank_statement", label: "Bank Statement (last 3 months)", help: "Corroborates transaction records", accept: ".pdf,.jpg,.jpeg,.png" },
                { key: "aadhaar_card", label: "Aadhaar Card", help: "Identity verification (PII masked before processing)", accept: ".pdf,.jpg,.jpeg,.png" },
                { key: "rent_agreement", label: "Rent Agreement", help: "Confirms business premises and tenure", accept: ".pdf,.jpg,.jpeg,.png" },
                { key: "trade_license", label: "Trade License", help: "Verifies local authority approval", accept: ".pdf,.jpg,.jpeg,.png" },
              ] as const).map(({ key, label, help, accept }) => {
                const file = documents[key];
                return (
                  <div key={key} className="border border-slate-200 rounded-xl p-3">
                    <p className="text-sm font-medium text-slate-800">{label}</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">{help}</p>
                    <input ref={docRefs[key] as any} type="file" accept={accept} onChange={(e) => {
                      const f = e.target.files?.[0] ?? null;
                      if (f && f.size > 10 * 1024 * 1024) { setError("Document too large (max 10MB)"); return; }
                      setError(null);
                      handleDocuments(key, f);
                    }} className="mt-2 block w-full text-xs text-gray-500 file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer" />
                    {file && (
                      <p className="mt-1.5 text-xs text-emerald-600 flex items-center gap-1 flex-wrap">
                        <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
                        ✓ {file.name}
                        <button type="button" onClick={() => { handleDocuments(key, null); if (docRefs[key]?.current) docRefs[key].current!.value = ""; }} className="text-red-500 hover:text-red-700 ml-auto underline">remove</button>
                        {/* Phase 1 P1-ST4: Change document */}
                        <button type="button" onClick={() => { const r = docRefs[key]; if (r?.current) { r.current.value = ""; r.current.click(); } }} className="text-xs text-indigo-600 hover:text-indigo-800 underline underline-offset-2 ml-1">Change</button>
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Phase 1 P1-ST2: Location inputs absorbed into Step 5 */}
            <div className="mt-6 border-t border-slate-100 pt-5">
              <p className="text-sm font-semibold text-slate-700 mb-3">Shop Location <span className="font-normal text-slate-400 text-xs">(optional — used for address verification)</span></p>
              <div className="flex flex-wrap items-center gap-3 mb-3">
                <button type="button" onClick={() => setShowMap((s) => !s)} className={`px-5 py-3 min-h-12 rounded-xl text-sm font-medium transition ${showMap ? "bg-slate-100 text-slate-700 hover:bg-slate-200" : "bg-indigo-50 text-indigo-700 hover:bg-indigo-100"}`}>
                  📍 {showMap ? "Hide Map" : "Show Map to Pin Location"}
                </button>
                {pinnedLocation && <span className="text-xs text-emerald-600">✓ Pinned: {formatLat(pinnedLocation.lat)}, {formatLon(pinnedLocation.lon)}</span>}
              </div>
              {showMap && <div className="mb-3"><div id="leaflet-map" className="w-full rounded-lg border border-slate-200" style={{ height: "300px" }} /></div>}
              <label htmlFor="vendor-name" className="block text-sm font-medium text-slate-700">Shop Name / Vendor Name</label>
              <input id="vendor-name" type="text" value={vendorName} onChange={(e) => setVendorName(e.target.value)} placeholder="e.g. Sri Krishna Traders" className="mt-1.5 block w-full min-h-12 rounded-lg border border-slate-200 px-3 py-3 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400" />
              <label htmlFor="shop-address" className="mt-4 block text-sm font-medium text-slate-700">Shop Address / Area</label>
              <input id="shop-address" type="text" value={shopAddress} onChange={(e) => setShopAddress(e.target.value)} placeholder="e.g. 123 MG Road, Bangalore" className="mt-1.5 block w-full min-h-12 rounded-lg border border-slate-200 px-3 py-3 text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400" />
            </div>
          </div>
        )}

        {/* Status footer */}
        <div className="flex flex-wrap items-center justify-center gap-3">
          {stepStatus.map((s, i) => (
            <span key={s.label} className="flex items-center gap-1.5 text-[11px] text-slate-500">
              <span className={`w-2.5 h-2.5 rounded-full ${s.done ? "bg-emerald-500" : s.required ? "bg-red-400" : "bg-amber-400"}`} />
              {i + 1}. {s.label}
            </span>
          ))}
        </div>

        <button
          onClick={handleSubmit}
          disabled={!canSubmit || loading || precomputedVisionLoading || precomputedVoiceLoading}
          className={`w-full py-4 px-6 rounded-xl text-base font-bold uppercase tracking-wider transition ${
            !canSubmit || loading || precomputedVisionLoading || precomputedVoiceLoading
              ? "bg-slate-200 text-slate-400 cursor-not-allowed"
              : "bg-indigo-600 text-white hover:bg-indigo-700"
          }`}
        >
          Generate Report
        </button>

        {/* Phase 3 P3-ST5: Loading state — white card, min-h rows */}
        {loading && (
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4 md:p-6 flex flex-col gap-3">
            <div className="space-y-1">
              {processingSteps.map((step) => {
                const icon = step.status === "done" ? "✅" : step.status === "active" ? "🔄" : "⬜";
                return (
                  <div key={step.id} className="flex items-center gap-3 min-h-[40px] text-sm">
                    <span className={`text-xl w-8 shrink-0 flex items-center justify-center ${step.status === "active" ? "animate-pulse" : ""}`}>{icon}</span>
                    <span className={`${step.status === "done" ? "text-slate-400 line-through" : step.status === "active" ? "text-indigo-700 font-medium" : "text-slate-400"}`}>
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-slate-400 mt-1">Generating... {elapsed}s</p>
            <div className="w-full h-1 rounded-full bg-slate-200 overflow-hidden">
              <div className="h-full bg-indigo-500 rounded-full transition-all duration-700" style={{ width: `${Math.min(100, (elapsed / Math.max(1, elapsed + 2)) * 100)}%` }} />
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
            <p className="font-medium mb-1">Error</p>
            <p className="text-red-600 break-words">{error}</p>
            <button onClick={() => setError(null)} className="mt-3 underline text-red-700 hover:text-red-900">try again</button>
          </div>
        )}
      </div>
    </main>
  );
}
