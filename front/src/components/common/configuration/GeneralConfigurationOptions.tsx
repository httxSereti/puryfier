import { Snowflake, Unlock } from "lucide-react";
import type { ChasterExtensionConfigSchema } from "@/types/chaster";
import ConfigurationSwitch from "@/components/common/configuration/ConfigurationSwitch";

interface GeneralConfigurationOptionsProps {
    config: ChasterExtensionConfigSchema;
    onChange: (updatedConfig: ChasterExtensionConfigSchema) => void;
}

export default function GeneralConfigurationOptions({ config, onChange }: GeneralConfigurationOptionsProps) {
    const handleToggle = (field: keyof ChasterExtensionConfigSchema) => {
        onChange({
            ...config,
            [field]: !config[field],
        });
    };

    return (
        <div className="flex flex-col gap-4 mt-4 w-full">
            <h6 className="text-xs font-mono tracking-tight text-gray-500">
                General
            </h6>

            <ConfigurationSwitch
                icon={<Snowflake className="w-5 h-5 text-cyan-400" />}
                title="Lock on Freeze"
                description="Automatically lock Puryfi when lock is frozen"
                checked={config.lock_on_freeze}
                onChange={() => handleToggle("lock_on_freeze")}
                baseColor="cyan"
            />

            <ConfigurationSwitch
                icon={<Unlock className="w-5 h-5 text-emerald-400" />}
                title="Unlock on Unfreeze"
                description="Automatically unlock Puryfi when unfreezing"
                checked={config.unlock_on_unfreeze}
                onChange={() => handleToggle("unlock_on_unfreeze")}
                baseColor="emerald"
            />
        </div>
    );
}
