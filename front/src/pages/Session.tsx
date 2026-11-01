import { useMemo, useState } from "react";
import { House, LockKeyhole, Settings2, Sparkles } from "lucide-react";

import AutomationsSection from "@/components/common/automations/AutomationsSection";
import MotdCard from "@/components/common/cards/MotdCard";
import PageHeader from "@/components/common/layout/PageHeader";
import PageShell from "@/components/common/layout/PageShell";
import PuryfiConnection from "@/components/common/sessions/PuryfiConnection";
import SessionAutomationsSummary from "@/components/common/sessions/SessionAutomationsSummary";
import SessionSettings from "@/components/common/sessions/SessionSettings";
import SessionSkeleton from "@/components/common/sessions/SessionSkeleton";
import ShowPuryfiPassword from "@/components/common/sessions/keyholder/ShowPuryfiPassword";
import ErrorAlert from "@/components/ui/error-alert";
import StatusPill from "@/components/ui/status-pill";
import Tabs from "@/components/ui/tabs";
import { usePuryfiRealtimeStatus } from "@/hooks/usePuryfiRealtimeStatus";
import { useSession } from "@/hooks/useSession";
import { readChasterIframeParams } from "@/lib/chaster";
import { cn } from "@/lib/utils";
import type {
    ChasterExtensionConfigSchema,
    ChasterExtensionSessionSchema,
} from "@/types/api";

type SessionTab = "home" | "automations" | "settings";

const TABS = [
    { value: "home", label: "Home", icon: <House /> },
    { value: "automations", label: "Automations", icon: <Sparkles /> },
    { value: "settings", label: "Settings", icon: <Settings2 /> },
];

export default function Session() {
    const { mainToken } = useMemo(() => readChasterIframeParams(), []);
    const {
        data: sessionData,
        setData: setSessionData,
        error,
        isLoading,
        reload,
    } = useSession(mainToken ?? null);
    const [activeTab, setActiveTab] = useState<SessionTab>("home");

    // Subscribe only once the REST call has created the lock configuration:
    // opening the socket before that would race the session lookup.
    const realtimeStatus = usePuryfiRealtimeStatus("session", sessionData ? (mainToken ?? null) : null);

    const session: ChasterExtensionSessionSchema | null = sessionData
        ? { ...sessionData, ...(realtimeStatus ?? {}) }
        : null;

    const hasPassword = Boolean(session?.lock_password && session.role === "keyholder");

    const handleConfigSaved = (config: ChasterExtensionConfigSchema) => {
        setSessionData((current) =>
            current
                ? {
                      ...current,
                      config,
                      effective_wearer_can_control:
                          config.puryfi_permissions.wearer_can_control ??
                          current.is_self_lock,
                  }
                : current,
        );
    };

    return (
        <PageShell>
            <PageHeader
                subtitle="Link Puryfi, manage automations and adjust lock permissions."
                version={import.meta.env.VITE_APP_VERSION}
            >
                {session ? (
                    <>
                        {session.puryfi_username ? (
                            <StatusPill tone="info" className="normal-case tracking-[0.02em]">
                                PuryFi: {session.puryfi_username}
                            </StatusPill>
                        ) : null}
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
                    </>
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
                    <Tabs
                        items={TABS}
                        value={activeTab}
                        onChange={(value) => {
                            if (
                                value === "home" ||
                                value === "automations" ||
                                value === "settings"
                            ) {
                                setActiveTab(value);
                            }
                        }}
                        ariaLabel="Extension sections"
                    />

                    {activeTab === "home" ? (
                        <div
                            role="tabpanel"
                            aria-label="Home"
                            className="flex flex-col gap-5"
                        >
                            <div className={cn("grid gap-5", hasPassword && "lg:grid-cols-2")}>
                                <PuryfiConnection session={session} liveStatus={realtimeStatus} />

                                {hasPassword && session.lock_password ? (
                                    <ShowPuryfiPassword puryfiPassword={session.lock_password} />
                                ) : null}
                            </div>

                            {session.automation_mode && mainToken ? (
                                <SessionAutomationsSummary mainToken={mainToken} />
                            ) : null}
                        </div>
                    ) : null}

                    {activeTab === "automations" && mainToken ? (
                        <div role="tabpanel" aria-label="Automations">
                            <AutomationsSection
                                mainToken={mainToken}
                                onChanged={() =>
                                    setSessionData((current) =>
                                        current
                                            ? { ...current, automation_mode: true }
                                            : current,
                                    )
                                }
                            />
                        </div>
                    ) : null}

                    {activeTab === "settings" && mainToken ? (
                        <div role="tabpanel" aria-label="Settings">
                            <SessionSettings
                                session={session}
                                mainToken={mainToken}
                                onSaved={handleConfigSaved}
                            />
                        </div>
                    ) : null}
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
                <LockKeyhole />
            </div>
            <div>
                <p className="text-sm font-semibold text-white">No session found</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-400">
                    Open this extension from a Chaster lock to link Puryfi and view its state.
                </p>
            </div>
        </div>
    );
}
