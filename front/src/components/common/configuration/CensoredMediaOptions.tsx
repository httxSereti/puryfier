import { Snowflake } from "lucide-react";
import type { ChasterExtensionConfigSchema } from "@/types/chaster";
import ConfigurationSwitch from "@/components/common/configuration/ConfigurationSwitch";
import { Input } from "@/components/ui/input";

interface CensoredMediaOptionsProps {
    config: ChasterExtensionConfigSchema;
    onChange: (updatedConfig: ChasterExtensionConfigSchema) => void;
}

export default function CensoredMediaOptions({ config, onChange }: CensoredMediaOptionsProps) {
    const handleToggle = (field: keyof ChasterExtensionConfigSchema["censorPicsConfig"]) => {
        onChange({
            ...config,
            censorPicsConfig: {
                ...config.censorPicsConfig,
                [field]: !config.censorPicsConfig[field],
            }
        });
    };

    return (
        <div className="flex flex-col gap-4 mt-4 w-full border-t border-slate-800 pt-4">
            <h6 className="text-xs font-mono tracking-tight text-gray-500">
                Censored media
            </h6>

            <div className="flex flex-col gap-4 w-full">
                <ConfigurationSwitch
                    icon={<Snowflake className="w-5 h-5 text-cyan-400" />}
                    title="Add time when a media is censored"
                    description="Add time to the lock when a media is censored by Puryfi"
                    checked={config.censorPicsConfig.enabled}
                    onChange={() => handleToggle("enabled")}
                    baseColor="cyan"
                />


                <div className="flex flex-col sm:flex-row gap-4 mt-2 px-1">
                    <div className="flex-1 space-y-1">
                        <label className="text-xs font-medium text-slate-400 ml-1">
                            Every X censored image(s) add time
                        </label>
                        <Input
                            type="number"
                            value={config.censorPicsConfig.limit_count}
                            onChange={(e) => {
                                const value = e.target.value;
                                if (!value) return;
                                onChange({
                                    ...config,
                                    censorPicsConfig: {
                                        ...config.censorPicsConfig,
                                        limit_count: Number(value),
                                    }
                                });
                            }}
                            className="bg-slate-900/50 text-white border-slate-800 focus-visible:ring-cyan-500/50"
                        />
                    </div>
                    <div className="flex-1 space-y-1">
                        <label className="text-xs font-medium text-slate-400 ml-1">
                            Duration to add (seconds)
                        </label>
                        <Input
                            type="number"
                            value={config.censorPicsConfig.added_duration}
                            onChange={(e) => {
                                const value = e.target.value;
                                if (!value) return;
                                onChange({
                                    ...config,
                                    censorPicsConfig: {
                                        ...config.censorPicsConfig,
                                        added_duration: Number(value),
                                    }
                                });
                            }}
                            className="bg-slate-900/50 text-white border-slate-800 focus-visible:ring-cyan-500/50"
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}
