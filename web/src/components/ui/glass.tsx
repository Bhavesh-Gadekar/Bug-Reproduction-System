import React from "react";
import { cn } from "@/lib/utils";

// ==========================================
// 1. GlassPanel
// ==========================================
export interface GlassPanelProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "subtle" | "elevated" | "row";
  children?: React.ReactNode;
}

export const GlassPanel = React.forwardRef<HTMLDivElement, GlassPanelProps>(
  ({ className, variant = "default", children, ...props }, ref) => {
    const variantClasses = {
      default: "liquid-glass",
      subtle: "liquid-glass-subtle",
      elevated: "liquid-glass shadow-[0_12px_40px_rgba(0,0,0,0.6)] border-white/20",
      row: "liquid-glass-row",
    };

    return (
      <div
        ref={ref}
        className={cn(variantClasses[variant], className)}
        {...props}
      >
        {children}
      </div>
    );
  }
);
GlassPanel.displayName = "GlassPanel";

// ==========================================
// 2. GlassCard
// ==========================================
export interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
  children?: React.ReactNode;
}

export const GlassCard = React.forwardRef<HTMLDivElement, GlassCardProps>(
  ({ className, interactive = false, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "liquid-glass p-5 sm:p-6",
          interactive &&
            "liquid-glass-row cursor-pointer group transition-all duration-200",
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);
GlassCard.displayName = "GlassCard";

// ==========================================
// 3. GlassButton
// ==========================================
export interface GlassButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  children?: React.ReactNode;
}

export const GlassButton = React.forwardRef<HTMLButtonElement, GlassButtonProps>(
  ({ className, variant = "default", size = "md", children, disabled, ...props }, ref) => {
    const baseStyles =
      "inline-flex items-center justify-center font-medium transition-all duration-150 disabled:opacity-40 disabled:pointer-events-none select-none";

    const sizeStyles = {
      sm: "px-3 py-1.5 text-xs rounded-xl gap-1.5",
      md: "px-4 py-2 text-xs sm:text-sm rounded-xl gap-2",
      lg: "px-5 py-2.5 text-sm rounded-2xl gap-2.5 font-semibold",
    };

    const variantStyles = {
      default:
        "liquid-glass-badge text-white/85 hover:text-white hover:bg-white/10 active:bg-white/15",
      primary:
        "liquid-glass bg-white/15 text-white font-semibold hover:bg-white/20 hover:border-white/30 active:bg-white/25 shadow-inner",
      secondary:
        "liquid-glass-subtle text-white/70 hover:text-white hover:bg-white/10 active:bg-white/15",
      ghost:
        "bg-transparent hover:bg-white/5 text-white/70 hover:text-white rounded-xl",
      danger:
        "liquid-glass-subtle text-rose-300 border-rose-500/30 hover:bg-rose-500/20 active:bg-rose-500/30",
    };

    return (
      <button
        ref={ref}
        disabled={disabled}
        className={cn(baseStyles, sizeStyles[size], variantStyles[variant], className)}
        {...props}
      >
        {children}
      </button>
    );
  }
);
GlassButton.displayName = "GlassButton";

// ==========================================
// 4. GlassBadge
// ==========================================
export type GlassBadgeVariant =
  | "succeeded"
  | "failed"
  | "error"
  | "infra_error"
  | "stale"
  | "dead_letter"
  | "running"
  | "analyzing"
  | "neutral";

export interface GlassBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: GlassBadgeVariant;
  dot?: boolean;
  children?: React.ReactNode;
}

export const GlassBadge = React.forwardRef<HTMLSpanElement, GlassBadgeProps>(
  ({ className, variant = "neutral", dot = false, children, ...props }, ref) => {
    // Preserve exact functional badge colors
    const variantStyles: Record<GlassBadgeVariant, { container: string; dot: string }> = {
      succeeded: {
        container: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30 shadow-[0_0_12px_rgba(16,185,129,0.15)]",
        dot: "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]",
      },
      failed: {
        container: "bg-rose-500/10 text-rose-300 border-rose-500/30 shadow-[0_0_12px_rgba(244,63,94,0.15)]",
        dot: "bg-rose-400",
      },
      error: {
        container: "bg-rose-500/10 text-rose-300 border-rose-500/30 shadow-[0_0_12px_rgba(244,63,94,0.15)]",
        dot: "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.7)]",
      },
      infra_error: {
        container: "bg-purple-500/10 text-purple-300 border-purple-500/30 shadow-[0_0_12px_rgba(168,85,247,0.2)]",
        dot: "bg-purple-400 shadow-[0_0_8px_rgba(168,85,247,0.7)]",
      },
      stale: {
        container: "bg-amber-500/10 text-amber-300 border-amber-500/40 shadow-[0_0_12px_rgba(245,158,11,0.2)]",
        dot: "bg-amber-400 animate-ping",
      },
      dead_letter: {
        container: "bg-amber-500/10 text-amber-300 border-amber-500/40 shadow-[0_0_12px_rgba(245,158,11,0.2)]",
        dot: "bg-amber-400 animate-ping",
      },
      running: {
        container: "bg-sky-500/10 text-sky-300 border-sky-500/30 shadow-[0_0_12px_rgba(56,189,248,0.2)]",
        dot: "bg-sky-400 animate-pulse shadow-[0_0_8px_rgba(56,189,248,0.7)]",
      },
      analyzing: {
        container: "bg-sky-500/10 text-sky-300 border-sky-500/30 shadow-[0_0_12px_rgba(56,189,248,0.2)]",
        dot: "bg-sky-400 animate-pulse shadow-[0_0_8px_rgba(56,189,248,0.7)]",
      },
      neutral: {
        container: "bg-white/5 text-white/80 border-white/14",
        dot: "bg-white/40",
      },
    };

    const current = variantStyles[variant] || variantStyles.neutral;

    return (
      <span
        ref={ref}
        className={cn(
          "liquid-glass-badge inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-mono font-medium tracking-wide",
          current.container,
          className
        )}
        {...props}
      >
        {dot && <span className={cn("w-2 h-2 rounded-full shrink-0", current.dot)} />}
        {children}
      </span>
    );
  }
);
GlassBadge.displayName = "GlassBadge";

// ==========================================
// 5. GlassInput
// ==========================================
export interface GlassInputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

export const GlassInput = React.forwardRef<HTMLInputElement, GlassInputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "liquid-glass-input w-full px-4 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-white/30 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
GlassInput.displayName = "GlassInput";

// ==========================================
// 6. GlassTextarea
// ==========================================
export interface GlassTextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

export const GlassTextarea = React.forwardRef<HTMLTextAreaElement, GlassTextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          "liquid-glass-input w-full px-4 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-white/30 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
GlassTextarea.displayName = "GlassTextarea";
