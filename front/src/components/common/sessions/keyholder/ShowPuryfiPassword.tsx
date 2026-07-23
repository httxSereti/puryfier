import { EyeOff, Eye, Check, Copy, AlertTriangle } from "lucide-react";
import { useState } from "react"
import { copyText } from "@/lib/clipboard";

export default function ShowPuryfiPassword({ puryfiPassword }: { puryfiPassword: string }) {
    const [showPassword, setShowPassword] = useState(false)
    const [copied, setCopied] = useState(false)
    const [copyFailed, setCopyFailed] = useState(false)

    const handleCopyPassword = async () => {
        setCopyFailed(false);
        const ok = await copyText(puryfiPassword);
        if (ok) {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } else {
            setCopyFailed(true);
            setTimeout(() => setCopyFailed(false), 3000);
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
                <div className="flex flex-col gap-2">
                    <div className="flex justify-between items-center bg-black/60 p-3 rounded-lg border border-slate-800">
                        <span className="text-sm font-mono font-bold text-cyan-400 tracking-widest select-all">
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
                    {copyFailed && (
                        <p className="text-xs text-amber-400 flex items-center gap-1.5">
                            <AlertTriangle size={12} />
                            Copy blocked by the browser — long-press the password to copy it manually.
                        </p>
                    )}
                </div>
            )}
        </div>
    )
}
