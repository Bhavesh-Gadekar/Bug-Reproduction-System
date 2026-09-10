"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Clock,
  Layers,
  FileCheck,
  RefreshCw,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  Database,
  ExternalLink,
} from "lucide-react";
import {
  GlassPanel,
  GlassCard,
  GlassButton,
  GlassBadge,
  type GlassBadgeVariant,
} from "@/components/ui/glass";

interface BugReportSummary {
  id: string;
  title: string;
  description?: string | null;
}

interface RunListItem {
  id: string;
  bug_report_id: string;
  status: string;
  raw_status: string;
  is_stale: boolean;
  stale_reason?: string | null;
  candidate_produced: boolean;
  plausible_reproduced: boolean;
  persist_error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  model_version?: string | null;
  step_count: number;
  artifact_count: number;
  bug_report?: BugReportSummary | null;
}

interface RunsResponse {
  total: number;
  page: number;
  page_size: number;
  items: RunListItem[];
}

const RAW_STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: "analyzing", label: "Analyzing" },
  { value: "queued", label: "Queued" },
  { value: "running", label: "Running" },
  { value: "succeeded", label: "Succeeded" },
  { value: "failed", label: "Failed" },
  { value: "error", label: "Error" },
  { value: "infra_error", label: "Infra Error" },
  { value: "timed_out", label: "Timed Out" },
];

