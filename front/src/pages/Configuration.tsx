import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { Check, Link2, LockKeyhole, Settings2, ShieldCheck, Unplug } from "lucide-react";

import GeneralConfigurationOptions from "@/components/common/configuration/GeneralConfigurationOptions";
import CensoredMediaOptions from "@/components/common/configuration/CensoredMediaOptions";
import ConfigurationSkeleton from "@/components/common/configuration/ConfigurationSkeleton";
import PageHeader from "@/components/common/layout/PageHeader";
import PageShell from "@/components/common/layout/PageShell";
import ErrorAlert from "@/components/ui/error-alert";
import StatusPill from "@/components/ui/status-pill";
import { usePuryfiRealtimeStatus } from "@/hooks/usePuryfiRealtimeStatus";
import { getBackendUrl } from "@/lib/backend";
import { readChasterIframeParams } from "@/lib/chaster";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type {
    ChasterExtensionConfigSchema,
    ChasterExtensionConfigurationSchema,
} from "@/types/chaster";

const CHASTER_ORIGIN = "https://chaster.app";

function postToParent(event: string, payload?: object) {
    window.parent.postMessage(
        JSON.stringify({ type: "partner_configuration", event, ...(payload ? { payload } : {}) }),
        CHASTER_ORIGIN,
    );
}

export default function Configuration() {
    const [configurationData, setConfigurationData] = useState<ChasterExtensionConfigurationSchema | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isDirty, setIsDirty] = useState(false);

    // Keep a mutable ref to the latest config & token so the event listener always has fresh values
    const configRef = useRef<ChasterExtensionConfigurationSchema | null>(null);
    const tokenRef = useRef<string>("");
    const hasFetched = useRef(false);
    const { partnerConfigurationToken } = useMemo(() => readChasterIframeParams(), []);

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
        postToParent("capabilities", { features: { save: true } });
    }, []);

    useEffect(() => {
        // Don't fetch session twice (react strict mode re-renders the component on development)
        if (hasFetched.current) return;

        hasFetched.current = true;

        const fetchSession = async () => {
            try {
                if (!window.location.hash) {
                    throw new Error("No login token detected in URL.");
                }

                if (!partnerConfigurationToken) {
                    throw new Error("partnerConfigurationToken not found in parameters.");
                }

                tokenRef.current = partnerConfigurationToken;

                const backendUrl = getBackendUrl();
                const response = await axios.get(`${backendUrl}/api/configuration/${partnerConfigurationToken}`);
                setConfigurationData(response.data);
                configRef.current = response.data;
            } catch (err: unknown) {
                setError(getApiErrorMessage(err, "Error syncing with the local server."));
            } finally {
                setIsLoading(false);
            }
        };

        fetchSession();
    }, [partnerConfigurationToken]);

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

            // Show spinner on the Chaster modal
            postToParent("save_loading");
            setError(null);

            try {
                const backendUrl = getBackendUrl();

                await axios.put(
                    `${backendUrl}/api/configuration/${tokenRef.current}`,
                    configRef.current?.config ?? {},
                );

                setIsDirty(false);

                // Signal success — Chaster will close the modal
                postToParent("save_success");
            } catch (err: unknown) {
                // Stop spinner and keep modal open
                postToParent("save_failed");
                setError(getApiErrorMessage(err, "Save failed. Please try again."));
            }
        };

        window.addEventListener("message", handleMessage);
        return () => window.removeEventListener("message", handleMessage);
    }, []);

    const handleConfigChange = (updatedConfig: ChasterExtensionConfigSchema) => {
        const current = configRef.current;
        if (!current) return;

        const next = { ...current, config: updatedConfig };
        configRef.current = next;
        setConfigurationData(next);
        setIsDirty(true);
    };

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

            {error ? <ErrorAlert message={error} /> : null}

            {isLoading ? (
                <ConfigurationSkeleton />
            ) : liveConfigurationData ? (
                <>
                    <ConnectionStatus data={liveConfigurationData} />

                    {liveConfigurationData.config ? (
                        <div className="flex flex-col gap-5">
                            <GeneralConfigurationOptions
                                config={liveConfigurationData.config}
                                onChange={handleConfigChange}
                            />

                            <CensoredMediaOptions
                                config={liveConfigurationData.config}
                                onChange={handleConfigChange}
                            />
                        </div>
                    ) : (
                        <EmptyConfiguration />
                    )}

                    <footer className="flex flex-col gap-2 px-1 pt-1 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                        <span className="inline-flex items-center gap-1.5">
                            <ShieldCheck className="size-3.5" />
                            Changes are saved to Chaster when you confirm.
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

function ConnectionStatus({ data }: { data: ChasterExtensionConfigurationSchema }) {
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
                </div>
                <p className="mt-1 text-xs leading-relaxed text-slate-400">{description}</p>
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
