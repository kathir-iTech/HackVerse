"use client";

import { useCallback, useRef, useState } from "react";

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
  report_id?: string;
  sources_cited?: string[];
  total_inflow?: number;
  total_outflow?: number;
  transaction_count?: number;
  average_transaction?: number;
  volatility?: string;
  trend?: string;
  date_range_days?: number;
  earliest_date?: string;
  latest_date?: string;
}

const AGREEMENT_COLORS: Record<string, string> = {
  agree: "bg-green-100 text-green-700 border-green-300",
  conflict: "bg-amber-100 text-amber-700 border-amber-300",
  insufficient_data: "bg-slate-50 text-slate-400 border-slate-200",
};

const AGREEMENT_LABELS: Record<string, string> = {
  agree: "✓ Agree",
  conflict: "✗ Conflict",
  insufficient_data: "— No Data",
};

const PAIR_LABELS: Record<string, string> = {
  photo_voice: "Photo ⇄ Voice",
  photo_transactions: "Photo ⇄ Transactions",
  voice_transactions: "Voice ⇄ Transactions",
};

function bandColor(b: Band) {
  switch (b) {
    case "Low":
      return "text-red-700 bg-red-50 border-red-200";
    case "Moderate":
      return "text-amber-700 bg-amber-50 border-amber-200";
    case "Strong":
      return "text-emerald-700 bg-emerald-50 border-emerald-200";
    default:
      return "text-slate-600 bg-slate-50 border-slate-200";
  }
}

function BandTag({ label, value }: { label: string; value: Band }) {
  return (
    <div className="flex items-center justify-between py-2.5">
      <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">{label}</span>
      <span className={`px-2.5 py-0.5 text-[11px] font-semibold border rounded ${bandColor(value)}`}>
        {value}
      </span>
    </div>
  );
}

