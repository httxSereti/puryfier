import { EyeOff, Eye, Check, Copy } from "lucide-react";
import { useState } from "react"

export default function ShowPuryfiPassword({ puryfiPassword }: { puryfiPassword: string }) {
    const [showPassword, setShowPassword] = useState(false)
    const [copied, setCopied] = useState(false)


    const handleCopyPassword = () => {
        try {
            // #TODO: fix, it throws a NotAllowedError: Failed to execute 'writeText'
            navigator.clipboard.writeText(puryfiPassword);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch (error) {
            console.error("Failed to copy password:", error);
        }
    };

    return (
        <div className="flex flex-col gap-3 bg-slate-900 border border-slate-800 p-5 rounded-xl mt-2 shadow-inner">
            <div className="flex justify-between items-center">
                <span className="text-sm text-slate-300 font-semibold flex items-center gap-2">
                    Emergency Lock Password
                </span>
                <button
                    onClick={() => setShowPassword(!showPassword)}
                    className="text-slate-400 hover:text-cyan-400 transition-colors flex items-center gap-1.5 text-xs font-bold bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700 hover:border-cyan-900/50"
                >
                    {showPassword ? (
                        <><EyeOff size={14} /> Ocult</>
                    ) : (
                        <><Eye size={14} /> Reveal</>
                    )}
                </button>
            </div>
            {showPassword && (
                <div className="flex justify-between items-center bg-black/60 p-3 rounded-lg border border-slate-800">
                    <span className="text-sm font-mono font-bold text-cyan-400 tracking-widest">
                        {puryfiPassword}
                    </span>
                    <button
                        onClick={handleCopyPassword}
                        className="text-slate-400 hover:text-emerald-400 transition-all p-2 bg-slate-800 rounded-md hover:bg-slate-700"
                        title="Copy password"
                    >
                        {copied ? <Check size={18} className="text-emerald-400" /> : <Copy size={18} />}
                    </button>
                </div>
            )}
        </div>
    )
}
