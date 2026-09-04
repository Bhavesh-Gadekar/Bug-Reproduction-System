import React from "react";

const packages = [
  {
    name: "api",
    type: "FastAPI Backend",
    description:
      "RESTful API gateway orchestrating reproduction triggers, webhooks, auth validation, and Neon DB persistence.",
    badge: "Python 3.11",
    color: "text-cyan-400",
    endpoints: ["/health", "/api/v1/health"],
  },
  {
    name: "worker",
    type: "LangGraph Agent Runner",
    description:
      "Autonomous execution engine running multi-step LangGraph workflows to isolate, reproduce, and verify bug traces.",
    badge: "Python / LangGraph",
    color: "text-purple-400",
    endpoints: ["Redis Queue: reproduction_tasks"],
  },
  {
    name: "web",
    type: "Next.js App Router (React 19 + Tailwind)",
    description:
      "Interactive developer console for initiating reproduction tasks, Clerk authentication, and viewing logs.",
    badge: "React 19 / TypeScript",
    color: "text-indigo-400",
    endpoints: ["http://localhost:3000"],
  },
];

const integrations = [
  { name: "Neon DB", role: "Serverless PostgreSQL", env: "NEON_DATABASE_URL (api & worker)" },
  { name: "Clerk Auth", role: "JWT & Route Protection", env: "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY, CLERK_SECRET_KEY" },
  { name: "Google Gemini", role: "Agent Reasoning LLM", env: "GEMINI_API_KEY (api & worker)" },
  { name: "Backblaze B2", role: "S3-Compatible Artifact Storage", env: "B2_KEY_ID, B2_APPLICATION_KEY, B2_ENDPOINT" },
  { name: "Redis", role: "Task Queue & State Broker", env: "REDIS_URL" },
];

export default function Home() {
  return (
    <div className="max-w-6xl mx-auto px-6 py-12">
      {/* Header */}
      <header className="mb-12 text-center">
        <div className="inline-flex items-center gap-2 mb-4">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            Monorepo Active
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
            React 19 + Tailwind CSS
          </span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-4">
          <span className="gradient-text">Bug Reproduction Agent</span>
        </h1>
        <p className="text-slate-400 text-lg max-w-2xl mx-auto">
          Autonomous multi-agent system powered by FastAPI, Next.js 15, LangGraph, and Backblaze B2 artifact storage.
        </p>
      </header>

      {/* Packages Grid */}
      <section className="mb-14">
        <h2 className="text-xl font-bold mb-5 text-slate-100">Workspace Packages</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {packages.map((pkg) => (
            <div key={pkg.name} className="glass-panel p-7">
              <div className="flex justify-between items-center mb-4">
                <span className={`mono text-xl font-bold ${pkg.color}`}>/{pkg.name}</span>
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                  {pkg.badge}
                </span>
              </div>
              <h3 className="text-base font-semibold text-slate-200 mb-2">{pkg.type}</h3>
              <p className="text-slate-400 text-sm mb-5 leading-relaxed">{pkg.description}</p>
              <div className="border-t border-white/10 pt-4">
                <div className="text-xs text-slate-500 mb-1.5 font-semibold uppercase tracking-wider">
                  Target Interface
                </div>
                {pkg.endpoints.map((ep, idx) => (
                  <div key={idx} className="mono text-xs text-slate-400">
                    • {ep}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Integrations Table */}
      <section className="mb-14">
        <h2 className="text-xl font-bold mb-5 text-slate-100">Service Integrations</h2>
        <div className="glass-panel p-6 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-slate-500">
                <th className="py-3 px-4 font-semibold">Service</th>
                <th className="py-3 px-4 font-semibold">Role</th>
                <th className="py-3 px-4 font-semibold">Environment Mapping</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {integrations.map((item, idx) => (
                <tr key={idx} className="hover:bg-white/[0.02]">
                  <td className="py-3.5 px-4 font-semibold text-slate-200">{item.name}</td>
                  <td className="py-3.5 px-4 text-slate-400">{item.role}</td>
                  <td className="py-3.5 px-4">
                    <code className="mono text-xs text-cyan-300 bg-cyan-950/40 border border-cyan-500/20 px-2 py-1 rounded">
                      {item.env}
                    </code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Quick Start Commands */}
      <section>
        <h2 className="text-xl font-bold mb-5 text-slate-100">Developer Workflow</h2>
        <div className="glass-panel p-7">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <div>
              <h4 className="text-sm font-semibold text-indigo-400 mb-2">Start Redis with Docker</h4>
              <pre className="mono bg-slate-950/60 p-3 rounded-lg text-xs border border-white/10 text-sky-400">
                docker compose up redis -d
              </pre>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-purple-400 mb-2">Run Python Ruff Linting</h4>
              <pre className="mono bg-slate-950/60 p-3 rounded-lg text-xs border border-white/10 text-purple-300">
                ruff check .
              </pre>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-cyan-400 mb-2">Run Web ESLint</h4>
              <pre className="mono bg-slate-950/60 p-3 rounded-lg text-xs border border-white/10 text-cyan-300">
                npm --workspace=web run lint
              </pre>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
