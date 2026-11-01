import { useId } from "react";
import type { KeyboardEvent, ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface TabItem {
    value: string;
    label: string;
    icon?: ReactNode;
    /** Pin the tab to the trailing edge of the tab list. */
    align?: "end";
}

interface TabsProps {
    items: TabItem[];
    value: string;
    onChange: (value: string) => void;
    ariaLabel: string;
    className?: string;
}

/**
 * Controlled tabs with roving focus. Panels stay in the caller so each tab can
 * render different content without coupling this component to a data model.
 */
export default function Tabs({
    items,
    value,
    onChange,
    ariaLabel,
    className,
}: TabsProps) {
    const baseId = useId();

    const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
        const index = items.findIndex((item) => item.value === value);
        if (index === -1) return;

        let nextIndex: number;
        switch (event.key) {
            case "ArrowRight":
                nextIndex = (index + 1) % items.length;
                break;
            case "ArrowLeft":
                nextIndex = (index - 1 + items.length) % items.length;
                break;
            case "Home":
                nextIndex = 0;
                break;
            case "End":
                nextIndex = items.length - 1;
                break;
            default:
                return;
        }

        event.preventDefault();
        const next = items[nextIndex];
        onChange(next.value);
        document.getElementById(`${baseId}-tab-${next.value}`)?.focus();
    };

    return (
        <div
            role="tablist"
            aria-label={ariaLabel}
            onKeyDown={handleKeyDown}
            className={cn(
                "flex w-full gap-1 rounded-xl border border-white/[0.07] bg-[#17151F]/90 p-1 shadow-lg shadow-black/10",
                className,
            )}
        >
            {items.map((item) => {
                const selected = item.value === value;

                return (
                    <button
                        key={item.value}
                        id={`${baseId}-tab-${item.value}`}
                        type="button"
                        role="tab"
                        aria-selected={selected}
                        tabIndex={selected ? 0 : -1}
                        onClick={() => onChange(item.value)}
                        className={cn(
                            "inline-flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[#17151F] sm:flex-none sm:px-4",
                            selected
                                ? "bg-white/[0.08] text-white shadow-sm"
                                : "text-slate-400 hover:bg-white/[0.03] hover:text-slate-200",
                            item.align === "end" && "sm:ml-auto",
                        )}
                    >
                        {item.icon ? (
                            <span aria-hidden="true" className="[&>svg]:size-3.5">
                                {item.icon}
                            </span>
                        ) : null}
                        {item.label}
                    </button>
                );
            })}
        </div>
    );
}
