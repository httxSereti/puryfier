import type { ChasterExtensionSessionSchema } from "@/types/api";
import { Link2 } from "lucide-react";

import LinkPuryfiCard from "@/components/common/sessions/wearer/LinkPuryfiCard";

export default function PuryfiConnection({ session }: { session: ChasterExtensionSessionSchema }) {
    if (!session.is_online) {
        return (
            <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                    <LinkPuryfiCard session={session} />
                </div>
            </div>
        );
    }

    return (
        <div className="w-full px-6 py-4 flex flex-row justify-between items-center gap-4 bg-slate-950/80 border border-slate-800 rounded-2xl text-left shadow-lg">
            <div className="flex items-center gap-3">
                <div className="flex p-2 shrink-0 items-center justify-center rounded-lg bg-cyan-900/50 rounded-xl shadow-inner">
                    <Link2 className="w-5 h-5 text-cyan-400" />
                </div>
                <div className="leading-tight">
                    <p className="text-sm font-medium text-slate-300">Puryfi</p>
                    <p className="text-xs text-slate-500">Successfully linked</p>
                </div>
            </div>

            <div className="flex items-center gap-1.5 rounded-full px-2.5 py-1">
                <span
                    className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400 animate-pulse"
                />
                <span className="text-xs font-medium whitespace-nowrap text-emerald-400">
                    Online
                </span>
            </div>
        </div>
    );
}