import { Link2, ShieldCheck } from "lucide-react";

import LinkPuryfiCard from "@/components/common/sessions/wearer/LinkPuryfiCard";
import StatusPill from "@/components/ui/status-pill";
import type { ChasterExtensionSessionSchema } from "@/types/api";

export default function PuryfiConnection({ session }: { session: ChasterExtensionSessionSchema }) {
    if (!session.is_online) {
        return <LinkPuryfiCard session={session} />;
    }

    return (
        <section className="flex h-full flex-col justify-between gap-4 rounded-2xl border border-emerald-400/15 bg-gradient-to-br from-emerald-400/[0.07] via-[#17151F] to-[#17151F] p-5 shadow-xl shadow-black/20">
            <div className="flex items-start gap-3">
                <div className="relative flex size-11 shrink-0 items-center justify-center rounded-2xl border border-emerald-400/20 bg-emerald-400/10 text-emerald-300">
                    <Link2 className="size-5" />
                    <span className="absolute -bottom-0.5 -right-0.5 size-3 rounded-full border-2 border-[#17151F] bg-emerald-400" />
                </div>

                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-sm font-semibold text-white">Puryfi connected</h2>
                        <StatusPill tone="online" dot pulse>
                            Online
                        </StatusPill>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-slate-400">
                        Your Puryfi client is linked to this lock and listening for censorship events.
                    </p>
                </div>
            </div>

            <div className="flex items-center gap-2 rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-2.5 text-[11px] text-slate-400">
                <ShieldCheck className="size-3.5 shrink-0 text-emerald-400" />
                The WebSocket connection is active.
            </div>
        </section>
    );
}
