import type { Metadata } from "next";
import {
  ClerkProvider,
  OrganizationSwitcher,
  SignedIn,
  SignedOut,
  SignInButton,
  UserButton,
} from "@clerk/nextjs";
import { clerkGlassAppearance } from "@/components/ui/clerk-theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bug Reproduction Agent - AI-Powered Automated Bug Repro Pipeline",
  description:
    "Autonomous multi-agent system for reproducing, isolating, and validating software bugs.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider appearance={clerkGlassAppearance}>
      <html lang="en">
        <body className="bg-[#0A0A0B] text-white min-h-screen">
          {/* Top Navigation Bar with Liquid Glass */}
          <nav className="border-b border-white/10 bg-[#0A0A0B]/75 backdrop-blur-2xl sticky top-0 z-50 shadow-[0_4px_24px_rgba(0,0,0,0.5)]">
            <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
              <div className="flex items-center gap-8">
                <a href="/runs" className="flex items-center gap-2.5 group">
                  <div className="w-8 h-8 rounded-xl bg-white/10 border border-white/20 flex items-center justify-center font-bold text-white text-xs shadow-inner group-hover:border-white/40 transition-colors">
                    BR
                  </div>
                  <span className="font-semibold text-sm tracking-tight text-white/90 group-hover:text-white transition-colors">
                    BugRepro System
                  </span>
                </a>

                <div className="flex items-center gap-1">
                  <a
                    href="/runs"
                    className="px-3.5 py-1.5 rounded-xl text-xs font-medium text-white/80 hover:text-white hover:bg-white/10 transition-all"
                  >
                    Reproduction Jobs
                  </a>
                  <a
                    href="/submit"
                    className="px-3.5 py-1.5 rounded-xl text-xs font-medium text-white/60 hover:text-white hover:bg-white/10 transition-all"
                  >
                    Submit Report
                  </a>
                  <a
                    href="/"
                    className="px-3.5 py-1.5 rounded-xl text-xs font-medium text-white/40 hover:text-white hover:bg-white/10 transition-all"
                  >
                    Overview
                  </a>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <SignedIn>
                  <OrganizationSwitcher
                    appearance={{
                      elements: {
                        organizationSwitcherTrigger:
                          "liquid-glass-badge text-white/80 px-3 py-1.5 text-xs hover:bg-white/10 transition-all",
                      },
                    }}
                  />
                  <UserButton
                    appearance={{
                      elements: {
                        avatarBox: "w-8 h-8 rounded-xl border border-white/20 shadow-inner",
                      },
                    }}
                  />
                </SignedIn>
                <SignedOut>
                  <SignInButton mode="modal">
                    <button className="liquid-glass px-3.5 py-1.5 text-xs font-semibold rounded-xl bg-white/10 hover:bg-white/15 text-white border border-white/20 transition-all shadow-inner">
                      Sign In
                    </button>
                  </SignInButton>
                </SignedOut>
              </div>
            </div>
          </nav>

          {/* Ambient Background Gradient Mesh (enables frosted glass blur visibility) */}
          <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden" aria-hidden="true">
            {/* Top-left violet / indigo glow */}
            <div className="absolute -top-[15%] left-[10%] w-[700px] h-[700px] rounded-full bg-gradient-to-br from-indigo-500/20 via-purple-600/12 to-transparent blur-[120px] transform-gpu" />
            {/* Mid-right cyan / sky glow */}
            <div className="absolute top-[25%] -right-[5%] w-[600px] h-[600px] rounded-full bg-gradient-to-bl from-sky-500/18 via-teal-500/10 to-transparent blur-[110px] transform-gpu" />
            {/* Lower-left amber / rose glow */}
            <div className="absolute top-[60%] -left-[10%] w-[550px] h-[550px] rounded-full bg-gradient-to-tr from-rose-500/12 via-amber-500/8 to-transparent blur-[110px] transform-gpu" />
            {/* Bottom-right purple glow */}
            <div className="absolute -bottom-[15%] right-[20%] w-[750px] h-[750px] rounded-full bg-gradient-to-tl from-purple-700/16 via-indigo-800/10 to-transparent blur-[130px] transform-gpu" />
          </div>

          <main className="relative z-10">{children}</main>
        </body>
      </html>
    </ClerkProvider>

  );
}

