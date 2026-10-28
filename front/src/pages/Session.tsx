import { useEffect, useRef, useState } from "react";
import axios from "axios";
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
import { getBackendUrl } from "@/lib/backend";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { ChasterExtensionSessionSchema } from "@/types/api";

export default function Session() {
    const [sessionData, setSessionData] = useState<ChasterExtensionSessionSchema | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const hasFetched = useRef(false);

    useEffect(() => {
        if (hasFetched.current) return;

        hasFetched.current = true;

        const fetchSession = async () => {
            try {
                if (!window.location.hash) {
                    throw new Error("No login token detected in URL.");
                }

                const hash = window.location.hash.substring(1);
                const params = JSON.parse(decodeURIComponent(hash));

                if (!params.mainToken) {
                    throw new Error("mainToken not found in parameters.");
                }

                const backendUrl = getBackendUrl();
                const response = await axios.get(`${backendUrl}/api/session/${params.mainToken}`);
                setSessionData(response.data);
            } catch (err: unknown) {
                setError(getApiErrorMessage(err, "Error syncing with the local server."));
            } finally {
                setIsLoading(false);
            }
        };

        fetchSession();
    }, []);

    const hasPassword = Boolean(sessionData?.lock_password && sessionData.role === "keyholder");

    return (
        <PageShell>
            <PageHeader
                subtitle="Link Puryfi to this lock and review the settings in effect."
                version={import.meta.env.VITE_APP_VERSION}
            >
                {sessionData ? (
                    <StatusPill
                        tone={
                            sessionData.role === "wearer"
                                ? "wearer"
                                : sessionData.role === "keyholder"
                                    ? "keyholder"
                                    : "neutral"
                        }
                    >
                        {sessionData.role}
                    </StatusPill>
                ) : null}
            </PageHeader>

            <MotdCard />

            {error ? (
                <ErrorAlert
                    title="Could not load this extension"
                    message={error}
                    onRetry={() => window.location.reload()}
                />
            ) : isLoading ? (
                <SessionSkeleton />
            ) : sessionData ? (
                <>
                    <div className={cn("grid gap-5", hasPassword && "lg:grid-cols-2")}>
                        <PuryfiConnection session={sessionData} />

                        {hasPassword && sessionData.lock_password ? (
                            <ShowPuryfiPassword puryfiPassword={sessionData.lock_password} />
                        ) : null}
                    </div>

                    <SessionSettings session={sessionData} />
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
