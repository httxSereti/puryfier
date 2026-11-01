import { ShieldCheck, Users } from "lucide-react";

import ConfigurationSwitch from "@/components/common/configuration/ConfigurationSwitch";
import SectionCard from "@/components/ui/section-card";
import StatusPill from "@/components/ui/status-pill";
import type { ChasterExtensionConfigSchema } from "@/types/api";

interface AutomationPermissionsCardProps {
    config: ChasterExtensionConfigSchema;
    readOnly?: boolean;
    selfLock?: boolean;
    onChange?: (config: ChasterExtensionConfigSchema) => void;
}

export default function AutomationPermissionsCard({
    config,
    readOnly = false,
    selfLock = false,
    onChange,
}: AutomationPermissionsCardProps) {
    const enabled = config.automation_permissions.wearer_can_manage || selfLock;

    const handleToggle = () => {
        if (readOnly || !onChange || selfLock) return;
        onChange({
            ...config,
            automation_permissions: {
                ...config.automation_permissions,
                wearer_can_manage: !config.automation_permissions.wearer_can_manage,
            },
        });
    };

    return (
        <SectionCard
            icon={<ShieldCheck />}
            title="Automation permissions"
            description="Choose who can create rules for this lock."
            accent="amber"
            action={readOnly ? <StatusPill tone="neutral">Read only</StatusPill> : null}
        >
            <ConfigurationSwitch
                icon={<Users />}
                title="Wearer can manage automations"
                description={
                    selfLock
                        ? "Self-locks always allow the wearer to manage their own rules."
                        : "The keyholder can always manage automations. Enable this to let the wearer create their own rules."
                }
                checked={enabled}
                onChange={handleToggle}
                baseColor="violet"
                disabled={readOnly || selfLock}
            />
            {selfLock ? (
                <p className="mt-2 px-1 text-[11px] text-slate-500">
                    This lock has no keyholder, so the wearer is the only automation manager.
                </p>
            ) : readOnly ? (
                <p className="mt-2 px-1 text-[11px] text-slate-500">
                    Only the keyholder can change this setting.
                </p>
            ) : null}
        </SectionCard>
    );
}
