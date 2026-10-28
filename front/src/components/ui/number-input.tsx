import { useState } from "react";

import { cn } from "@/lib/utils";

interface NumberInputProps {
    id: string;
    value: number;
    onChange: (value: number) => void;
    suffix?: string;
    min?: number;
    max?: number;
    placeholder?: string;
    disabled?: boolean;
    className?: string;
}

/**
 * Number input that keeps an internal draft while typing, so the field can be
 * cleared and edited naturally and is clamped only when it loses focus.
 */
export default function NumberInput({
    id,
    value,
    onChange,
    suffix,
    min = 0,
    max,
    placeholder,
    disabled = false,
    className,
}: NumberInputProps) {
    const [draft, setDraft] = useState(String(value));

    const commit = () => {
        const parsed = Number(draft);

        if (draft.trim() === "" || !Number.isFinite(parsed)) {
            setDraft(String(value));
            return;
        }

        const clamped = Math.min(max ?? Number.MAX_SAFE_INTEGER, Math.max(min, Math.floor(parsed)));
        setDraft(String(clamped));

        if (clamped !== value) {
            onChange(clamped);
        }
    };

    return (
        <div className={cn("relative", className)}>
            <input
                id={id}
                type="number"
                inputMode="numeric"
                min={min}
                max={max}
                value={draft}
                placeholder={placeholder}
                disabled={disabled}
                onChange={(event) => {
                    const next = event.target.value;
                    setDraft(next);

                    if (next.trim() !== "") {
                        const parsed = Number(next);
                        if (Number.isFinite(parsed)) {
                            onChange(parsed);
                        }
                    }
                }}
                onBlur={commit}
                className={cn(
                    "h-11 w-full rounded-xl border border-white/10 bg-[#0F0E16] pl-3 text-sm font-medium text-white outline-none transition-colors placeholder:text-slate-600 hover:border-white/20 focus:border-cyan-400/50 focus:ring-4 focus:ring-cyan-400/10 disabled:cursor-not-allowed disabled:opacity-60",
                    suffix ? "pr-20" : "pr-3",
                )}
            />

            {suffix ? (
                <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[11px] font-medium text-slate-500">
                    {suffix}
                </span>
            ) : null}
        </div>
    );
}