export default function RunsListPage() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const pageSize = 12;

  const [rawStatusFilter, setRawStatusFilter] = useState<string>("");
  const [stalenessFilter, setStalenessFilter] = useState<"all" | "stale" | "active">("all");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });

      if (rawStatusFilter) {
        params.set("raw_status", rawStatusFilter);
      }

      if (stalenessFilter === "stale") {
        params.set("is_stale", "true");
      } else if (stalenessFilter === "active") {
        params.set("is_stale", "false");
      }

      const res = await fetch(`${apiUrl}/api/runs?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`API returned HTTP ${res.status}`);
      }
      const data: RunsResponse = await res.json();
      setRuns(data.items);
      setTotal(data.total);
    } catch (err: any) {
      console.error("Failed to load runs:", err);
      setError(err?.message || "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, page, pageSize, rawStatusFilter, stalenessFilter]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Format relative or date string
  const formatTime = (iso?: string | null) => {
    if (!iso) return "—";
    try {
      const date = new Date(iso);
      return date.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
    } catch {
      return iso;
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <GlassBadge variant="neutral" className="px-3 py-1 text-[11px]">
              GET /api/runs
            </GlassBadge>
            <span className="text-xs text-white/40 font-mono">
              Total {total} tracked runs
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Reproduction Jobs
          </h1>
          <p className="text-white/50 text-xs sm:text-sm mt-1">
            Browse automated reproduction runs, monitor in-flight tasks, and inspect terminal outcomes.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <GlassButton
            onClick={() => fetchRuns()}
            disabled={loading}
            size="sm"
            variant="default"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-white/50" : "text-white/80"}`} />
            Refresh
          </GlassButton>
          <Link href="/submit">
            <GlassButton size="sm" variant="primary">
              + New Run
            </GlassButton>
          </Link>
        </div>
      </div>

      {/* Filter Surface (Liquid Glass Panel) */}
      <GlassPanel className="p-4 sm:p-5 mb-6">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
          {/* Raw Status Select */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-white/50 flex items-center gap-1.5 mr-1">
              <Filter className="w-3.5 h-3.5" />
              Raw Status:
            </span>
            <div className="flex flex-wrap gap-1.5">
              {RAW_STATUS_OPTIONS.map((opt) => {
                const isActive = rawStatusFilter === opt.value;
                return (
                  <button
                    key={opt.value}
                    onClick={() => {
                      setRawStatusFilter(opt.value);
                      setPage(1);
                    }}
                    className={`px-3 py-1 rounded-xl text-xs font-medium transition-all ${
                      isActive
                        ? "liquid-glass bg-white/15 text-white font-semibold border-white/30"
                        : "liquid-glass-subtle text-white/60 hover:text-white hover:bg-white/8"
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Staleness Toggle (Independent) */}
          <div className="flex items-center gap-2 border-t sm:border-t-0 pt-3 sm:pt-0 border-white/10 shrink-0">
            <span className="text-xs font-medium text-white/50">Staleness:</span>
            <div className="inline-flex rounded-xl p-0.5 liquid-glass-subtle">
              <button
                onClick={() => {
                  setStalenessFilter("all");
                  setPage(1);
                }}
                className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
                  stalenessFilter === "all"
                    ? "bg-white/15 text-white font-semibold"
                    : "text-white/50 hover:text-white"
                }`}
              >
                All
              </button>
              <button
                onClick={() => {
                  setStalenessFilter("stale");
                  setPage(1);
                }}
                className={`px-2.5 py-1 text-xs rounded-lg font-medium flex items-center gap-1.5 transition-colors ${
                  stalenessFilter === "stale"
                    ? "bg-amber-500/20 text-amber-300 font-semibold border border-amber-500/30"
                    : "text-white/50 hover:text-amber-300"
                }`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                Stale Only
              </button>
              <button
                onClick={() => {
                  setStalenessFilter("active");
                  setPage(1);
                }}
                className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
                  stalenessFilter === "active"
                    ? "bg-white/15 text-white font-semibold"
                    : "text-white/50 hover:text-white"
                }`}
              >
                Active Only
              </button>
            </div>
          </div>
        </div>
      </GlassPanel>

      {/* Runs List Table / Rows */}
      {loading && runs.length === 0 ? (
        <GlassPanel className="p-12 text-center text-white/50">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-3 text-white/40" />
          <p className="text-sm">Loading reproduction jobs from backend...</p>
        </GlassPanel>
      ) : error ? (
        <GlassPanel className="p-8 text-center text-white/70 border-rose-500/30">
          <p className="text-rose-400 text-sm font-semibold mb-2">Error loading runs</p>
          <p className="text-xs text-white/50 mb-4">{error}</p>
          <GlassButton
            onClick={() => fetchRuns()}
            size="sm"
            variant="default"
          >
            Retry
          </GlassButton>
        </GlassPanel>
      ) : runs.length === 0 ? (
        <GlassPanel className="p-12 text-center text-white/50">
          <Database className="w-8 h-8 mx-auto mb-3 text-white/30" />
          <p className="text-sm font-medium text-white/70">No reproduction runs found</p>
          <p className="text-xs text-white/40 mt-1">Try changing your status or staleness filters.</p>
        </GlassPanel>
      ) : (
        <div className="space-y-2.5">
          {runs.map((run) => {
            const isInfraError = run.raw_status === "infra_error";
            const isError = run.raw_status === "error" || Boolean(run.persist_error);
            const isSucceeded = run.raw_status === "succeeded";
            const isFailed = run.raw_status === "failed";
            const isAnalyzing = run.raw_status === "analyzing" || run.raw_status === "running";

            // Determine badge variant preserving functional colors
            let badgeVariant: GlassBadgeVariant = "neutral";
            if (isInfraError) {
              badgeVariant = "infra_error";
            } else if (isSucceeded && run.plausible_reproduced) {
              badgeVariant = "succeeded";
            } else if (isSucceeded && !run.plausible_reproduced) {
              badgeVariant = "stale";
            } else if (isFailed) {
              badgeVariant = "failed";
            } else if (isError) {
              badgeVariant = "error";
            } else if (isAnalyzing) {
              badgeVariant = "running";
            }

            return (
              <Link
                key={run.id}
                href={`/runs/${run.id}`}
                className="block group"
              >
                <GlassPanel
                  variant="row"
                  className="p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 group-hover:border-white/25 transition-all"
                >
                  {/* Left: Status Badges and Title */}
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1.5">
                      {/* Raw Status Badge using GlassBadge */}
                      <GlassBadge variant={badgeVariant} dot>
                        {run.raw_status}
                      </GlassBadge>

                      {/* Independent Is Stale Badge */}
                      {run.is_stale && (
                        <GlassBadge variant="stale" dot>
                          STALE
                        </GlassBadge>
                      )}

                      {/* Verdict Outcome Pill */}
                      {isSucceeded && (
                        <span className="text-[11px] font-mono text-white/60">
                          {run.plausible_reproduced
                            ? "reproduced = true"
                            : "candidate produced (not verified)"}
                        </span>
                      )}

                      {/* Short Run ID */}
                      <span className="text-[11px] font-mono text-white/40">
                        #{run.id.slice(0, 8)}
                      </span>
                    </div>

                    {/* Bug Title */}
                    <h3 className="text-sm sm:text-base font-semibold text-white/95 group-hover:text-white truncate">
                      {run.bug_report?.title || "Reproduction Run"}
                    </h3>

                    {/* Surface Stale Reason or Persist Error */}
                    {run.is_stale && run.stale_reason && (
                      <p className="text-xs text-amber-300/80 font-mono mt-1 truncate">
                        ⚠ {run.stale_reason}
                      </p>
                    )}
                    {isError && run.persist_error && (
                      <p className="text-xs text-rose-300/85 font-mono mt-1 truncate">
                        ✕ {run.persist_error}
                      </p>
                    )}
                  </div>

                  {/* Right: Metrics and Timestamp */}
                  <div className="flex items-center gap-4 sm:gap-6 shrink-0 text-xs text-white/60 font-mono">
                    <div className="flex items-center gap-1.5" title="Run Steps">
                      <Layers className="w-3.5 h-3.5 text-white/40" />
                      <span>{run.step_count} steps</span>
                    </div>

                    <div className="flex items-center gap-1.5" title="Generated Artifacts">
                      <FileCheck className="w-3.5 h-3.5 text-white/40" />
                      <span>{run.artifact_count} artifacts</span>
                    </div>

                    <div className="flex items-center gap-1.5 text-white/40" title="Started At">
                      <Clock className="w-3.5 h-3.5" />
                      <span>{formatTime(run.started_at)}</span>
                    </div>

                    <div className="liquid-glass-badge p-1.5 text-white/40 group-hover:text-white group-hover:border-white/30 transition-colors">
                      <ArrowRight className="w-3.5 h-3.5" />
                    </div>
                  </div>
                </GlassPanel>
              </Link>
            );
          })}
        </div>
      )}

      {/* Pagination Footer */}
      <GlassPanel className="p-4 mt-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-white/60">
        <div>
          Showing {runs.length > 0 ? (page - 1) * pageSize + 1 : 0} to{" "}
          {Math.min(page * pageSize, total)} of {total} runs
        </div>

        <div className="flex items-center gap-2">
          <GlassButton
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1 || loading}
            size="sm"
            variant="default"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            Previous
          </GlassButton>

          <span className="font-mono text-white/80 px-2">
            Page {page} of {totalPages}
          </span>

          <GlassButton
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages || loading}
            size="sm"
            variant="default"
          >
            Next
            <ChevronRight className="w-3.5 h-3.5" />
          </GlassButton>
        </div>
      </GlassPanel>
    </div>
  );
}

