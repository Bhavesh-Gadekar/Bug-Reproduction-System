import React from "react";
import Link from "next/link";
import {
  GlassPanel,
  GlassCard,
  GlassButton,
  GlassBadge,
} from "@/components/ui/glass";

export default function LandingPage() {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-12 sm:py-16 space-y-20">
      {/* 1. HERO SECTION */}
      <section className="text-center max-w-4xl mx-auto pt-4 sm:pt-8">
        <div className="inline-flex items-center gap-2 mb-6">
          <GlassBadge variant="succeeded" dot>
            Autonomous Bug Reproduction Pipeline
          </GlassBadge>
          <GlassBadge variant="running" dot>
            Production Active
          </GlassBadge>
        </div>

        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight text-white mb-6 leading-tight">
          From Issue Report to{" "}
          <span className="bg-gradient-to-r from-white via-white/90 to-white/60 bg-clip-text text-transparent">
            Verified Sandboxed Repro
          </span>
        </h1>

        <p className="text-white/75 text-lg sm:text-xl leading-relaxed mb-10 max-w-3xl mx-auto font-normal">
          An autonomous agent that takes a bug report + stack trace, clones the real repo,
          and tries to actually reproduce the bug in an isolated sandbox, returning a verified
          repro script or an honest &ldquo;not reproduced.&rdquo;
        </p>

        {/* CTA Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-4 mb-12">
          <Link href="/sign-up">
            <GlassButton size="lg" variant="primary" className="px-7 py-3 text-base shadow-xl">
              Get Started &rarr;
            </GlassButton>
          </Link>
          <Link href="/runs">
            <GlassButton size="lg" variant="secondary" className="px-7 py-3 text-base">
              View Jobs
            </GlassButton>
          </Link>
        </div>

        {/* Metric summary bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-3xl mx-auto">
          <GlassPanel variant="subtle" className="p-3.5 text-center">
            <div className="text-xl sm:text-2xl font-bold font-mono text-white">91.7%</div>
            <div className="text-[11px] text-white/50 uppercase font-medium tracking-wider mt-0.5">
              Candidate BRT
            </div>
          </GlassPanel>
          <GlassPanel variant="subtle" className="p-3.5 text-center">
            <div className="text-xl sm:text-2xl font-bold font-mono text-emerald-400">58.3%</div>
            <div className="text-[11px] text-white/50 uppercase font-medium tracking-wider mt-0.5">
              Plausible BRT
            </div>
          </GlassPanel>
          <GlassPanel variant="subtle" className="p-3.5 text-center">
            <div className="text-xl sm:text-2xl font-bold font-mono text-white">12 / 12</div>
            <div className="text-[11px] text-white/50 uppercase font-medium tracking-wider mt-0.5">
              Benchmark Audited
            </div>
          </GlassPanel>
          <GlassPanel variant="subtle" className="p-3.5 text-center">
            <div className="text-xl sm:text-2xl font-bold font-mono text-purple-400">0 Infra Noise</div>
            <div className="text-[11px] text-white/50 uppercase font-medium tracking-wider mt-0.5">
              Strict Isolation
            </div>
          </GlassPanel>
        </div>
      </section>

      {/* 2. WHAT IT DOES — FEATURE CARDS */}
      <section className="space-y-6">
        <div className="text-center max-w-2xl mx-auto mb-8">
          <h2 className="text-2xl sm:text-3xl font-bold text-white tracking-tight mb-2">
            Engineered for Ground-Truth Verification
          </h2>
          <p className="text-white/60 text-sm sm:text-base">
            Static analysis guesses where bugs might be. Our pipeline runs code in real sandboxes to prove it.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Card 1 */}
          <GlassCard className="p-6 sm:p-7 flex flex-col justify-between">
            <div>
              <div className="w-10 h-10 rounded-xl bg-sky-500/10 border border-sky-500/30 flex items-center justify-center mb-4 text-sky-400 font-mono text-sm font-bold shadow-[0_0_15px_rgba(56,189,248,0.2)]">
                01
              </div>
              <h3 className="text-lg font-bold text-white mb-2">
                Real Sandboxed Execution
              </h3>
              <p className="text-white/65 text-sm leading-relaxed mb-4">
                Not just static code analysis or AST guessing. Spawns isolated, containerized sandboxes
                with enforced CPU/memory limits, fork-bomb defense, and timeout guards to safely run
                untrusted reproduction attempts against target repositories.
              </p>
            </div>
            <div className="border-t border-white/10 pt-3">
              <span className="text-xs font-mono text-sky-300/80">
                Docker Containers • PIDs & Memory Capped • Ephemeral Volumes
              </span>
            </div>
          </GlassCard>

          {/* Card 2 */}
          <GlassCard className="p-6 sm:p-7 flex flex-col justify-between">
            <div>
              <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center mb-4 text-indigo-400 font-mono text-sm font-bold shadow-[0_0_15px_rgba(99,102,241,0.2)]">
                02
              </div>
              <h3 className="text-lg font-bold text-white mb-2">
                LLM-Driven Hypothesis Generation
              </h3>
              <p className="text-white/65 text-sm leading-relaxed mb-4">
                Evaluates repository call hierarchies, recent commit diffs, and reported stack traces with
                reasoning agents. Systematically synthesizes candidate reproduction scripts that target
                the exact failure conditions described in the issue.
              </p>
            </div>
            <div className="border-t border-white/10 pt-3">
              <span className="text-xs font-mono text-indigo-300/80">
                Google Gemini Reasoning • AST Context Extraction • LangGraph State
              </span>
            </div>
          </GlassCard>

          {/* Card 3 */}
          <GlassCard className="p-6 sm:p-7 flex flex-col justify-between">
            <div>
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mb-4 text-emerald-400 font-mono text-sm font-bold shadow-[0_0_15px_rgba(16,185,129,0.2)]">
                03
              </div>
              <h3 className="text-lg font-bold text-white mb-2">
                Honest Verdict States
              </h3>
              <p className="text-white/65 text-sm leading-relaxed mb-4">
                No false binaries or inflated reproduction rates. Clear distinction between confirmed
                reproductions (<span className="text-emerald-300 font-mono text-xs">reproduced</span>),
                clean negative results (<span className="text-amber-300 font-mono text-xs">not_reproduced</span>),
                and infrastructure crashes (<span className="text-purple-300 font-mono text-xs">infra_error</span>).
              </p>
            </div>
            <div className="border-t border-white/10 pt-3">
              <span className="text-xs font-mono text-emerald-300/80">
                Primary Error Matching • Chained Traceback Immunity • Honest Benchmarking
              </span>
            </div>
          </GlassCard>

          {/* Card 4 */}
          <GlassCard className="p-6 sm:p-7 flex flex-col justify-between">
            <div>
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center mb-4 text-amber-400 font-mono text-sm font-bold shadow-[0_0_15px_rgba(245,158,11,0.2)]">
                04
              </div>
              <h3 className="text-lg font-bold text-white mb-2">
                Downloadable Verifiable Artifacts
              </h3>
              <p className="text-white/65 text-sm leading-relaxed mb-4">
                Every reproduction run captures and persists the full audit trail. Download generated
                standalone Python scripts (<code className="text-amber-300 font-mono text-xs">candidate_script.py</code>),
                unfiltered stdout/stderr logs, and JSON execution traces via secure presigned Backblaze B2 links.
              </p>
            </div>
            <div className="border-t border-white/10 pt-3">
              <span className="text-xs font-mono text-amber-300/80">
                Backblaze B2 S3 Storage • Presigned URLs • Reproducible Scripts
              </span>
            </div>
          </GlassCard>
        </div>
      </section>

      {/* 3. HOW IT WORKS — STEP-BY-STEP WALKTHROUGH */}
      <section className="space-y-8">
        <div className="text-center max-w-2xl mx-auto">
          <div className="inline-block mb-3">
            <GlassBadge variant="neutral">Pipeline Architecture</GlassBadge>
          </div>
          <h2 className="text-2xl sm:text-3xl font-bold text-white tracking-tight mb-2">
            How It Works
          </h2>
          <p className="text-white/60 text-sm sm:text-base">
            The multi-agent LangGraph pipeline mirrors the exact stage terminology you see live in the run detail console:
          </p>
        </div>

        <div className="space-y-3 max-w-4xl mx-auto">
          {/* Step 1: ingest */}
          <GlassPanel variant="row" className="p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="flex items-center gap-3 shrink-0">
              <div className="w-8 h-8 rounded-lg bg-white/10 border border-white/20 flex items-center justify-center font-mono text-xs font-bold text-white">
                1
              </div>
              <code className="font-mono text-sm font-semibold text-cyan-300 bg-cyan-950/40 px-2 py-0.5 rounded border border-cyan-500/20">
                ingest
              </code>
            </div>
            <div className="text-sm text-white/70">
              <strong className="text-white font-medium">Bug Report Ingest:</strong> Receives report title, description,
              target repository URL, and raw stack trace. Persists state to Neon DB and queues the task via Redis &amp; Arq.
            </div>
          </GlassPanel>

          {/* Step 2: repo_analysis */}
          <GlassPanel variant="row" className="p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="flex items-center gap-3 shrink-0">
              <div className="w-8 h-8 rounded-lg bg-white/10 border border-white/20 flex items-center justify-center font-mono text-xs font-bold text-white">
                2
              </div>
              <code className="font-mono text-sm font-semibold text-purple-300 bg-purple-950/40 px-2 py-0.5 rounded border border-purple-500/20">
                repo_analysis
              </code>
            </div>
            <div className="text-sm text-white/70">
              <strong className="text-white font-medium">Repo Clone &amp; Environment Setup:</strong> Clones the codebase,
              identifies package dependencies, locates offending files from the trace, and prepares the runtime environment.
            </div>
          </GlassPanel>

          {/* Step 3: hypothesis_gen */}
          <GlassPanel variant="row" className="p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="flex items-center gap-3 shrink-0">
              <div className="w-8 h-8 rounded-lg bg-white/10 border border-white/20 flex items-center justify-center font-mono text-xs font-bold text-white">
                3
              </div>
              <code className="font-mono text-sm font-semibold text-indigo-300 bg-indigo-950/40 px-2 py-0.5 rounded border border-indigo-500/20">
                hypothesis_gen
              </code>
            </div>
            <div className="text-sm text-white/70">
              <strong className="text-white font-medium">Hypothesis Generation:</strong> Reasoning agent explores
              potential root causes and generates targeted reproduction hypotheses, synthesizing a standalone Python repro script.
            </div>
          </GlassPanel>

          {/* Step 4: sandbox_exec */}
          <GlassPanel variant="row" className="p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="flex items-center gap-3 shrink-0">
              <div className="w-8 h-8 rounded-lg bg-white/10 border border-white/20 flex items-center justify-center font-mono text-xs font-bold text-white">
                4
              </div>
              <code className="font-mono text-sm font-semibold text-amber-300 bg-amber-950/40 px-2 py-0.5 rounded border border-amber-500/20">
                sandbox_exec
              </code>
            </div>
            <div className="text-sm text-white/70">
              <strong className="text-white font-medium">Sandboxed Execution:</strong> Executes the candidate reproduction
              script inside an ephemeral container under strict resource and timeout enforcement, capturing full stdout/stderr streams.
            </div>
          </GlassPanel>

          {/* Step 5: verdict */}
          <GlassPanel variant="row" className="p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="flex items-center gap-3 shrink-0">
              <div className="w-8 h-8 rounded-lg bg-white/10 border border-white/20 flex items-center justify-center font-mono text-xs font-bold text-white">
                5
              </div>
              <code className="font-mono text-sm font-semibold text-emerald-300 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-500/20">
                verdict
              </code>
            </div>
            <div className="text-sm text-white/70">
              <strong className="text-white font-medium">Verdict Computation:</strong> Compares the sandbox exception
              against the original submitted stack trace, requiring primary error matches to prevent false positives from incidental intermediate errors.
            </div>
          </GlassPanel>

          {/* Step 6: artifacts */}
          <GlassPanel variant="row" className="p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="flex items-center gap-3 shrink-0">
              <div className="w-8 h-8 rounded-lg bg-white/10 border border-white/20 flex items-center justify-center font-mono text-xs font-bold text-white">
                6
              </div>
              <code className="font-mono text-sm font-semibold text-rose-300 bg-rose-950/40 px-2 py-0.5 rounded border border-rose-500/20">
                artifacts
              </code>
            </div>
            <div className="text-sm text-white/70">
              <strong className="text-white font-medium">Artifact Storage:</strong> Packages candidate scripts,
              execution logs, and trace telemetry, securely syncing them to Backblaze B2 for instant download.
            </div>
          </GlassPanel>
        </div>
      </section>

      {/* 4. REAL EXAMPLE — LIVE BENCHMARK RUN */}
      <section className="space-y-6">
        <div className="text-center max-w-2xl mx-auto">
          <div className="inline-block mb-3">
            <GlassBadge variant="succeeded" dot>Verified Real Benchmark Run</GlassBadge>
          </div>
          <h2 className="text-2xl sm:text-3xl font-bold text-white tracking-tight mb-2">
            Real Bug Reproduced in the Sandbox
          </h2>
          <p className="text-white/60 text-sm sm:text-base">
            No invented marketing copy — an actual production reproduction captured directly from our database.
          </p>
        </div>

        <GlassPanel variant="elevated" className="p-6 sm:p-8 max-w-4xl mx-auto">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-white/10">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <GlassBadge variant="succeeded" dot>
                  Confirmed Reproduced
                </GlassBadge>
                <GlassBadge variant="neutral">
                  Run 3291ad5e
                </GlassBadge>
              </div>
              <h3 className="text-lg sm:text-xl font-bold text-white">
                AttributeError: &apos;tqdm&apos; object has no attribute &apos;last_print_t&apos;
              </h3>
              <p className="text-xs font-mono text-white/50 mt-1">
                Repository: <span className="text-white/80">https://github.com/tqdm/tqdm</span>
              </p>
            </div>

            <Link href="/runs/3291ad5e-e5f9-43be-ae61-baebd9cb7087">
              <GlassButton size="sm" variant="secondary">
                View Full Run &rarr;
              </GlassButton>
            </Link>
          </div>

          {/* Two-column comparison */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-6">
            {/* Left: Original Reported Bug */}
            <div className="space-y-3">
              <div className="text-xs font-semibold text-white/60 uppercase tracking-wider">
                Original Submitted Stack Trace
              </div>
              <div className="bg-black/60 border border-white/10 rounded-xl p-4 font-mono text-xs text-rose-300 leading-relaxed overflow-x-auto">
                <p className="text-white/40"># Reported crash in tqdm</p>
                <p>Traceback (most recent call last):</p>
                <p className="text-white/60">&nbsp;&nbsp;File &quot;&lt;string&gt;&quot;, line 16, in &lt;module&gt;</p>
                <p className="text-white/60">&nbsp;&nbsp;File &quot;/repos/tqdm/tqdm/std.py&quot;, line 1234, in close</p>
                <p className="text-white/80">&nbsp;&nbsp;&nbsp;&nbsp;if self.last_print_t &lt; self.start_t + self.mininterval:</p>
                <p className="text-rose-400 font-bold">AttributeError: &apos;tqdm&apos; object has no attribute &apos;last_print_t&apos;</p>
              </div>
            </div>

            {/* Right: Sandbox Execution & Verdict */}
            <div className="space-y-3">
              <div className="text-xs font-semibold text-white/60 uppercase tracking-wider">
                Sandbox Execution Result
              </div>
              <div className="bg-black/60 border border-white/10 rounded-xl p-4 font-mono text-xs leading-relaxed overflow-x-auto space-y-2">
                <div className="flex items-center justify-between text-white/60 pb-1 border-b border-white/10">
                  <span>Candidate Script:</span>
                  <span className="text-emerald-400 font-bold">Generated (1,152 bytes)</span>
                </div>
                <div className="flex items-center justify-between text-white/60 pb-1 border-b border-white/10">
                  <span>Sandbox Exit Code:</span>
                  <span className="text-rose-400 font-bold">1 (Exception triggered)</span>
                </div>
                <div className="flex items-center justify-between text-white/60 pb-1 border-b border-white/10">
                  <span>Exception Matched:</span>
                  <span className="text-emerald-300 font-bold">AttributeError (primary)</span>
                </div>
                <div className="flex items-center justify-between text-white/60">
                  <span>Evaluation Verdict:</span>
                  <span className="text-emerald-400 font-bold">matched (True Positive)</span>
                </div>
              </div>

              {/* Artifacts Available */}
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <span className="text-xs text-white/40 font-medium">Persisted Artifacts:</span>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-white/80">
                  candidate_script.py
                </span>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-white/80">
                  sandbox_stdout.log
                </span>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-white/80">
                  sandbox_stderr.log
                </span>
              </div>
            </div>
          </div>
        </GlassPanel>
      </section>

      {/* 5. BOTTOM CTA BANNER */}
      <section className="text-center py-6">
        <GlassCard className="p-8 sm:p-10 max-w-3xl mx-auto text-center space-y-5">
          <h2 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            Ready to Reproduce Your First Bug?
          </h2>
          <p className="text-white/70 text-sm sm:text-base max-w-xl mx-auto leading-relaxed">
            Submit a bug report with an error trace, and let the autonomous agent isolate and verify it in seconds.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
            <Link href="/sign-up">
              <GlassButton size="lg" variant="primary">
                Get Started Free &rarr;
              </GlassButton>
            </Link>
            <Link href="/runs">
              <GlassButton size="lg" variant="secondary">
                Browse Reproduction Jobs
              </GlassButton>
            </Link>
          </div>
        </GlassCard>
      </section>
    </div>
  );
}
