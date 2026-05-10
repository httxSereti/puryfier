import type { ChasterExtensionSessionSchema } from "@/types/api";
import ShowPuryfiPassword from "@/components/common/sessions/keyholder/ShowPuryfiPassword";

export default function SessionSettings({ session }: { session: ChasterExtensionSessionSchema }) {
    return (
        <div className="w-full px-6 py-4 flex flex-col gap-4 bg-slate-950/80 border border-slate-800 rounded-2xl text-left shadow-lg">
            <h1 className="text-xl font-bold tracking-tight text-white">
                Settings
            </h1>

            {session.lock_password && session.role === "keyholder" && (
                <ShowPuryfiPassword puryfiPassword={session.lock_password} />
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex flex-col gap-2 bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-inner">
                    <span className="text-sm text-slate-400 font-medium">Lock on Freeze</span>
                    {session.lock_on_freeze ? (
                        <span className="text-sm font-black text-cyan-400 uppercase tracking-wider">Enabled</span>
                    ) : (
                        <span className="text-sm font-black text-slate-600 uppercase tracking-wider">Disabled</span>
                    )}
                </div>
                <div className="flex flex-col gap-2 bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-inner">
                    <span className="text-sm text-slate-400 font-medium">Unlock on Unfreeze</span>
                    {session.unlock_on_unfreeze ? (
                        <span className="text-sm font-black text-emerald-400 uppercase tracking-wider">Enabled</span>
                    ) : (
                        <span className="text-sm font-black text-slate-600 uppercase tracking-wider">Disabled</span>
                    )}
                </div>
            </div>

        </div>

    )
}