import { useState } from "react";
import { Check, Settings2, ShieldCheck } from "lucide-react";

import AutomationPermissionsCard from "@/components/common/automations/AutomationPermissionsCard";
import PuryfiControlPermissionCard from "@/components/common/configuration/PuryfiControlPermissionCard";
import ErrorAlert from "@/components/ui/error-alert";
import StatusPill from "@/components/ui/status-pill";
import { Button } from "@/components/ui/button";
import { getApiErrorMessage } from "@/lib/errors";
import { updateSessionPermissions } from "@/lib/http/session";
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

    const canSave = session.role === "keyholder" && !session.is_self_lock;
    const isDirty =
        draft.automation_permissions.wearer_can_manage !==
            config.automation_permissions.wearer_can_manage ||
        draft.puryfi_permissions.wearer_can_control !==
            config.puryfi_permissions.wearer_can_control;

    const handleSave = async () => {
        if (!canSave || !isDirty || isSaving) return;

        setIsSaving(true);
        setError(null);
        try {
            const saved = await updateSessionPermissions(mainToken, {
                automation_permissions: draft.automation_permissions,
                puryfi_permissions: draft.puryfi_permissions,
            });
            setDraft(saved);
            onSaved(saved);
        } catch (cause) {
            setError(
                getApiErrorMessage(cause, "Could not save the permissions. Please try again."),
            );
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div className="flex flex-col gap-4">
            <div className="flex items-start gap-2 px-1">
                <Settings2 className="mt-0.5 size-3.5 shrink-0 text-slate-500" />
                <p className="text-xs leading-relaxed text-slate-400">
                    Permissions for this lock. Legacy freeze and media settings are managed from
                    the extension configuration page.
                </p>
            </div>

            {error ? <ErrorAlert message={error} /> : null}

            <PuryfiControlPermissionCard
                config={draft}
                role={session.role}
                hasSession
                selfLock={session.is_self_lock}
                onChange={setDraft}
            />

            <AutomationPermissionsCard
                config={draft}
                readOnly={session.role !== "keyholder" && !session.is_self_lock}
                selfLock={session.is_self_lock}
                onChange={setDraft}
            />

            {canSave ? (
                <footer className="flex flex-col gap-2 px-1 pt-1 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                    <span className="inline-flex items-center gap-1.5">
                        <ShieldCheck className="size-3.5" />
                        Changes are applied to the running session immediately.
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
                            <ShieldCheck />
                            {isSaving ? "Saving…" : "Save permissions"}
                        </Button>
                    </div>
                </footer>
            ) : (
                <p className="px-1 text-[11px] text-slate-500">
                    {session.is_self_lock
                        ? "These permissions are fixed for the duration of the lock."
                        : "Only the keyholder can change these permissions while the lock is running."}
                </p>
            )}
        </div>
    );
}
