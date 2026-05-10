import type { ChasterExtensionSessionSchema } from "@/types/api";
import { Loader2 } from "lucide-react";

export default function SessionSidebar({ session, isLoading }: { session: ChasterExtensionSessionSchema | null, isLoading: boolean }) {
    if (isLoading || !session) {
        return (
            <div className="w-full md:w-80 bg-[#14131A] rounded-2xl p-6 flex flex-col space-y-5 relative overflow-hidden">
                <h1 className="text-xl font-bold tracking-tight text-white">
                    Statistiques
                </h1>
                <div className="flex flex-col items-center justify-center py-12 space-y-4">
                    <Loader2 className="w-10 h-10 text-purple-500 animate-spin" />
                    <p className="text-sm text-slate-400 animate-pulse font-medium">Loading...</p>
                </div>
            </div>
        )
    }

    return (
        <div className="w-full md:w-64 bg-[#14131A] rounded-2xl p-4 flex flex-col space-y-5 relative overflow-hidden">

            <h1 className="text-xl font-bold tracking-tight text-white">
                Statistiques
            </h1>

            <div className="bg-slate-950/60 p-5 rounded-2xl border border-slate-800/80 hover:border-indigo-900/50 transition-all group mt-auto relative z-10">
                <p className="text-xs text-slate-500 uppercase font-bold tracking-widest mb-2">Puryfi Link Status</p>
                <div className="flex items-center gap-3">
                    <span className="relative flex h-4 w-4">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span className={`relative inline-flex rounded-full h-4 w-4 ${session.is_online ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]" : "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]"}`}></span>
                    </span>
                    <p className={`text-base font-bold ${session.is_online ? "text-emerald-400" : "text-red-400"}`}>{session.is_online ? "Online" : "Offline"}</p>
                </div>
            </div>

            <div className="bg-slate-950/60 p-5 rounded-2xl border border-slate-800/80 hover:border-indigo-900/50 transition-all group relative z-10">
                <p className="text-xs text-slate-500 uppercase font-bold tracking-widest mb-2">Purify Lock Status</p>
                <p className="text-base font-bold text-slate-400">{session.lock_password ? "🔒 Locked" : "🔓 Unlocked"}</p>
            </div>

        </div>
    );
}