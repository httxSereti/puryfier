import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

type SectionCardAccent = "cyan" | "emerald" | "violet" | "amber" | "rose" | "neutral";

const accentStyles: Record<SectionCardAccent, string> = {
    cyan: "border-cyan-400/20 bg-cyan-400/10 text-cyan-300",
    emerald: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
    violet: "border-violet-400/20 bg-violet-400/10 text-violet-300",
    amber: "border-amber-400/20 bg-amber-400/10 text-amber-300",
    rose: "border-rose-400/20 bg-rose-400/10 text-rose-300",
    neutral: "border-white/10 bg-white/[0.04] text-slate-300",
};

interface SectionCardProps extends Omit<ComponentProps<"section">, "title"> {
    icon?: ReactNode;
    title: string;
    description?: string;
    action?: ReactNode;
    accent?: SectionCardAccent;
    contentClassName?: string;
}

export default function SectionCard({
    icon,
    title,
    description,
    action,
    accent = "cyan",
    className,
    contentClassName,
    children,
    ...props
}: SectionCardProps) {
    return (
        <section
            className={cn(
                "overflow-hidden rounded-2xl border border-white/[0.07] bg-[#17151F]/90 shadow-xl shadow-black/20 backdrop-blur",
                className,
            )}
            {...props}
        >
            <div className="flex items-start gap-3 border-b border-white/[0.05] px-4 py-4 sm:px-5">
                {icon ? (
                    <div
                        className={cn(
                            "flex size-9 shrink-0 items-center justify-center rounded-xl border [&>svg]:size-4",
                            accentStyles[accent],
                        )}
                    >
                        {icon}
                    </div>
                ) : null}

                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-sm font-semibold tracking-tight text-white">{title}</h2>
                        {action}
                    </div>
                    {description ? (
                        <p className="mt-0.5 text-xs leading-relaxed text-slate-400">{description}</p>
                    ) : null}
                </div>
            </div>

            <div className={cn("p-3.5 sm:p-4", contentClassName)}>{children}</div>
        </section>
    );
}
