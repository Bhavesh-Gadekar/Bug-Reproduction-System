"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Bug, CheckCircle2, Flame, Loader2, Play, Sparkles } from "lucide-react";
import {
  GlassPanel,
  GlassButton,
  GlassInput,
  GlassTextarea,
  GlassBadge,
} from "@/components/ui/glass";

export default function SubmitBugReportPage() {
  const router = useRouter();

  const [title, setTitle] = useState("AttributeError: 'tqdm' object has no attribute 'last_print_t'");
  const [description, setDescription] = useState(
    "When a tqdm instance fails partway through initialization, Python GC still calls __del__ which invokes close(). close() unconditionally reads self.last_print_t, raising AttributeError."
  );
  const [rawStackTrace, setRawStackTrace] = useState(
    `Traceback (most recent call last):
  File "<string>", line 16, in <module>
  File "/repos/tqdm/tqdm/std.py", line 1234, in close
    if self.last_print_t < self.start_t + self.mininterval:
AttributeError: 'tqdm' object has no attribute 'last_print_t'`
  );
  const [gitUrl, setGitUrl] = useState("https://github.com/tqdm/tqdm");
  const [branch, setBranch] = useState("master");
  const [baseCommit, setBaseCommit] = useState("6ab24dcc5df910044f1f6e0685f95dbf9cd424f3");
  const [maxHypotheses, setMaxHypotheses] = useState(5);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    const payload = {
      title,
      description,
      raw_stack_trace: rawStackTrace,
      repo: {
        git_url: gitUrl,
        branch,
        base_commit_sha: baseCommit || undefined,
      },
      max_hypotheses: Number(maxHypotheses),
    };

    try {
      const res = await fetch(`${apiUrl}/api/bug-reports`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server returned HTTP ${res.status}`);
      }

      const data = await res.json();
      if (data.run_id) {
        router.push(`/runs/${data.run_id}`);
      } else {
        throw new Error("No run_id returned from API");
      }
    } catch (err: any) {
      console.error("Submission failed:", err);
      setError(err.message || "Failed to submit bug report. Make sure the API is running.");
      setIsSubmitting(false);
    }
  };

  const loadSample = (type: "tqdm" | "calc") => {
    if (type === "tqdm") {
      setTitle("AttributeError: 'tqdm' object has no attribute 'last_print_t'");
      setDescription(
        "When a tqdm instance fails partway through initialization, Python GC still calls __del__ which invokes close(). close() unconditionally reads self.last_print_t, raising AttributeError."
      );
      setRawStackTrace(
        `Traceback (most recent call last):
  File "<string>", line 16, in <module>
  File "/repos/tqdm/tqdm/std.py", line 1234, in close
    if self.last_print_t < self.start_t + self.mininterval:
AttributeError: 'tqdm' object has no attribute 'last_print_t'`
      );
      setGitUrl("https://github.com/tqdm/tqdm");
      setBranch("master");
      setBaseCommit("6ab24dcc5df910044f1f6e0685f95dbf9cd424f3");
    } else {
      setTitle("AssertionError: Expected values to be equal");
      setDescription("Calling calculate_discount(100, 0.2) returned 70 instead of 80 due to operator precedence bug.");
      setRawStackTrace(
        `Traceback (most recent call last):
  File "test_pricing.py", line 42, in test_discount
    assert calculate_discount(100, 0.2) == 80
AssertionError: Expected values to be equal (70 != 80)`
      );
      setGitUrl("https://github.com/example/ecommerce-engine");
      setBranch("main");
      setBaseCommit("");
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-10">
      <div className="mb-6">
        <Link
          href="/runs"
          className="inline-flex items-center gap-1.5 text-xs text-white/60 hover:text-white transition-colors liquid-glass-badge px-3 py-1.5 mb-4"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Reproduction Jobs
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <GlassBadge variant="neutral" className="px-2.5 py-0.5 text-[11px]">
                POST /api/bug-reports
              </GlassBadge>
              <span className="text-xs text-white/40 font-mono">Autonomous Pipeline</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white mb-1">
              Submit Bug Report
            </h1>
            <p className="text-white/50 text-xs sm:text-sm">
              Enqueue an autonomous LangGraph reproduction task and stream live reasoning steps.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <GlassButton
              type="button"
              onClick={() => loadSample("tqdm")}
              size="sm"
              variant="default"
              className="text-xs"
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-300" />
              Load tqdm Repro
            </GlassButton>
            <GlassButton
              type="button"
              onClick={() => loadSample("calc")}
              size="sm"
              variant="secondary"
              className="text-xs"
            >
              Load Calc Repro
            </GlassButton>
          </div>
        </div>
      </div>

      {error && (
        <GlassPanel className="mb-6 p-4 border-rose-500/30 bg-rose-500/10 text-rose-300 text-xs sm:text-sm">
          {error}
        </GlassPanel>
      )}

      <GlassPanel className="p-6 sm:p-8">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Title */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-white/70 mb-2">
              Bug Report Title <span className="text-rose-400">*</span>
            </label>
            <GlassInput
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. TypeError in JSON serialisation"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-white/70 mb-2">
              Description & Context
            </label>
            <GlassTextarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the trigger conditions, expected vs actual behavior..."
            />
          </div>

          {/* Raw Stack Trace */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-white/70 mb-2">
              Raw Stack Trace / Exception <span className="text-rose-400">*</span>
            </label>
            <textarea
              rows={5}
              required
              value={rawStackTrace}
              onChange={(e) => setRawStackTrace(e.target.value)}
              placeholder="Paste raw Python traceback or error output..."
              className="liquid-glass-input w-full px-4 py-2.5 text-xs font-mono text-emerald-300 placeholder-white/20 focus:outline-none focus:border-white/30 leading-relaxed bg-black/60"
            />
          </div>

          {/* Repo Details Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-white/10">
            <div className="md:col-span-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-white/70 mb-2">
                Git Repository URL <span className="text-rose-400">*</span>
              </label>
              <GlassInput
                type="url"
                required
                value={gitUrl}
                onChange={(e) => setGitUrl(e.target.value)}
                placeholder="https://github.com/org/repo"
                className="font-mono text-xs sm:text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-white/70 mb-2">
                Git Branch
              </label>
              <GlassInput
                type="text"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="main"
                className="font-mono text-xs sm:text-sm"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-white/70 mb-2">
                Base Commit SHA (Optional)
              </label>
              <GlassInput
                type="text"
                value={baseCommit}
                onChange={(e) => setBaseCommit(e.target.value)}
                placeholder="e.g. 6ab24dcc5df9..."
                className="font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-white/70 mb-2">
                Max Hypotheses
              </label>
              <GlassInput
                type="number"
                min={1}
                max={10}
                value={maxHypotheses}
                onChange={(e) => setMaxHypotheses(Number(e.target.value))}
              />
            </div>
          </div>

          {/* Submit Action */}
          <div className="pt-4 flex items-center justify-end gap-3 border-t border-white/10">
            <Link href="/runs">
              <GlassButton type="button" variant="ghost" size="md">
                Cancel
              </GlassButton>
            </Link>
            <GlassButton
              type="submit"
              disabled={isSubmitting}
              variant="primary"
              size="lg"
              className="gap-2 font-bold"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Enqueueing Task...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-white" />
                  Start Live Reproduction
                </>
              )}
            </GlassButton>
          </div>
        </form>
      </GlassPanel>
    </div>
  );
}

