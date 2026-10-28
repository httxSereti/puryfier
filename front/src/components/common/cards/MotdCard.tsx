import { Info } from "lucide-react";

import StatusPill from "@/components/ui/status-pill";

export default function MotdCard() {
    return (
        <div className="flex items-start gap-3 rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.06] px-4 py-3.5 shadow-lg shadow-black/10 sm:items-center">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-cyan-400/20 bg-cyan-400/10 text-cyan-300">
                <Info className="size-4" />
            </div>

            <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-cyan-100">Puryfier is in development</p>
                <p className="mt-0.5 text-xs leading-relaxed text-cyan-100/60">
                    Some features may not work as expected. Thanks for testing!
                </p>
            </div>

            <StatusPill tone="info" className="hidden sm:inline-flex">
                Beta
            </StatusPill>
        </div>
    );
}
