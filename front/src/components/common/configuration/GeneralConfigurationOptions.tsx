import { SlidersHorizontal, Snowflake, Unlock } from "lucide-react";

import ConfigurationSwitch from "@/components/common/configuration/ConfigurationSwitch";
import SectionCard from "@/components/ui/section-card";
import StatusPill from "@/components/ui/status-pill";
import type { ChasterExtensionConfigSchema } from "@/types/chaster";

interface GeneralConfigurationOptionsProps {
    config: ChasterExtensionConfigSchema;
    onChange?: (updatedConfig: ChasterExtensionConfigSchema) => void;
    readOnly?: boolean;
}

export default function GeneralConfigurationOptions({
    config,
    onChange,
    readOnly = false,
}: GeneralConfigurationOptionsProps) {
    const handleToggle = (field: "lock_on_freeze" | "unlock_on_unfreeze") => {
        if (readOnly || !onChange) return;

        onChange({
            ...config,
            [field]: !config[field],
        });
    };

    return (
        <SectionCard
            icon={<SlidersHorizontal />}
            title="General"
            description="Automation tied to Chaster lock events."
            accent="cyan"
            action={readOnly ? <StatusPill tone="neutral">Read only</StatusPill> : null}
        >
            <div className="flex flex-col gap-3">
                <ConfigurationSwitch
                    icon={<Snowflake />}
                    title="Lock on freeze"
                    description="Automatically lock Puryfi when the Chaster lock is frozen."
                    checked={config.lock_on_freeze}
                    onChange={() => handleToggle("lock_on_freeze")}
                    baseColor="cyan"
                    disabled={readOnly}
                />

                <ConfigurationSwitch
                    icon={<Unlock />}
                    title="Unlock on unfreeze"
                    description="Automatically unlock Puryfi when the Chaster lock is unfrozen."
                    checked={config.unlock_on_unfreeze}
                    onChange={() => handleToggle("unlock_on_unfreeze")}
                    baseColor="emerald"
                    disabled={readOnly}
                />
            </div>
        </SectionCard>
    );
}
