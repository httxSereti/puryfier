import { UserRound } from "lucide-react";

import StatusPill from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";
import type { PuryfiSupportTierSchema } from "@/types/api";

interface PuryfiProfileProps {
    username: string | null | undefined;
    supportTier: PuryfiSupportTierSchema | null | undefined;
    className?: string;
}

/** PuryFi account shown in the linked/offline cards once it was captured. */
export default function PuryfiProfile({
    username,
    supportTier,
    className,
}: PuryfiProfileProps) {
    if (!username) {
        return null;
    }

    const supportTierName = supportTier?.name?.trim() || null;

    return (
        <div className={cn("flex flex-wrap items-center gap-2 text-xs text-slate-400", className)}>
            <UserRound className="size-3.5 shrink-0 text-slate-500" />
            <span>
                PuryFi: <span className="font-medium text-slate-200">{username}</span>
            </span>
            {supportTierName ? (
                <StatusPill
                    tone={supportTier?.level != null ? "info" : "neutral"}
                    className="normal-case tracking-[0.02em]"
                >
                    {supportTierName}
                </StatusPill>
            ) : null}
        </div>
    );
}