export default function Page() {
  const [screen, setScreen] = useState<"upload" | "report" | "history">("upload");
  const [photos, setPhotos] = useState<File[]>([]);
  const [audio, setAudio] = useState<File | null>(null);
  const [csv, setCsv] = useState<File | null>(null);
  const [precomputedVision, setPrecomputedVision] = useState<any>(null);
  const [precomputedVoice, setPrecomputedVoice] = useState<any>(null);
  const [precomputedVisionLoading, setPrecomputedVisionLoading] = useState(false);
  const [precomputedVoiceLoading, setPrecomputedVoiceLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingPhase, setLoadingPhase] = useState<"finishing" | "generating">("generating");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const audioRef = useRef<HTMLInputElement>(null);
  const csvRef = useRef<HTMLInputElement>(null);
  const precomputedVisionLoadingRef = useRef(false);
  const precomputedVoiceLoadingRef = useRef(false);
  const precomputedVisionRef = useRef<any>(null);
  const precomputedVoiceRef = useRef<any>(null);

  const canSubmit = photos.length > 0 || audio !== null || csv !== null;

  const handlePhotos = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
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
  }, []);

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
    try {
      let res;
      const visionResult = precomputedVisionRef.current;
      const voiceResult = precomputedVoiceRef.current;
      if (visionResult || voiceResult) {
        const fd = new FormData();
        if (visionResult) fd.append("vision_result", JSON.stringify(visionResult));
        if (voiceResult) fd.append("voice_result", JSON.stringify(voiceResult));
        if (csv) fd.append("transactions", csv);
        res = await fetch(API_BASE + "/report/synthesize", { method: "POST", body: fd });
      } else {
        const fd = new FormData();
        for (const f of photos) fd.append("photos", f);
        if (audio) fd.append("audio", audio);
        if (csv) fd.append("transactions", csv);
        res = await fetch(API, { method: "POST", body: fd });
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Report = await res.json();
      setReport(data);
      setScreen("report");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [photos, audio, csv, precomputedVision, precomputedVoice]);

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
    } finally {
      setHistoryLoading(false);
    }
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
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setScreen("upload");
    setPhotos([]);
    setAudio(null);
    setCsv(null);
    setPrecomputedVision(null);
    setPrecomputedVoice(null);
    precomputedVisionRef.current = null;
    precomputedVoiceRef.current = null;
    setReport(null);
    setError(null);
  }, []);

  if (screen === "report" && report) {
    const hasFinancial = report.transaction_count !== undefined;

    return (
      <main className="max-w-2xl mx-auto px-4 py-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Theligai</h1>
            <p className="text-xs text-slate-400">Business Readiness Report for MSME Field Assessment</p>
            {report.report_id && (
              <p className="mt-0.5 text-[11px] font-mono text-slate-400">ID {report.report_id}</p>
            )}
          </div>
          <button onClick={reset} className="text-sm text-slate-500 hover:text-slate-700 underline">
            New Report
          </button>
        </div>

        <div className="space-y-6">
          {/* Business type */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Business Type</span>
            <p className="mt-1 text-lg font-semibold text-slate-900">
              {report.business_type ?? "Not specified"}
            </p>
          </div>

          {/* Band rows */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 divide-y divide-slate-100">
            <BandTag label="Revenue Consistency" value={report.revenue_consistency_band} />
            <BandTag label="Inventory Observation" value={report.inventory_observation_band} />
            <BandTag label="Digital Activity" value={report.digital_activity_band} />
          </div>

          {/* Assessment band */}
          <div className="bg-indigo-50 rounded-xl border border-indigo-200 p-5">
            <span className="text-xs font-medium text-indigo-500 uppercase tracking-wide">Assessment</span>
            <p className="mt-1 text-lg font-semibold text-indigo-900">{report.assessment_band}</p>
          </div>

          {/* Financial Evidence card */}
          {hasFinancial && (
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Financial Evidence</span>
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
            </div>
          )}

          {/* Cross-verification matrix */}
          {report.source_agreement && (
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 px-5 pt-5 pb-3">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Cross-Verification</span>
              <div className="mt-3 flex flex-col items-center select-none">
                {/* Top row: Photo ── connector ── Voice */}
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

                {/* Vertical connectors */}
                <div className="flex justify-between w-full max-w-xs h-6">
                  <div className="flex flex-col items-center w-1/3">
                    <div className={`w-0.5 h-3 ${report.source_agreement.photo_transactions === "agree" ? "bg-green-400" : report.source_agreement.photo_transactions === "conflict" ? "bg-amber-400" : "bg-slate-200"}`} />
                  </div>
                  <div className="flex flex-col items-center w-1/3">
                    <div className={`w-0.5 h-3 ${report.source_agreement.voice_transactions === "agree" ? "bg-green-400" : report.source_agreement.voice_transactions === "conflict" ? "bg-amber-400" : "bg-slate-200"}`} />
                  </div>
                </div>

                {/* Between verticals: status pills */}
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

                {/* Bottom row: Transactions (centered, span both) */}
                <div className="mt-1 flex justify-center w-full max-w-xs">
                  <div className="inline-flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-700">
                    <span className="text-base">💰</span> Transactions
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Discrepancy flags */}
          {report.discrepancy_flags && report.discrepancy_flags.length > 0 && (
            <div className="bg-amber-50 rounded-xl border border-amber-200 p-5">
              <span className="text-xs font-medium text-amber-700 uppercase tracking-wide">Needs Officer Review</span>
              <ul className="mt-2 space-y-1">
                {report.discrepancy_flags.map((s, i) => (
                  <li key={i} className="text-sm text-amber-800 flex gap-2">
                    <span className="text-amber-400 mt-0.5 shrink-0">•</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Scheme note + Sources Referenced */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Scheme Note</span>
            <p className="mt-2 text-sm text-slate-700 leading-relaxed">{report.relevant_scheme_note}</p>
            {report.sources_cited && report.sources_cited.length > 0 && (
              <p className="mt-3 text-[11px] text-slate-400">
                Sources referenced: {report.sources_cited.join(", ")}
              </p>
            )}
          </div>

          {/* Evidence summary */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Evidence Summary</span>
            <ul className="mt-2 space-y-1">
              {(report.evidence_summary ?? []).map((s, i) => (
                <li key={i} className="text-sm text-slate-700 flex gap-2">
                  <span className="text-slate-300 mt-0.5 shrink-0">•</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Missing inputs note */}
          {report.missing_inputs.length > 0 && (
            <div className="bg-amber-50 rounded-xl border border-amber-200 p-4 text-sm text-amber-800">
              Note: no{" "}
              {report.missing_inputs
                .map((m) => m.replace("photos", "shop photos").replace("voice", "voice note"))
                .join(" or ")}{" "}
              were provided for this assessment.
            </div>
          )}

          {/* Footer */}
          <p className="text-[11px] text-slate-300 text-center">
            This report was generated by an AI pipeline. All outputs should be verified by a field officer before decision-making.
          </p>
        </div>
      </main>
    );
  }

  if (screen === "history") {
    return (
      <main className="max-w-2xl mx-auto px-4 py-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Theligai</h1>
            <p className="text-xs text-slate-400">Business Readiness Report for MSME Field Assessment</p>
          </div>
          <button onClick={() => setScreen("upload")} className="text-sm text-slate-500 hover:text-slate-700 underline">
            Back
          </button>
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
                  <span className={`px-2.5 py-0.5 text-[11px] font-semibold border rounded ${bandColor(r.assessment_band as Band)}`}>
                    {r.assessment_band}
                  </span>
                  <button onClick={() => viewReport(r.report_id)} className="text-xs font-medium text-indigo-600 hover:text-indigo-800 underline underline-offset-2">
                    View Full Report
                  </button>
                </div>
              </div>
            ))
          )}
          {error && screen === "history" && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{error}</div>
          )}
        </div>

        <p className="mt-8 text-[11px] text-slate-300 text-center">
          Demo mode — showing all assessments. Production version would restrict this to the logged-in officer&apos;s own history.
        </p>
      </main>
    );
  }

  return (
    <main className="max-w-xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-900">Theligai</h1>
      <p className="text-xs text-slate-400">Business Readiness Report for MSME Field Assessment</p>
      <p className="mt-3 text-sm text-slate-500">
        For field officers — upload evidence collected during a vendor visit
      </p>
      <p className="mt-1 text-xs text-slate-400">
        Upload at least one item below to generate a report — all three are optional individually.
      </p>

      <div className="mt-8 space-y-6">
        {/* Photos */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
          <div className="flex items-baseline gap-2">
            <h2 className="text-sm font-semibold text-slate-800">Shop Photos</h2>
            <span className="text-xs text-slate-400">optional</span>
          </div>
          <input
            type="file"
            accept="image/*"
            multiple
            onChange={handlePhotos}
            className="mt-3 block w-full text-sm text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer"
          />
          {precomputedVisionLoading && (
            <p className="text-xs text-indigo-500 mt-2 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
              Processing photos...
            </p>
          )}
          {!precomputedVisionLoading && precomputedVision && photos.length > 0 && (
            <p className="text-xs text-emerald-600 mt-2 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-emerald-500 rounded-full" />
              Ready
            </p>
          )}
          {photos.length > 0 && (
            <div className="mt-3 flex gap-2 flex-wrap">
              {photos.map((f, i) => (
                <div key={i} className="relative group">
                  <img
                    src={URL.createObjectURL(f)}
                    alt=""
                    className="w-16 h-16 object-cover rounded-lg border border-slate-200"
                  />
                  <button
                    type="button"
                    onClick={() => {
                        const newPhotos = photos.filter((_, j) => j !== i);
                        setPhotos(newPhotos);
                        if (newPhotos.length === 0) setPrecomputedVision(null);
                    }}
                    className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Audio */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
          <div className="flex items-baseline gap-2">
            <h2 className="text-sm font-semibold text-slate-800">Voice Note</h2>
            <span className="text-xs text-slate-400">optional</span>
          </div>
          <input
            ref={audioRef}
            type="file"
            accept="audio/*"
            onChange={(e) => handleAudio(e.target.files?.[0] ?? null)}
            className="mt-3 block w-full text-sm text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer"
          />
          {precomputedVoiceLoading && (
            <p className="text-xs text-indigo-500 mt-2 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
              Processing voice note...
            </p>
          )}
          {!precomputedVoiceLoading && precomputedVoice && audio && (
            <p className="text-xs text-emerald-600 mt-2 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-emerald-500 rounded-full" />
              Ready
            </p>
          )}
          {audio && (
            <div className="mt-2 flex items-center gap-2 text-sm text-slate-600">
              <span>✓ {audio.name}</span>
              <button
                type="button"
                onClick={() => { handleAudio(null); if (audioRef.current) audioRef.current.value = ""; }}
                className="text-red-500 hover:text-red-700 text-xs"
              >
                remove
              </button>
            </div>
          )}
        </div>

        {/* CSV */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
          <div className="flex items-baseline gap-2">
            <h2 className="text-sm font-semibold text-slate-800">Transaction Export (CSV)</h2>
            <span className="text-xs text-slate-400">optional</span>
          </div>
          <input
            ref={csvRef}
            type="file"
            accept=".csv"
            onChange={(e) => setCsv(e.target.files?.[0] ?? null)}
            className="mt-3 block w-full text-sm text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer"
          />
          {csv && (
            <p className="text-xs text-emerald-600 mt-2 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-emerald-500 rounded-full" />
              Ready
            </p>
          )}
          {csv && (
            <div className="mt-2 flex items-center gap-2 text-sm text-slate-600">
              <span>✓ {csv.name}</span>
              <button
                type="button"
                onClick={() => { setCsv(null); if (csvRef.current) csvRef.current.value = ""; }}
                className="text-red-500 hover:text-red-700 text-xs"
              >
                remove
              </button>
            </div>
          )}
        </div>

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!canSubmit || loading}
          className={`w-full py-3 px-6 rounded-xl text-sm font-semibold transition ${
            !canSubmit || loading
              ? "bg-slate-200 text-slate-400 cursor-not-allowed"
              : "bg-indigo-600 text-white hover:bg-indigo-700"
          }`}
        >
          {loading ? loadingPhase === "finishing" ? "Finishing analysis..." : "Generating report..." : "Generate Report"}
        </button>

        {loading && (
          <div className="flex items-center justify-center gap-2 text-sm text-slate-500">
            <span className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <span>{loadingPhase === "finishing" ? "Finishing analysis…" : "Generating report…"}</span>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
            <p className="font-medium mb-1">Error</p>
            <p className="text-red-600 break-words">{error}</p>
            <button onClick={() => setError(null)} className="mt-3 underline text-red-700 hover:text-red-900">
              try again
            </button>
          </div>
        )}

        <button onClick={fetchReports} className="w-full text-center text-sm text-slate-400 hover:text-slate-600 underline underline-offset-2">
          View Past Assessments
        </button>
      </div>
    </main>
  );
}
