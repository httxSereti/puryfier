import { useId } from "react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type SwitchColor = "cyan" | "emerald" | "violet";

const colorStyles: Record<SwitchColor, { icon: string; track: string; ring: string }> = {
    cyan: {
        icon: "border-cyan-400/20 bg-cyan-400/10 text-cyan-300",
        track: "bg-cyan-500",
        ring: "focus-visible:ring-cyan-400/60",
    },
    emerald: {
        icon: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
        track: "bg-emerald-500",
        ring: "focus-visible:ring-emerald-400/60",
    },
    violet: {
        icon: "border-violet-400/20 bg-violet-400/10 text-violet-300",
        track: "bg-violet-500",
        ring: "focus-visible:ring-violet-400/60",
    },
};

interface ConfigurationSwitchProps {
    icon: ReactNode;
    title: string;
    description: string;
    checked: boolean;
    onChange: () => void;
    baseColor?: SwitchColor;
    disabled?: boolean;
}

export default function ConfigurationSwitch({
    icon,
    title,
    description,
    checked,
    onChange,
    baseColor = "cyan",
    disabled = false,
}: ConfigurationSwitchProps) {
    const titleId = useId();
    const colors = colorStyles[baseColor];

    return (
        <div
            className={cn(
                "flex items-start gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5 transition-colors sm:items-center sm:gap-4 sm:p-4",
                disabled ? "opacity-90" : "hover:border-white/[0.11] hover:bg-white/[0.03]",
            )}
        >
            <div
                className={cn(
                    "flex size-10 shrink-0 items-center justify-center rounded-xl border [&>svg]:size-4",
                    colors.icon,
                )}
            >
                {icon}
            </div>

            <div className="min-w-0 flex-1 text-left">
                <p id={titleId} className="text-sm font-medium leading-snug text-slate-100">
                    {title}
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-slate-400">{description}</p>
            </div>

            <button
                type="button"
                role="switch"
                aria-checked={checked}
                aria-labelledby={titleId}
                onClick={disabled ? undefined : onChange}
                disabled={disabled}
                className={cn(
                    "relative mt-0.5 inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#17151F] sm:mt-0",
                    colors.ring,
                    checked ? colors.track : "bg-slate-700/80",
                    disabled && "cursor-not-allowed opacity-50",
                )}
            >
                <span
                    aria-hidden="true"
                    className={cn(
                        "pointer-events-none block size-5 rounded-full bg-white shadow-md ring-0 transition-transform duration-200 ease-in-out",
                        checked ? "translate-x-5" : "translate-x-0",
                    )}
                />
            </button>
        </div>
    );
}
