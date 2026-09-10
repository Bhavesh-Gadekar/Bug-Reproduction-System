/**
 * Clerk Appearance Theme Configuration for Liquid Glass Design System
 * Uses Clerk's official Appearance theming API (variables + elements)
 * instead of arbitrary CSS selector overrides.
 */

export const clerkGlassAppearance = {
  variables: {
    colorBackground: "transparent",
    colorPrimary: "#ffffff",
    colorText: "#ffffff",
    colorTextSecondary: "rgba(255, 255, 255, 0.65)",
    colorInputBackground: "rgba(255, 255, 255, 0.04)",
    colorInputText: "#ffffff",
    colorInputBorder: "rgba(255, 255, 255, 0.14)",
    colorDanger: "#f43f5e",
    borderRadius: "1rem",
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  },
  elements: {
    rootBox: "w-full",
    cardBox:
      "liquid-glass backdrop-blur-2xl border border-white/14 bg-white/[0.04] text-white rounded-[22px] shadow-[0_16px_48px_rgba(0,0,0,0.7)] overflow-hidden w-full",
    card: "!bg-transparent !border-0 !shadow-none !rounded-none p-6 sm:p-8",
    headerTitle: "text-white text-xl font-bold tracking-tight",
    headerSubtitle: "text-white/60 text-xs sm:text-sm mt-1",
    socialButtonsBlockButton:
      "liquid-glass-subtle border border-white/14 text-white hover:bg-white/10 hover:border-white/25 rounded-xl transition-all",
    socialButtonsBlockButtonText: "text-white/90 font-medium text-xs sm:text-sm",
    dividerLine: "bg-white/10",
    dividerText: "text-white/40 text-xs font-mono uppercase tracking-wider",
    formFieldLabel: "text-xs font-semibold uppercase tracking-wider text-white/70 mb-1.5",
    formFieldInput:
      "liquid-glass-input bg-white/[0.04] border border-white/14 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/30 focus:border-white/30 focus:outline-none transition-all",
    formButtonPrimary:
      "liquid-glass bg-white/15 hover:bg-white/20 text-white font-semibold border border-white/25 rounded-xl py-2.5 px-4 transition-all shadow-inner text-sm",
    footer: "!bg-transparent border-t border-white/10 px-6 py-4 sm:px-8 !m-0 !rounded-none",
    footerAction: "!bg-transparent text-white/60 text-xs flex justify-center items-center gap-1.5 !p-0 !m-0",
    footerActionText: "text-white/60 text-xs",
    footerActionLink: "text-white font-semibold hover:text-white/80 underline decoration-white/40 hover:decoration-white transition-all text-xs",
    footerPages: "!bg-transparent",
    footerPagesLink: "text-white/60 hover:text-white",

    formFieldSuccessText: "text-emerald-400 text-xs font-mono",
    formFieldErrorText: "text-rose-400 text-xs font-mono",
    identityPreviewText: "text-white text-xs font-mono",
    identityPreviewEditButton: "text-white/70 hover:text-white text-xs",
  },

};

