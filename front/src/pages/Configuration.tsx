import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Link2, LockKeyhole, Settings2, ShieldCheck, Sparkles, Unplug } from "lucide-react";

import AutomationPermissionsCard from "@/components/common/automations/AutomationPermissionsCard";
import AutomationsSection from "@/components/common/automations/AutomationsSection";
import GeneralConfigurationOptions from "@/components/common/configuration/GeneralConfigurationOptions";
import CensoredMediaOptions from "@/components/common/configuration/CensoredMediaOptions";
import PuryfiControlPermissionCard from "@/components/common/configuration/PuryfiControlPermissionCard";
import ConfigurationSkeleton from "@/components/common/configuration/ConfigurationSkeleton";
import PageHeader from "@/components/common/layout/PageHeader";
import PageShell from "@/components/common/layout/PageShell";
import PuryfiProfile from "@/components/common/sessions/PuryfiProfile";
import ErrorAlert from "@/components/ui/error-alert";
import SectionCard from "@/components/ui/section-card";
import StatusPill from "@/components/ui/status-pill";
import { Button } from "@/components/ui/button";
import { useConfiguration } from "@/hooks/useConfiguration";
import { usePuryfiRealtimeStatus } from "@/hooks/usePuryfiRealtimeStatus";
import { migrateLegacyAutomations } from "@/lib/http/automations";
import { updateConfiguration } from "@/lib/http/configuration";
import { readChasterIframeParams } from "@/lib/chaster";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type {
    ChasterExtensionConfigSchema,
    ChasterExtensionConfigurationSchema,
    PuryfiRealtimeStatus,
} from "@/types/api";

const CHASTER_ORIGIN = "https://chaster.app";

function postToParent(event: string, payload?: object) {
    window.parent.postMessage(
        JSON.stringify({ type: "partner_configuration", event, ...(payload ? { payload } : {}) }),
        CHASTER_ORIGIN,
    );
}

