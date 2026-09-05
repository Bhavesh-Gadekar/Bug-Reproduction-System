import type { Metadata } from "next";
import {
  ClerkProvider,
  OrganizationSwitcher,
  SignedIn,
  SignedOut,
  SignInButton,
  UserButton,
} from "@clerk/nextjs";
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
    <ClerkProvider>
      <html lang="en">
        <body className="bg-slate-950 text-slate-100 min-h-screen">
          {/* Top Navigation Bar */}
          <nav className="border-b border-white/10 bg-slate-950/60 backdrop-blur-md sticky top-0 z-50">
            <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <a href="/" className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 via-purple-500 to-cyan-400 flex items-center justify-center font-bold text-white text-sm">
                    BR
                  </div>
                  <span className="font-bold text-lg tracking-tight gradient-text">
                    BugRepro Agent
                  </span>
                </a>
              </div>

              <div className="flex items-center gap-4">
                <SignedIn>
                  <OrganizationSwitcher
                    appearance={{
                      elements: {
                        organizationSwitcherTrigger:
                          "bg-slate-900 border border-white/10 text-slate-200 px-3 py-1.5 rounded-lg text-sm hover:bg-slate-800",
                      },
                    }}
                  />
                  <UserButton
                    appearance={{
                      elements: {
                        avatarBox: "w-9 h-9 border border-indigo-500/30",
                      },
                    }}
                  />
                </SignedIn>
                <SignedOut>
                  <SignInButton mode="modal">
                    <button className="px-4 py-1.5 text-sm font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors">
                      Sign In
                    </button>
                  </SignInButton>
                </SignedOut>
              </div>
            </div>
          </nav>

          <main>{children}</main>
        </body>
      </html>
    </ClerkProvider>
  );
}
