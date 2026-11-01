import { Gamepad2, LockKeyhole } from "lucide-react";

import ConfigurationSwitch from "@/components/common/configuration/ConfigurationSwitch";
import SectionCard from "@/components/ui/section-card";
import StatusPill from "@/components/ui/status-pill";
import type { ChasterExtensionConfigSchema } from "@/types/api";

interface PuryfiControlPermissionCardProps {
    config: ChasterExtensionConfigSchema;
    role: string;
    hasSession: boolean;
    selfLock?: boolean;
    onChange?: (config: ChasterExtensionConfigSchema) => void;
}

export default function PuryfiControlPermissionCard({
    config,
    role,
    hasSession,
    selfLock = false,
    onChange,
}: PuryfiControlPermissionCardProps) {
    const isWearer = role === "wearer";
    const defaultEnabled = selfLock || (!hasSession && isWearer);
    const enabled = config.puryfi_permissions.wearer_can_control ?? defaultEnabled;

    // A self-lock freezes its choice once the session exists. In a shared
    // lock, only the keyholder may change the wearer's permission.
    const readOnly = hasSession && (selfLock || role !== "keyholder");

    const handleToggle = () => {
        if (readOnly || !onChange) return;
        onChange({
            ...config,
            puryfi_permissions: {
                ...config.puryfi_permissions,
                wearer_can_control: !enabled,
            },
        });
    };

    const description = readOnly
        ? selfLock
            ? enabled
                ? "Control is allowed for this lock, but the choice is frozen until the lock ends."
                : "Control is disabled for this lock, and the choice is frozen until the lock ends."
            : "Only the keyholder can change this setting while the lock is running."
        : hasSession
            ? "The keyholder can always control Puryfi. Enable this to let the wearer control it too."
            : isWearer
                ? "Choose whether you can control Puryfi during this lock. The choice is locked once the lock starts."
                : "Choose whether the wearer can control Puryfi during this lock. The choice is locked once the lock starts.";

    return (
        <SectionCard
            icon={<Gamepad2 />}
            title="Puryfi control"
            description="Choose who can enable, disable, lock or unlock Puryfi for this lock."
            accent="cyan"
            action={readOnly ? <StatusPill tone="neutral">Read only</StatusPill> : null}
        >
            <ConfigurationSwitch
                icon={<LockKeyhole />}
                title="Wearer can control Puryfi"
                description={description}
                checked={enabled}
                onChange={handleToggle}
                baseColor="cyan"
                disabled={readOnly || !onChange}
            />
        </SectionCard>
    );
}