export default function Configuration() {
    const { partnerConfigurationToken } = useMemo(() => readChasterIframeParams(), []);
    const {
        data: configurationData,
        setData: setConfigurationData,
        error: fetchError,
        isLoading,
        reload,
    } = useConfiguration(partnerConfigurationToken ?? null);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [migrationError, setMigrationError] = useState<string | null>(null);
    const [isMigrating, setIsMigrating] = useState(false);
    const [isDirty, setIsDirty] = useState(false);

    // Keep a mutable ref to the latest config so the message listener always
    // saves the values currently displayed, without re-registering on edits.
    const configRef = useRef<ChasterExtensionConfigurationSchema | null>(null);

    // Subscribe only once the REST call has created the lock configuration:
    // opening the socket before that would race the session lookup.
    const realtimeStatus = usePuryfiRealtimeStatus(
        "configuration",
        configurationData?.has_session ? (partnerConfigurationToken ?? null) : null,
    );

    const liveConfigurationData: ChasterExtensionConfigurationSchema | null = configurationData
        ? { ...configurationData, ...(realtimeStatus ?? {}) }
        : null;

    useEffect(() => {
        configRef.current = configurationData;
    }, [configurationData]);

    useEffect(() => {
        postToParent("capabilities", { features: { save: true } });
    }, []);

    useEffect(() => {
        const handleMessage = async (e: MessageEvent) => {
            // Only act on messages from the Chaster host page (REVIEW.md #7)
            if (e.origin !== CHASTER_ORIGIN || typeof e.data !== "string") return;

            let parsed: { type?: string; event?: string };
            try {
                parsed = JSON.parse(e.data);
            } catch {
                return;
            }

            if (parsed.type !== "chaster" || parsed.event !== "partner_configuration_save") return;

            const config = configRef.current?.config;

            if (!partnerConfigurationToken || !config) {
                postToParent("save_failed");
                setSaveError("Configuration is not loaded yet. Reload the page and try again.");
                return;
            }

            // Show spinner on the Chaster modal
            postToParent("save_loading");
            setSaveError(null);

            try {
                await updateConfiguration(partnerConfigurationToken, config);

                setIsDirty(false);

                // Signal success — Chaster will close the modal
                postToParent("save_success");
            } catch (err: unknown) {
                // Stop spinner and keep modal open
                postToParent("save_failed");
                setSaveError(getApiErrorMessage(err, "Save failed. Please try again."));
            }
        };

        window.addEventListener("message", handleMessage);
        return () => window.removeEventListener("message", handleMessage);
    }, [partnerConfigurationToken]);

    const handleConfigChange = (updatedConfig: ChasterExtensionConfigSchema) => {
        setConfigurationData((current) => {
            if (!current) return current;
            const next = { ...current, config: updatedConfig };
            configRef.current = next;
            return next;
        });
        setIsDirty(true);
    };

    const handleMigrate = async () => {
        if (!partnerConfigurationToken) return;

        setIsMigrating(true);
        setMigrationError(null);
        try {
            const currentConfig = configRef.current?.config;
            if (currentConfig) {
                await updateConfiguration(partnerConfigurationToken, currentConfig);
            }
            await migrateLegacyAutomations(partnerConfigurationToken);
            setIsDirty(false);
            await reload();
        } catch (cause) {
            setMigrationError(
                getApiErrorMessage(cause, "Could not convert the legacy settings."),
            );
        } finally {
            setIsMigrating(false);
        }
    };

    const error = fetchError ?? saveError ?? migrationError;

    return (
        <PageShell className="max-w-3xl">
            <PageHeader
                subtitle="Choose how Puryfier behaves inside your Chaster lock."
                version={import.meta.env.VITE_APP_VERSION}
            >
                {liveConfigurationData ? (
                    <StatusPill
                        tone={
                            liveConfigurationData.role === "wearer"
                                ? "wearer"
                                : liveConfigurationData.role === "keyholder"
                                    ? "keyholder"
                                    : "neutral"
                        }
                    >
                        {liveConfigurationData.role}
                    </StatusPill>
                ) : null}
            </PageHeader>

            {error ? (
                <ErrorAlert
                    message={error}
                    onRetry={fetchError && partnerConfigurationToken ? reload : undefined}
                />
            ) : null}

            {isLoading ? (
                <ConfigurationSkeleton />
            ) : liveConfigurationData ? (
                <>
                    <ConnectionStatus
                        data={liveConfigurationData}
                        liveStatus={realtimeStatus}
                    />

                    {liveConfigurationData.config ? (
                        <div className="flex flex-col gap-5">
                            <PuryfiControlPermissionCard
                                config={liveConfigurationData.config}
                                role={liveConfigurationData.role}
                                hasSession={liveConfigurationData.has_session}
                                selfLock={liveConfigurationData.is_self_lock}
                                onChange={handleConfigChange}
                            />

                            {liveConfigurationData.has_session ? (
                                <AutomationPermissionsCard
                                    config={liveConfigurationData.config}
                                    readOnly={
                                        liveConfigurationData.role !== "keyholder" &&
                                        !liveConfigurationData.is_self_lock
                                    }
                                    selfLock={liveConfigurationData.is_self_lock}
                                    onChange={handleConfigChange}
                                />
                            ) : null}

                            {liveConfigurationData.automation_mode &&
                            partnerConfigurationToken ? (
                                <AutomationsSection
                                    configurationToken={partnerConfigurationToken}
                                />
                            ) : (
                                <>
                                    {liveConfigurationData.has_session ? (
                                        <SectionCard
                                            icon={<Sparkles />}
                                            title="Automations are off"
                                            description="The switches below are the legacy settings. Convert them to automations to use the new rule builder."
                                            accent="violet"
                                        >
                                            <Button
                                                type="button"
                                                onClick={handleMigrate}
                                                disabled={isMigrating}
                                                className="bg-violet-500 text-slate-950 hover:bg-violet-400"
                                            >
                                                <Sparkles />
                                                {isMigrating
                                                    ? "Converting…"
                                                    : "Convert to automations"}
                                            </Button>
                                        </SectionCard>
                                    ) : null}

                                    <GeneralConfigurationOptions
                                        config={liveConfigurationData.config}
                                        onChange={handleConfigChange}
                                    />

                                    <CensoredMediaOptions
                                        config={liveConfigurationData.config}
                                        onChange={handleConfigChange}
                                    />
                                </>
                            )}
                        </div>
                    ) : (
                        <EmptyConfiguration />
                    )}

                    <footer className="flex flex-col gap-2 px-1 pt-1 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                        <span className="inline-flex items-center gap-1.5">
                            <ShieldCheck className="size-3.5" />
                            {liveConfigurationData.automation_mode
                                ? "Automation changes are saved immediately."
                                : "Changes are saved to Chaster when you confirm."}
                        </span>

                        {isDirty ? (
                            <StatusPill tone="warning" dot>
                                Unsaved changes
                            </StatusPill>
                        ) : (
                            <span className="inline-flex items-center gap-1.5">
                                <Check className="size-3.5 text-emerald-400/80" />
                                Up to date
                            </span>
                        )}
                    </footer>
                </>
            ) : (
                <EmptyConfiguration />
            )}
        </PageShell>
    );
}

