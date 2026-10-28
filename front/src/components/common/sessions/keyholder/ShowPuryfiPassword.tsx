import { useState } from "react";
import { Check, Copy, Eye, EyeOff, KeyRound, TriangleAlert } from "lucide-react";

import SectionCard from "@/components/ui/section-card";
import StatusPill from "@/components/ui/status-pill";
import { copyText } from "@/lib/clipboard";
import { cn } from "@/lib/utils";

export default function ShowPuryfiPassword({ puryfiPassword }: { puryfiPassword: string }) {
    const [showPassword, setShowPassword] = useState(false);
    const [copied, setCopied] = useState(false);
    const [copyFailed, setCopyFailed] = useState(false);

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
        <SectionCard
            icon={<KeyRound />}
            title="Emergency password"
            description="Use this only if Puryfi must be unlocked outside Chaster."
            accent="rose"
            action={<StatusPill tone="keyholder">Keyholder</StatusPill>}
            className="h-full"
        >
            <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-[#0F0E16] px-3.5 py-3">
                    <code
                        className={cn(
                            "min-w-0 flex-1 text-sm font-semibold tracking-[0.15em]",
                            showPassword ? "break-all text-slate-200 select-all" : "text-slate-500",
                        )}
                    >
                        {showPassword ? puryfiPassword : "••••••••••••"}
                    </code>

                    <div className="flex shrink-0 items-center gap-1">
                        <button
                            type="button"
                            onClick={() => setShowPassword((current) => !current)}
                            aria-label={showPassword ? "Hide password" : "Reveal password"}
                            title={showPassword ? "Hide password" : "Reveal password"}
                            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 text-[11px] font-medium text-slate-400 transition-colors hover:border-white/20 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                        >
                            {showPassword ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                            {showPassword ? "Hide" : "Reveal"}
                        </button>

                        <button
                            type="button"
                            onClick={handleCopyPassword}
                            aria-label="Copy password"
                            title="Copy password"
                            className="inline-flex size-8 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-slate-400 transition-colors hover:border-emerald-400/20 hover:bg-emerald-400/10 hover:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60"
                        >
                            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                        </button>
                    </div>
                </div>

                <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-slate-500">
                    <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-amber-400/80" />
                    Keep this password private. It can unlock Puryfi without Chaster.
                </p>

                {copyFailed ? (
                    <p className="text-[11px] leading-relaxed text-amber-400">
                        Copy blocked by the browser — long-press the password to copy it manually.
                    </p>
                ) : null}

                <span role="status" className="sr-only">
                    {copied ? "Password copied" : ""}
                </span>
            </div>
        </SectionCard>
    );
}
