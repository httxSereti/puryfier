import { useMemo } from "react";
import { LockKeyhole } from "lucide-react";

import MotdCard from "@/components/common/cards/MotdCard";
import PageHeader from "@/components/common/layout/PageHeader";
import PageShell from "@/components/common/layout/PageShell";
import PuryfiConnection from "@/components/common/sessions/PuryfiConnection";
import SessionSettings from "@/components/common/sessions/SessionSettings";
import SessionSkeleton from "@/components/common/sessions/SessionSkeleton";
import ShowPuryfiPassword from "@/components/common/sessions/keyholder/ShowPuryfiPassword";
import ErrorAlert from "@/components/ui/error-alert";
import StatusPill from "@/components/ui/status-pill";
import { usePuryfiRealtimeStatus } from "@/hooks/usePuryfiRealtimeStatus";
import { useSession } from "@/hooks/useSession";
import { readChasterIframeParams } from "@/lib/chaster";
import { cn } from "@/lib/utils";
import type { ChasterExtensionSessionSchema } from "@/types/api";

export default function Session() {
    const { mainToken } = useMemo(() => readChasterIframeParams(), []);
    const { data: sessionData, error, isLoading, reload } = useSession(mainToken ?? null);

    // Subscribe only once the REST call has created the lock configuration:
    // opening the socket before that would race the session lookup.
    const realtimeStatus = usePuryfiRealtimeStatus("session", sessionData ? (mainToken ?? null) : null);

    const session: ChasterExtensionSessionSchema | null = sessionData
        ? { ...sessionData, ...(realtimeStatus ?? {}) }
        : null;

    const hasPassword = Boolean(session?.lock_password && session.role === "keyholder");

    return (
        <PageShell>
            <PageHeader
                subtitle="Link Puryfi to this lock and review the settings in effect."
                version={import.meta.env.VITE_APP_VERSION}
            >
                {session ? (
                    <StatusPill
                        tone={
                            session.role === "wearer"
                                ? "wearer"
                                : session.role === "keyholder"
                                    ? "keyholder"
                                    : "neutral"
                        }
                    >
                        {session.role}
                    </StatusPill>
                ) : null}
            </PageHeader>

            <MotdCard />

            {error ? (
                <ErrorAlert
                    title="Could not load this extension"
                    message={error}
                    onRetry={mainToken ? reload : undefined}
                />
            ) : isLoading ? (
                <SessionSkeleton />
            ) : session ? (
                <>
                    <div className={cn("grid gap-5", hasPassword && "lg:grid-cols-2")}>
                        <PuryfiConnection session={session} />

                        {hasPassword && session.lock_password ? (
                            <ShowPuryfiPassword puryfiPassword={session.lock_password} />
                        ) : null}
                    </div>

                    <SessionSettings session={session} />
                </>
            ) : (
                <EmptySession />
            )}
        </PageShell>
    );
}

function EmptySession() {
    return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-white/[0.07] bg-[#17151F]/90 px-4 py-14 text-center shadow-xl shadow-black/20">
            <div className="flex size-11 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-slate-400">
                <LockKeyhole className="size-5" />
            </div>
            <div>
                <p className="text-sm font-semibold text-white">No session found</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-400">
                    Open this extension from a Chaster lock to link Puryfi and view its settings.
                </p>
            </div>
        </div>
    );
}
