"use client";

import { useCallback, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001/report";

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
}

function bandColor(b: Band) {
  switch (b) {
    case "Low":
      return "bg-red-100 text-red-800";
    case "Moderate":
      return "bg-yellow-100 text-yellow-800";
    case "Strong":
      return "bg-green-100 text-green-800";
    default:
      return "bg-slate-100 text-slate-800";
  }
}

function BandPill({ label, value }: { label: string; value: Band }) {
  return (
    <div className="flex items-center justify-between py-3">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <span className={`px-3 py-1 rounded-full text-xs font-semibold ${bandColor(value)}`}>
        {value}
      </span>
    </div>
  );
}

export default function Page() {
  const [screen, setScreen] = useState<"upload" | "report">("upload");
  const [photos, setPhotos] = useState<File[]>([]);
  const [audio, setAudio] = useState<File | null>(null);
  const [csv, setCsv] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  const audioRef = useRef<HTMLInputElement>(null);
  const csvRef = useRef<HTMLInputElement>(null);

  const canSubmit = photos.length > 0 || audio !== null || csv !== null;

  const handlePhotos = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setPhotos(Array.from(e.target.files ?? []));
  }, []);

  const handleSubmit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const fd = new FormData();
      for (const f of photos) fd.append("photos", f);
      if (audio) fd.append("audio", audio);
      if (csv) fd.append("transactions", csv);
      const res = await fetch(API, { method: "POST", body: fd });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data: Report = await res.json();
      setReport(data);
      setScreen("report");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [photos, audio, csv]);

  const reset = useCallback(() => {
    setScreen("upload");
    setPhotos([]);
    setAudio(null);
    setCsv(null);
    setReport(null);
    setError(null);
  }, []);

  if (screen === "report" && report) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-10">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-slate-900">Business Readiness Report</h1>
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
            <BandPill label="Revenue Consistency" value={report.revenue_consistency_band} />
            <BandPill label="Inventory Observation" value={report.inventory_observation_band} />
            <BandPill label="Digital Activity" value={report.digital_activity_band} />
          </div>

          {/* Assessment band */}
          <div className="bg-indigo-50 rounded-xl border border-indigo-200 p-5">
            <span className="text-xs font-medium text-indigo-500 uppercase tracking-wide">Assessment</span>
            <p className="mt-1 text-lg font-semibold text-indigo-900">{report.assessment_band}</p>
          </div>

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

          {/* Scheme note */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Scheme Note</span>
            <p className="mt-2 text-sm text-slate-700 leading-relaxed">{report.relevant_scheme_note}</p>
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
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-900">Business Readiness Report</h1>
      <p className="mt-1 text-sm text-slate-500">
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
                    onClick={() => setPhotos((prev) => prev.filter((_, j) => j !== i))}
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
            onChange={(e) => setAudio(e.target.files?.[0] ?? null)}
            className="mt-3 block w-full text-sm text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer"
          />
          {audio && (
            <div className="mt-2 flex items-center gap-2 text-sm text-slate-600">
              <span>✓ {audio.name}</span>
              <button
                type="button"
                onClick={() => { setAudio(null); if (audioRef.current) audioRef.current.value = ""; }}
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
          {loading ? "Analyzing evidence..." : "Generate Report"}
        </button>

        {loading && (
          <div className="flex items-center justify-center gap-2 text-sm text-slate-500">
            <span className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <span>Analyzing evidence…</span>
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
      </div>
    </main>
  );
}
