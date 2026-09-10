"use client";

import React, { useEffect, useState, useRef, use, useCallback } from "react";

import Link from "next/link";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  Clock,
  Code,
  Copy,
  Cpu,
  Download,
  ExternalLink,
  FileCode,
  FileText,
  Layers,
  RefreshCw,
  Terminal as TerminalIcon,
  Wifi,
  WifiOff,
  XCircle,
  Zap,
} from "lucide-react";
import {
  GlassPanel,
  GlassCard,
  GlassButton,
  GlassBadge,
  type GlassBadgeVariant,
} from "@/components/ui/glass";


interface RunStep {
  id: string;
  run_id: string;
  node_name: string;
  input: Record<string, any>;
  output: Record<string, any>;
  tokens_used: number;
  latency_ms: number;
  created_at: string;
}

interface ArtifactItem {
  id: string;
  run_id: string;
  type: string;
  storage_path: string;
  status: string;
  error?: string | null;
  download_url?: string | null;
  created_at?: string | null;
}

interface BugReportInfo {
  id: string;
  title: string;
  description?: string | null;
  raw_stack_trace?: string | null;
}

interface RunDetailsData {
  id: string;
  bug_report_id: string;
  status: string;
  raw_status?: string;
  is_stale: boolean;
  stale_reason?: string | null;
  model_version?: string | null;
  prompt_version?: string | null;
  candidate_produced: boolean;
  plausible_reproduced: boolean;
  started_at?: string | null;
  completed_at?: string | null;
  persist_error?: string | null;
  sandbox_container_id?: string | null;
  steps: RunStep[];
  artifacts: ArtifactItem[];
  bug_report?: BugReportInfo | null;
}

