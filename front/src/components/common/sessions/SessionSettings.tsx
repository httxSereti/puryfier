import { useState } from "react";
import { Check, LockKeyhole, Save, ShieldCheck } from "lucide-react";

import AutomationPermissionsCard from "@/components/common/automations/AutomationPermissionsCard";
import CensoredMediaOptions from "@/components/common/configuration/CensoredMediaOptions";
import GeneralConfigurationOptions from "@/components/common/configuration/GeneralConfigurationOptions";
import ErrorAlert from "@/components/ui/error-alert";
import StatusPill from "@/components/ui/status-pill";
import { Button } from "@/components/ui/button";
import { getApiErrorMessage } from "@/lib/errors";
import { updateSessionConfiguration } from "@/lib/http/session";
import type {
    ChasterExtensionConfigSchema,
    ChasterExtensionSessionSchema,
} from "@/types/api";

interface SessionSettingsProps {
    session: ChasterExtensionSessionSchema;
    mainToken: string;
    onSaved: (config: ChasterExtensionConfigSchema) => void;
}

export default function SessionSettings({
    session,
    mainToken,
    onSaved,
}: SessionSettingsProps) {
    const config = session.config;
    const [draft, setDraft] = useState<ChasterExtensionConfigSchema | null>(config ?? null);
    const [error, setError] = useState<string | null>(null);
    const [isSaving, setIsSaving] = useState(false);

    if (!config || !draft) {
        return null;
    }

    const canManage = session.role === "keyholder" || session.is_self_lock;
    const canEditSettings = canManage && !session.automation_mode;
    const isDirty = JSON.stringify(draft) !== JSON.stringify(config);

    const handleChange = (updatedConfig: ChasterExtensionConfigSchema) => {
        setDraft(updatedConfig);
    };

    const handleSave = async () => {
        if (!canManage || !isDirty || isSaving) return;

        setIsSaving(true);
        setError(null);
        try {
            await updateSessionConfiguration(mainToken, draft);
            onSaved(draft);
        } catch (cause) {
            setError(
                getApiErrorMessage(cause, "Could not save the settings. Please try again."),
            );
        } finally {
            setIsSaving(false);
        }
    };

    const description = session.automation_mode
        ? "This lock runs automations. The legacy settings below are read-only and no longer applied."
        : canEditSettings
            ? "Change how Puryfier behaves for this lock. The new settings are applied as soon as you save."
            : "Only the keyholder can change these settings while the lock is running.";

    return (
        <div className="flex flex-col gap-4">
            <div className="flex items-start gap-2 px-1">
                <LockKeyhole className="mt-0.5 size-3.5 shrink-0 text-slate-500" />
                <p className="text-xs leading-relaxed text-slate-400">{description}</p>
            </div>

            {error ? <ErrorAlert message={error} /> : null}

            <AutomationPermissionsCard
                config={draft}
                readOnly={!canManage}
                selfLock={session.is_self_lock}
                onChange={handleChange}
            />

            <div className="grid gap-5 lg:grid-cols-2">
                <GeneralConfigurationOptions
                    config={draft}
                    onChange={handleChange}
                    readOnly={!canEditSettings}
                />
                <CensoredMediaOptions
                    config={draft}
                    onChange={handleChange}
                    readOnly={!canEditSettings}
                />
            </div>

            {canManage ? (
                <footer className="flex flex-col gap-2 px-1 pt-1 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                    <span className="inline-flex items-center gap-1.5">
                        <ShieldCheck className="size-3.5" />
                        Settings are stored on your Puryfier server and synced to Chaster.
                    </span>

                    <div className="flex items-center gap-3">
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

                        <Button
                            type="button"
                            onClick={handleSave}
                            disabled={!isDirty || isSaving}
                            className="bg-cyan-500 text-slate-950 hover:bg-cyan-400"
                        >
                            <Save />
                            {isSaving ? "Saving…" : "Save settings"}
                        </Button>
                    </div>
                </footer>
            ) : null}
        </div>
    );
}
