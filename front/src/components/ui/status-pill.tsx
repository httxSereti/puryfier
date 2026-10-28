import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type StatusPillTone = "online" | "offline" | "warning" | "neutral" | "wearer" | "keyholder" | "info";

const toneStyles: Record<StatusPillTone, { pill: string; dot?: string }> = {
    online: {
        pill: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
        dot: "bg-emerald-400",
    },
    offline: {
        pill: "border-red-400/20 bg-red-400/10 text-red-300",
        dot: "bg-red-400",
    },
    warning: {
        pill: "border-amber-400/25 bg-amber-400/10 text-amber-300",
        dot: "bg-amber-400",
    },
    neutral: {
        pill: "border-white/10 bg-white/[0.04] text-slate-400",
        dot: "bg-slate-500",
    },
    wearer: {
        pill: "border-rose-400/25 bg-rose-400/10 text-rose-300",
    },
    keyholder: {
        pill: "border-violet-400/25 bg-violet-400/10 text-violet-300",
    },
    info: {
        pill: "border-cyan-400/25 bg-cyan-400/10 text-cyan-300",
        dot: "bg-cyan-400",
    },
};

interface StatusPillProps {
    tone: StatusPillTone;
    children: ReactNode;
    dot?: boolean;
    pulse?: boolean;
    className?: string;
}

export default function StatusPill({ tone, children, dot = false, pulse = false, className }: StatusPillProps) {
    return (
        <span
            className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em]",
                toneStyles[tone].pill,
                className,
            )}
        >
            {dot ? (
                <span
                    className={cn(
                        "size-1.5 shrink-0 rounded-full",
                        toneStyles[tone].dot,
                        pulse && "animate-pulse",
                    )}
                />
            ) : null}
            {children}
        </span>
    );
}
