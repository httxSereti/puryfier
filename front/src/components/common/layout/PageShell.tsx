import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface PageShellProps {
    children: ReactNode;
    className?: string;
}

/**
 * Shared page frame: dark backdrop with soft brand glows, centered content and
 * consistent spacing for both the extension and configuration iframes.
 */
export default function PageShell({ children, className }: PageShellProps) {
    return (
        <div className="relative min-h-screen w-full overflow-x-hidden bg-[#211E2C] text-slate-100">
            <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-gradient-to-b from-white/[0.025] to-transparent"
            />

            <main
                className={cn(
                    "relative mx-auto flex w-full max-w-5xl flex-col gap-5 px-3 py-5 sm:px-6 sm:py-8",
                    className,
                )}
            >
                {children}
            </main>
        </div>
    );
}
