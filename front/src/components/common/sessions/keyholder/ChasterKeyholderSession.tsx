import type { ChasterExtensionSessionSchema } from "@/types/api";
import { ShieldCheck } from "lucide-react";

export default function ChasterKeyholderSession({ session }: { session: ChasterExtensionSessionSchema }) {

    if (!session) {
        return (
            <div>
                <h1>No Chaster Session</h1>
            </div>
        );
    }

    return (
        <div className="flex flex-col gap-2 text-left">
            <div className="flex items-center justify-between">
                <div className="flex flex-row gap-2 items-center">
                    <ShieldCheck className="w-5 h-5 text-slate-400" />
                    <p className="text-sm font-medium text-slate-300">Puryfi Link</p>
                </div>
                <span className={`text-sm font-semibold ${session.is_online ? "text-emerald-400" : "text-red-400"}`}>
                    {session.is_online ? "Connected" : "Disconnected"}
                </span>
            </div>
        </div>
    );
}