export default function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const runId = resolvedParams.id;

  const [runData, setRunData] = useState<RunDetailsData | null>(null);
  const [steps, setSteps] = useState<RunStep[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [status, setStatus] = useState<string>("queued");
  const [rawStatus, setRawStatus] = useState<string>("queued");
  const [isStale, setIsStale] = useState<boolean>(false);
  const [staleReason, setStaleReason] = useState<string | null>(null);
  const [persistError, setPersistError] = useState<string | null>(null);
  const [candidateProduced, setCandidateProduced] = useState<boolean>(false);
  const [plausibleReproduced, setPlausibleReproduced] = useState<boolean>(false);

  // SSE Stream State: "connecting" | "live" | "done" | "disconnected"
  const [streamState, setStreamState] = useState<"connecting" | "live" | "done" | "disconnected">("connecting");
  const [disconnectError, setDisconnectError] = useState<string | null>(null);

  // Active Tab: sandbox terminal, script, artifacts panel, stack trace
  const [activeTab, setActiveTab] = useState<"terminal" | "script" | "artifacts" | "stacktrace">("terminal");
  const [copiedScript, setCopiedScript] = useState<boolean>(false);
  const [copiedId, setCopiedId] = useState<boolean>(false);
  const [selectedNodeFilter, setSelectedNodeFilter] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const streamEndedRef = useRef<boolean>(false);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Fetch full run details & B2 artifacts
  const fetchRunDetailsAndArtifacts = useCallback(async () => {
    try {
      // 1. Fetch details
      const res = await fetch(`${apiUrl}/api/runs/${runId}`);
      if (res.ok) {
        const data: RunDetailsData = await res.json();
        setRunData(data);
        setStatus(data.status);
        setRawStatus(data.raw_status || data.status);
        setIsStale(Boolean(data.is_stale));
        setStaleReason(data.stale_reason || null);
        setPersistError(data.persist_error || null);
        setCandidateProduced(Boolean(data.candidate_produced));
        setPlausibleReproduced(Boolean(data.plausible_reproduced));

        if (data.steps && data.steps.length > 0) {
          setSteps(data.steps);
        }

        const terminalStatuses = ["succeeded", "failed", "timed_out", "completed", "error"];
        if (terminalStatuses.includes((data.raw_status || data.status).toLowerCase())) {
          setStreamState("done");
          streamEndedRef.current = true;
        }
      }

      // 2. Fetch presigned B2 artifacts
      const artRes = await fetch(`${apiUrl}/api/runs/${runId}/artifacts`);
      if (artRes.ok) {
        const artData = await artRes.json();
        if (Array.isArray(artData.artifacts)) {
          setArtifacts(artData.artifacts);
        }
      }
    } catch (err: any) {
      console.warn("Could not fetch run details:", err);
    }
  }, [apiUrl, runId]);

  // Connect / Reconnect to real SSE endpoint: GET /api/runs/{id}/stream
  const connectSSE = useCallback(() => {
    if (streamEndedRef.current) return;

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setStreamState("connecting");
    setDisconnectError(null);

    const sseUrl = `${apiUrl}/api/runs/${runId}/stream`;
    const es = new EventSource(sseUrl);
    eventSourceRef.current = es;

    es.onopen = () => {
      setStreamState("live");
      setDisconnectError(null);
    };

    es.addEventListener("status", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.status) setStatus(data.status);
        if (data.raw_status) setRawStatus(data.raw_status);
        if (data.is_stale !== undefined) setIsStale(Boolean(data.is_stale));
        if (data.stale_reason !== undefined) setStaleReason(data.stale_reason);
        if (data.persist_error !== undefined) setPersistError(data.persist_error);
        if (data.candidate_produced !== undefined) setCandidateProduced(Boolean(data.candidate_produced));
        if (data.plausible_reproduced !== undefined) setPlausibleReproduced(Boolean(data.plausible_reproduced));
      } catch (e) {
        console.error("Error parsing status event:", e);
      }
    });

    es.addEventListener("step", (event: MessageEvent) => {
      try {
        const newStep: RunStep = JSON.parse(event.data);
        setSteps((prev) => {
          if (prev.some((s) => s.id === newStep.id)) return prev;
          return [...prev, newStep];
        });
      } catch (e) {
        console.error("Error parsing step event:", e);
      }
    });

    es.addEventListener("artifact", (event: MessageEvent) => {
      try {
        const newArt: ArtifactItem = JSON.parse(event.data);
        setArtifacts((prev) => {
          if (prev.some((a) => a.id === newArt.id)) return prev;
          return [...prev, newArt];
        });
      } catch (e) {
        console.error("Error parsing artifact event:", e);
      }
    });

    es.addEventListener("done", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.status) {
          setStatus(data.status);
          setRawStatus(data.status);
        }
        if (data.candidate_produced !== undefined) setCandidateProduced(Boolean(data.candidate_produced));
        if (data.plausible_reproduced !== undefined) setPlausibleReproduced(Boolean(data.plausible_reproduced));
        if (data.persist_error !== undefined) setPersistError(data.persist_error);

        setStreamState("done");
        streamEndedRef.current = true;
        es.close();
        // Refresh artifacts to get presigned B2 URLs
        fetchRunDetailsAndArtifacts();
      } catch (e) {
        console.error("Error parsing done event:", e);
      }
    });

    es.addEventListener("error", () => {
      const terminalStatuses = ["succeeded", "failed", "timed_out", "completed", "error"];
      if (terminalStatuses.includes(rawStatus.toLowerCase()) || terminalStatuses.includes(status.toLowerCase())) {
        setStreamState("done");
        streamEndedRef.current = true;
        es.close();
      } else {
        // EXPLICIT DISCONNECTED STATE:
        // Must NOT be visually indistinguishable from a healthy idle stream
        setStreamState("disconnected");
        setDisconnectError("SSE connection dropped or backend server unreachable.");
        es.close();
      }
    });
  }, [apiUrl, runId, rawStatus, status, fetchRunDetailsAndArtifacts]);

  useEffect(() => {
    fetchRunDetailsAndArtifacts();
    connectSSE();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [fetchRunDetailsAndArtifacts, connectSSE]);

  // Extract latest script from minimization or script_gen steps
  const scriptStep = [...steps].reverse().find((s) => s.node_name === "minimization" || s.node_name === "script_gen");
  const currentScript =
    scriptStep?.output?.minimized_script ||
    scriptStep?.output?.script ||
    steps.find((s) => s.output?.script)?.output?.script ||
    "";

  // Sandbox steps
  const sandboxSteps = steps.filter((s) => s.node_name === "sandbox_exec");
  const latestSandbox = sandboxSteps[sandboxSteps.length - 1];

  const totalTokens = steps.reduce((acc, s) => acc + (s.tokens_used || 0), 0);
  const totalLatency = steps.reduce((acc, s) => acc + (s.latency_ms || 0), 0);

  const handleCopyScript = () => {
    if (!currentScript) return;
    navigator.clipboard.writeText(currentScript);
    setCopiedScript(true);
    setTimeout(() => setCopiedScript(false), 2000);
  };

  const handleCopyId = () => {
    navigator.clipboard.writeText(runId);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  const filteredSteps = selectedNodeFilter
    ? steps.filter((s) => s.node_name === selectedNodeFilter)
    : steps;

  // VERDICT LOGIC: reflects the actual 5-state space
  // 1. running/analyzing (in progress)
  // 2. succeeded, plausible_reproduced = true
  // 3. succeeded, plausible_reproduced = false (candidate_produced but not confirmed)
  // 4. error terminal status (surface persist_error or relevant error field)
  // 5. stale (via is_stale/stale_reason, shown regardless of underlying raw_status)
  const isTerminal = ["succeeded", "failed", "timed_out", "completed", "error", "infra_error"].includes(rawStatus.toLowerCase());
  const isInfraError = rawStatus.toLowerCase() === "infra_error";
  const isErrorTerminal = rawStatus.toLowerCase() === "error" || Boolean(persistError);

  let verdictState: {
    title: string;
    badgeText: string;
    dotClass: string;
    borderClass: string;
    description: string;
  };

  if (isStale) {
    verdictState = {
      title: "Run Flagged as Stale",
      badgeText: "STALE",
      dotClass: "bg-amber-400 animate-ping",
      borderClass: "border-amber-500/30",
      description: staleReason || "No activity recorded while in non-terminal state. Worker or dependency may have stalled.",
    };
  } else if (isInfraError) {
    verdictState = {
      title: "Infrastructure Error Encountered",
      badgeText: "INFRA ERROR",
      dotClass: "bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.7)]",
      borderClass: "border-purple-500/30",
      description: persistError || "Docker daemon, container runtime, or runner environment failure occurred. Not counted as a bug non-reproduction.",
    };
  } else if (isErrorTerminal) {
    verdictState = {
      title: "Terminal Error Encountered",
      badgeText: "ERROR",
      dotClass: "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.7)]",
      borderClass: "border-rose-500/30",
      description: persistError || "The reproduction execution encountered a fatal error during graph traversal or database persistence.",
    };
  } else if (rawStatus.toLowerCase() === "succeeded" && plausibleReproduced) {
    verdictState = {
      title: "Plausible Bug Reproduction Succeeded",
      badgeText: "CONFIRMED REPRODUCED",
      dotClass: "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]",
      borderClass: "border-emerald-500/30",
      description: "Standalone reproduction script successfully reproduced target error in isolated sandbox with matched stack trace.",
    };
  } else if (rawStatus.toLowerCase() === "succeeded" && !plausibleReproduced) {
    verdictState = {
      title: "Candidate Script Generated (Unconfirmed)",
      badgeText: "UNCONFIRMED",
      dotClass: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.7)]",
      borderClass: "border-amber-500/30",
      description: candidateProduced
        ? "Candidate reproduction script was formulated, but sandbox execution did not confirm reproduction match."
        : "Run completed without producing a valid reproduction candidate.",
    };
  } else if (isTerminal && rawStatus.toLowerCase() === "failed") {
    verdictState = {
      title: "Reproduction Failed",
      badgeText: "FAILED",
      dotClass: "bg-rose-400",
      borderClass: "border-rose-500/20",
      description: persistError || "Max hypothesis retries exhausted without reproducing the target stack trace.",
    };
  } else {
    // In progress
    verdictState = {
      title: `Execution In Progress (${rawStatus})`,
      badgeText: "RUNNING / ANALYZING",
      dotClass: "bg-sky-400 animate-pulse shadow-[0_0_8px_rgba(56,189,248,0.7)]",
      borderClass: "border-sky-500/20",
      description: "Autonomous reasoning agent actively analyzing repository, preparing environment, and synthesizing reproduction script.",
    };
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      {/* Top Breadcrumb & Live Stream Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6 pb-4 border-b border-white/10">
        <div className="flex items-center gap-3">
          <Link href="/runs">
            <GlassButton size="sm" variant="default" className="text-white/70 hover:text-white">
              <ArrowLeft className="w-3.5 h-3.5" />
              All Reproduction Jobs
            </GlassButton>
          </Link>
          <div className="liquid-glass-badge px-3 py-1.5 text-xs font-mono text-white/60 flex items-center gap-2">
            <span className="text-white/40">Run:</span>
            <span className="text-white/80">{runId.slice(0, 8)}...{runId.slice(-6)}</span>
            <button onClick={handleCopyId} className="text-white/40 hover:text-white transition-colors ml-1" title="Copy Run ID">
              {copiedId ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Live SSE Stream Indicator & Controls */}
        <div className="flex items-center gap-3">
          {streamState === "live" && (
            <GlassBadge variant="running" dot>
              Live SSE Stream Active
            </GlassBadge>
          )}

          {streamState === "connecting" && (
            <GlassBadge variant="neutral">
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-white/40" />
              Connecting SSE...
            </GlassBadge>
          )}

          {streamState === "done" && (
            <GlassBadge variant="succeeded" dot>
              Stream Completed
            </GlassBadge>
          )}

          {/* EXPLICIT STREAM DISCONNECTED STATE */}
          {streamState === "disconnected" && (
            <div className="liquid-glass-badge px-3.5 py-1.5 text-xs font-semibold text-rose-300 border-rose-500/40 bg-rose-500/10 flex items-center gap-2">
              <WifiOff className="w-3.5 h-3.5 text-rose-400" />
              <span>Stream Disconnected</span>
              <button
                onClick={connectSSE}
                className="ml-1 text-[11px] underline text-white/90 hover:text-white transition-colors"
              >
                Reconnect
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Explicit Stream Disconnected Banner (if dropped mid-stream) */}
      {streamState === "disconnected" && (
        <GlassPanel className="p-4 mb-6 border-rose-500/40 flex items-start justify-between gap-4 bg-rose-500/5">
          <div className="flex items-start gap-3">
            <WifiOff className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
            <div>
              <div className="text-sm font-semibold text-rose-200">
                Live SSE Stream Disconnected
              </div>
              <p className="text-xs text-white/60 mt-0.5">
                {disconnectError || "The Server-Sent Events connection to GET /api/runs/{id}/stream was closed unexpectedly. The run may still be executing in the background."}
              </p>
            </div>
          </div>
          <GlassButton
            onClick={connectSSE}
            size="sm"
            variant="default"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Reconnect Stream
          </GlassButton>
        </GlassPanel>
      )}

      {/* Hero: Verdict Indicator Panel (Reflects 5-state space) */}
      <GlassPanel className={`p-6 sm:p-7 mb-6 ${verdictState.borderClass}`}>
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2.5 mb-2.5">
              {/* Status Badge */}
              <span className="liquid-glass-badge px-3 py-1 text-xs font-mono font-semibold text-white flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${verdictState.dotClass}`} />
                {verdictState.badgeText}
              </span>

              {/* Underlying Raw Status Badge */}
              <GlassBadge variant="neutral" className="px-2.5 py-1 text-xs text-white/60">
                raw_status: {rawStatus}
              </GlassBadge>

              {/* Independent Staleness Badge */}
              {isStale && (
                <GlassBadge variant="stale" dot className="px-2.5 py-1 font-semibold">
                  STALE RUN
                </GlassBadge>
              )}

              {runData?.model_version && (
                <span className="text-xs font-mono text-white/40">
                  model: {runData.model_version}
                </span>
              )}
            </div>

            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight mb-2">
              {runData?.bug_report?.title || "Reproduction Task"}
            </h1>

            <p className="text-sm text-white/70 max-w-3xl leading-relaxed">
              {verdictState.description}
            </p>

            {/* Surfacing Persist Error if present */}
            {persistError && (
              <GlassPanel variant="subtle" className="mt-3 p-3 border-rose-500/30 text-xs font-mono text-rose-300 whitespace-pre-wrap bg-rose-500/5">
                <span className="font-bold text-rose-400">persist_error:</span> {persistError}
              </GlassPanel>
            )}
          </div>

          {/* Quick Metrics */}
          <div className="grid grid-cols-3 gap-2.5 self-stretch md:self-auto min-w-[260px]">
            <GlassPanel variant="subtle" className="p-3 text-center">
              <div className="flex items-center justify-center gap-1 text-white/50 text-[11px] mb-1">
                <Layers className="w-3 h-3 text-white/40" />
                <span>Steps</span>
              </div>
              <span className="text-base font-bold font-mono text-white">{steps.length}</span>
            </GlassPanel>

            <GlassPanel variant="subtle" className="p-3 text-center">
              <div className="flex items-center justify-center gap-1 text-white/50 text-[11px] mb-1">
                <Clock className="w-3 h-3 text-white/40" />
                <span>Latency</span>
              </div>
              <span className="text-base font-bold font-mono text-white">{totalLatency}ms</span>
            </GlassPanel>

            <GlassPanel variant="subtle" className="p-3 text-center">
              <div className="flex items-center justify-center gap-1 text-white/50 text-[11px] mb-1">
                <Zap className="w-3 h-3 text-white/40" />
                <span>Tokens</span>
              </div>
              <span className="text-base font-bold font-mono text-white">{totalTokens}</span>
            </GlassPanel>
          </div>
        </div>
      </GlassPanel>

      {/* Main Grid: Left Column Steps / Right Column Tab Panels */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Live Step Stream Container (5 cols) */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-white/70 flex items-center gap-2">
              <Layers className="w-4 h-4 text-white/40" />
              Run Steps Stream ({filteredSteps.length})
            </h3>
            {selectedNodeFilter && (
              <button
                onClick={() => setSelectedNodeFilter(null)}
                className="text-xs text-white/50 hover:text-white underline"
              >
                Clear filter
              </button>
            )}
          </div>

          {filteredSteps.length === 0 ? (
            <GlassPanel className="p-8 text-center text-white/40">
              <Activity className="w-6 h-6 mx-auto mb-2 text-white/30 animate-spin" />
              <p className="text-xs font-medium">Waiting for run steps from SSE stream...</p>
            </GlassPanel>
          ) : (
            <div className="space-y-2.5 max-h-[720px] overflow-y-auto pr-1">
              {filteredSteps.map((step, idx) => {
                const isDeadLetter = step.node_name === "dead_letter_reconciled";
                const isVerdict = step.node_name === "verdict";
                const isSandbox = step.node_name === "sandbox_exec";

                return (
                  <GlassPanel
                    key={step.id || idx}
                    variant="subtle"
                    className={`p-3.5 transition-all ${
                      isDeadLetter
                        ? "border-amber-500/40 bg-amber-500/5"
                        : isVerdict && step.output?.verdict === "matched"
                        ? "border-emerald-500/30"
                        : ""
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        {/* DISTINCT RENDERING FOR DEAD_LETTER_RECONCILED */}
                        {isDeadLetter ? (
                          <GlassBadge variant="stale" dot className="font-bold uppercase text-[11px]">
                            dead_letter_reconciled
                          </GlassBadge>
                        ) : (
                          <GlassBadge variant="neutral" className="text-[11px] text-white/80">
                            {step.node_name}
                          </GlassBadge>
                        )}

                        {isVerdict && (
                          <span className="text-[10px] font-mono text-white/50">
                            {step.output?.verdict || "evaluated"}
                          </span>
                        )}
                      </div>

                      <div className="text-[10px] font-mono text-white/40">
                        {step.latency_ms}ms
                      </div>
                    </div>

                    {/* Distinct content for dead_letter_reconciled */}
                    {isDeadLetter && (
                      <div className="mt-2 p-2.5 rounded-xl bg-amber-950/20 border border-amber-500/20 text-xs font-mono space-y-1">
                        <div className="text-amber-300 font-semibold flex items-center gap-1">
                          <span>⟳ Recovered from Dead Letter Queue</span>
                        </div>
                        {step.input?.dead_letter_file && (
                          <div className="text-white/60 text-[11px] truncate">
                            File: {step.input.dead_letter_file}
                          </div>
                        )}
                        {step.output?.persist_error && (
                          <div className="text-rose-300 text-[11px] truncate">
                            Recovered Error: {step.output.persist_error}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Hypothesis Step Output */}
                    {step.node_name === "hypothesis_gen" && step.output?.hypothesis && (
                      <div className="mt-2 text-xs text-white/70 liquid-glass-subtle p-2 leading-relaxed">
                        <span className="font-semibold text-white/90">Hypothesis:</span> {step.output.hypothesis}
                      </div>
                    )}

                    {/* Sandbox Output Preview */}
                    {isSandbox && (
                      <div className="mt-2 text-xs font-mono liquid-glass-subtle p-2 text-white/70">
                        <div className="flex items-center justify-between text-white/40 mb-1">
                          <span>Exit: {step.output?.exit_code}</span>
                          <span>{step.output?.duration_seconds?.toFixed(1)}s</span>
                        </div>
                        {step.output?.stdout && (
                          <div className="text-emerald-400/90 truncate">
                            {step.output.stdout.slice(0, 100)}...
                          </div>
                        )}
                      </div>
                    )}

                    {/* Collapsible raw details */}
                    <details className="mt-2 text-[10px] text-white/40 cursor-pointer">
                      <summary className="hover:text-white/70 transition-colors">Raw Node Payload</summary>
                      <pre className="mono mt-1.5 p-2 rounded-lg bg-black/60 border border-white/5 text-[10px] text-white/60 overflow-x-auto">
                        {JSON.stringify({ input: step.input, output: step.output }, null, 2)}
                      </pre>
                    </details>
                  </GlassPanel>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: Console / Script / Artifacts Panel (7 cols) */}
        <div className="lg:col-span-7">
          <GlassPanel className="p-5 sm:p-6 flex flex-col h-full min-h-[580px]">
            {/* Tab Navigation */}
            <div className="flex items-center justify-between pb-4 border-b border-white/10 mb-4">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setActiveTab("terminal")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                    activeTab === "terminal"
                      ? "liquid-glass bg-white/15 text-white"
                      : "liquid-glass-subtle text-white/50 hover:text-white"
                  }`}
                >
                  <TerminalIcon className="w-3.5 h-3.5" />
                  Sandbox Terminal
                </button>

                <button
                  onClick={() => setActiveTab("script")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                    activeTab === "script"
                      ? "liquid-glass bg-white/15 text-white"
                      : "liquid-glass-subtle text-white/50 hover:text-white"
                  }`}
                >
                  <FileCode className="w-3.5 h-3.5" />
                  Repro Script
                  {currentScript && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />}
                </button>

                {/* PIECE 3: ARTIFACTS PANEL TAB */}
                <button
                  onClick={() => setActiveTab("artifacts")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                    activeTab === "artifacts"
                      ? "liquid-glass bg-white/15 text-white"
                      : "liquid-glass-subtle text-white/50 hover:text-white"
                  }`}
                >
                  <Download className="w-3.5 h-3.5" />
                  Artifacts ({artifacts.length})
                  {artifacts.some((a) => a.status === "upload_failed" || a.error) && (
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                  )}
                </button>

                <button
                  onClick={() => setActiveTab("stacktrace")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                    activeTab === "stacktrace"
                      ? "liquid-glass bg-white/15 text-white"
                      : "liquid-glass-subtle text-white/50 hover:text-white"
                  }`}
                >
                  <Code className="w-3.5 h-3.5" />
                  Stack Trace
                </button>
              </div>

              {activeTab === "script" && currentScript && (
                <GlassButton
                  onClick={handleCopyScript}
                  size="sm"
                  variant="default"
                >
                  {copiedScript ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedScript ? "Copied" : "Copy"}
                </GlassButton>
              )}
            </div>

            {/* Tab 1: Terminal Console */}
            {activeTab === "terminal" && (
              <div className="flex-1 bg-black/70 rounded-xl border border-white/10 p-4 font-mono text-xs overflow-y-auto flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between text-white/40 border-b border-white/10 pb-2 mb-3 text-[11px]">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-white/20" />
                      <span>Sandbox Execution Output</span>
                    </div>
                    {latestSandbox?.output?.exit_code !== undefined && (
                      <span className="text-white/70">
                        Exit Code: {latestSandbox.output.exit_code}
                      </span>
                    )}
                  </div>

                  {sandboxSteps.length === 0 ? (
                    <div className="text-white/40 italic py-16 text-center">
                      No sandbox execution records yet. Waiting for script generator...
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {sandboxSteps.map((s, idx) => (
                        <div key={idx} className="border-b border-white/5 pb-3 last:border-0">
                          <div className="text-white/50 text-[11px] mb-1 font-semibold">
                            $ python3 repro_attempt_{idx + 1}.py
                          </div>
                          {s.output?.stdout && (
                            <pre className="text-emerald-400/90 whitespace-pre-wrap leading-relaxed">
                              {s.output.stdout}
                            </pre>
                          )}
                          {s.output?.stderr && (
                            <pre className="text-rose-400 whitespace-pre-wrap leading-relaxed mt-1">
                              {s.output.stderr}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="pt-3 text-white/30 text-[11px] flex items-center justify-between border-t border-white/5">
                  <span>Isolated Docker Sandbox</span>
                  <span>Attempts: {sandboxSteps.length}</span>
                </div>
              </div>
            )}

            {/* Tab 2: Reproduction Script */}
            {activeTab === "script" && (
              <div className="flex-1 bg-black/70 rounded-xl border border-white/10 p-4 font-mono text-xs overflow-y-auto">
                {currentScript ? (
                  <pre className="text-white/90 leading-relaxed whitespace-pre-wrap">
                    {currentScript}
                  </pre>
                ) : (
                  <div className="text-white/40 italic py-16 text-center">
                    Reproduction script is being formulated by the LLM reasoning agent...
                  </div>
                )}
              </div>
            )}

            {/* Tab 3: PIECE 3 — ARTIFACTS PANEL */}
            {activeTab === "artifacts" && (
              <div className="flex-1 space-y-3 overflow-y-auto">
                <div className="flex items-center justify-between text-xs text-white/50 mb-2">
                  <span>Storage Provider: <strong className="text-white/80">Backblaze B2</strong> (S3-Compatible)</span>
                  <span>Fetched via <code className="text-white/60 font-mono">GET /api/runs/{'{id}'}/artifacts</code></span>
                </div>

                {artifacts.length === 0 ? (
                  <GlassPanel variant="subtle" className="p-12 text-center text-white/40">
                    <FileText className="w-8 h-8 mx-auto mb-2 text-white/20" />
                    <p className="text-sm font-medium text-white/60">No artifacts generated yet</p>
                    <p className="text-xs text-white/40 mt-1">
                      Reproduction scripts, execution logs, and patch diffs will appear here once uploaded to Backblaze B2.
                    </p>
                  </GlassPanel>
                ) : (
                  <div className="space-y-2">
                    {artifacts.map((art) => {
                      const isFailed = art.status === "upload_failed" || Boolean(art.error);
                      const isUploaded = art.status === "uploaded";

                      return (
                        <GlassPanel
                          key={art.id}
                          variant="subtle"
                          className={`p-4 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                            isFailed ? "border-rose-500/30 bg-rose-500/5" : ""
                          }`}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <GlassBadge variant="neutral" className="text-[11px] uppercase">
                                {art.type}
                              </GlassBadge>

                              {/* Status Badge */}
                              {isFailed ? (
                                <GlassBadge variant="error" dot className="font-semibold text-[11px]">
                                  <XCircle className="w-3 h-3 text-rose-400" />
                                  Upload Failed
                                </GlassBadge>
                              ) : isUploaded ? (
                                <GlassBadge variant="succeeded" dot className="text-[11px]">
                                  Uploaded
                                </GlassBadge>
                              ) : (
                                <GlassBadge variant="neutral" className="text-[11px]">
                                  {art.status}
                                </GlassBadge>
                              )}
                            </div>

                            {/* Storage Path Key in Backblaze B2 */}
                            <div className="text-xs font-mono text-white/80 truncate">
                              {art.storage_path}
                            </div>

                            {/* Surface Error if upload failed */}
                            {isFailed && art.error && (
                              <div className="mt-1.5 text-xs text-rose-300/90 font-mono bg-rose-950/30 p-2 rounded-lg border border-rose-500/20">
                                <span className="font-semibold text-rose-400">Error:</span> {art.error}
                              </div>
                            )}
                          </div>

                          {/* Action / Presigned Download Link */}
                          <div className="shrink-0 flex items-center gap-2">
                            {art.download_url ? (
                              <a
                                href={art.download_url}
                                target="_blank"
                                rel="noreferrer"
                                download
                              >
                                <GlassButton size="sm" variant="default" className="text-white hover:bg-white/10">
                                  <Download className="w-3.5 h-3.5 text-white/80" />
                                  Download File
                                </GlassButton>
                              </a>
                            ) : isFailed ? (
                              <span className="text-xs text-rose-400 font-mono italic">
                                File Unavailable
                              </span>
                            ) : (
                              <span className="text-xs text-white/40 font-mono italic">
                                Processing...
                              </span>
                            )}
                          </div>
                        </GlassPanel>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Tab 4: Raw Stack Trace */}
            {activeTab === "stacktrace" && (
              <div className="flex-1 bg-black/70 rounded-xl border border-white/10 p-4 font-mono text-xs overflow-y-auto">
                {runData?.bug_report?.raw_stack_trace ? (
                  <pre className="text-emerald-300/90 leading-relaxed whitespace-pre-wrap">
                    {runData.bug_report.raw_stack_trace}
                  </pre>
                ) : (
                  <div className="text-white/40 italic py-16 text-center">
                    No stack trace attached to this bug report.
                  </div>
                )}
              </div>
            )}
          </GlassPanel>
        </div>
      </div>
    </div>
  );
}