function ConnectionStatus({
    data,
    liveStatus,
}: {
    data: ChasterExtensionConfigurationSchema;
    liveStatus?: PuryfiRealtimeStatus | null;
}) {
    const isOnline = data.is_online;

    const tone = isOnline
        ? "online"
        : !data.has_session
            ? "neutral"
            : data.has_linked_plugin
                ? "offline"
                : "warning";

    const label = isOnline ? "Online" : !data.has_session ? "No session" : data.has_linked_plugin ? "Offline" : "Not linked";

    const title = isOnline
        ? "Puryfi is connected"
        : !data.has_session
            ? "No active lock session"
            : data.has_linked_plugin
                ? "Puryfi is offline"
                : "Puryfi is not linked";

    const description = isOnline
        ? "Puryfi is linked to this lock and listening for censorship events."
        : !data.has_session
            ? "These preferences will apply the next time the extension is used with a lock."
            : data.has_linked_plugin
                ? "The Puryfi plugin is registered, but the WebSocket connection is currently inactive."
                : "Open the extension page from your lock to generate a WebSocket URL and link Puryfi.";

    const Icon = isOnline ? Link2 : data.has_session ? Unplug : LockKeyhole;

    return (
        <div className="flex items-start gap-3.5 rounded-2xl border border-white/[0.07] bg-[#17151F]/90 p-4 shadow-xl shadow-black/20 backdrop-blur sm:items-center sm:p-5">
            <div
                className={cn(
                    "flex size-11 shrink-0 items-center justify-center rounded-2xl border [&>svg]:size-5",
                    isOnline
                        ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-300"
                        : !data.has_session
                            ? "border-white/10 bg-white/[0.04] text-slate-400"
                            : data.has_linked_plugin
                                ? "border-red-400/20 bg-red-400/10 text-red-300"
                                : "border-amber-400/20 bg-amber-400/10 text-amber-300",
                )}
            >
                <Icon />
            </div>

            <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-white">{title}</p>
                    <StatusPill tone={tone} dot={tone !== "neutral"} pulse={isOnline}>
                        {label}
                    </StatusPill>
                    {isOnline && data.puryfi_version ? (
                        <StatusPill tone="neutral">v{data.puryfi_version}</StatusPill>
                    ) : null}
                    {liveStatus?.puryfi_enabled != null ? (
                        <StatusPill
                            tone={liveStatus.puryfi_enabled ? "online" : "neutral"}
                        >
                            {liveStatus.puryfi_enabled ? "Enabled" : "Disabled"}
                        </StatusPill>
                    ) : null}
                    {liveStatus?.puryfi_has_lock != null ? (
                        <StatusPill
                            tone={liveStatus.puryfi_has_lock ? "info" : "neutral"}
                        >
                            {liveStatus.puryfi_has_lock ? "Lock set" : "No lock"}
                        </StatusPill>
                    ) : null}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-slate-400">{description}</p>
                <PuryfiProfile
                    username={data.puryfi_username}
                    supportTier={data.puryfi_support_tier}
                    className="mt-2"
                />
            </div>
        </div>
    );
}

function EmptyConfiguration() {
    return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-white/[0.07] bg-[#17151F]/90 px-4 py-14 text-center shadow-xl shadow-black/20">
            <div className="flex size-11 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-slate-400">
                <Settings2 className="size-5" />
            </div>
            <div>
                <p className="text-sm font-semibold text-white">No configuration available</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-400">
                    This extension did not return any settings for this session.
                </p>
            </div>
        </div>
    );
}
