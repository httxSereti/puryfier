import { useId } from "react";
import { Eye, Info } from "lucide-react";

import ConfigurationSwitch from "@/components/common/configuration/ConfigurationSwitch";
import NumberInput from "@/components/ui/number-input";
import SectionCard from "@/components/ui/section-card";
import StatusPill from "@/components/ui/status-pill";
import { formatDuration, pluralize } from "@/lib/format";
import type { ChasterExtensionConfigSchema } from "@/types/api";

interface CensoredMediaOptionsProps {
    config: ChasterExtensionConfigSchema;
    onChange?: (updatedConfig: ChasterExtensionConfigSchema) => void;
    readOnly?: boolean;
}

export default function CensoredMediaOptions({
    config,
    onChange,
    readOnly = false,
}: CensoredMediaOptionsProps) {
    const thresholdId = useId();
    const durationId = useId();
    const { censorPicsConfig } = config;

    const handleToggle = (field: keyof ChasterExtensionConfigSchema["censorPicsConfig"]) => {
        if (readOnly || !onChange) return;

        onChange({
            ...config,
            censorPicsConfig: {
                ...censorPicsConfig,
                [field]: !censorPicsConfig[field],
            },
        });
    };

    const handleNumberChange = (field: "limit_count" | "added_duration", value: number) => {
        if (readOnly || !onChange) return;

        onChange({
            ...config,
            censorPicsConfig: {
                ...censorPicsConfig,
                [field]: value,
            },
        });
    };

    return (
        <SectionCard
            icon={<Eye />}
            title="Censored media"
            description="Penalise the lock when Puryfi censors media."
            accent="violet"
            action={readOnly ? <StatusPill tone="neutral">Read only</StatusPill> : null}
        >
            <div className="flex flex-col gap-4">
                <ConfigurationSwitch
                    icon={<Eye />}
                    title="Add time when media is censored"
                    description="Add time to the lock whenever Puryfi censors a picture."
                    checked={censorPicsConfig.enabled}
                    onChange={() => handleToggle("enabled")}
                    baseColor="violet"
                    disabled={readOnly}
                />

                {censorPicsConfig.enabled ? (
                    readOnly ? (
                        <div className="grid gap-3 sm:grid-cols-2">
                            <ReadOnlyStat
                                label="Threshold"
                                value={pluralize(censorPicsConfig.limit_count, "image")}
                            />
                            <ReadOnlyStat
                                label="Time added"
                                value={formatDuration(censorPicsConfig.added_duration)}
                            />
                        </div>
                    ) : (
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="grid gap-4 sm:grid-cols-2">
                                <div className="space-y-2">
                                    <label
                                        htmlFor={thresholdId}
                                        className="block text-xs font-medium text-slate-300"
                                    >
                                        Censored media threshold
                                    </label>
                                    <NumberInput
                                        id={thresholdId}
                                        value={censorPicsConfig.limit_count}
                                        onChange={(value) => handleNumberChange("limit_count", value)}
                                        min={1}
                                        suffix="images"
                                    />
                                    <p className="text-[11px] leading-relaxed text-slate-500">
                                        Apply the penalty after this many censored media.
                                    </p>
                                </div>

                                <div className="space-y-2">
                                    <label
                                        htmlFor={durationId}
                                        className="block text-xs font-medium text-slate-300"
                                    >
                                        Time added
                                    </label>
                                    <NumberInput
                                        id={durationId}
                                        value={censorPicsConfig.added_duration}
                                        onChange={(value) => handleNumberChange("added_duration", value)}
                                        min={1}
                                        suffix="seconds"
                                    />
                                    <p className="text-[11px] leading-relaxed text-slate-500">
                                        Equals {formatDuration(censorPicsConfig.added_duration)} per threshold.
                                    </p>
                                </div>
                            </div>

                            <div className="mt-4 flex items-start gap-2 rounded-lg border border-violet-400/10 bg-violet-400/[0.06] px-3 py-2.5">
                                <Info className="mt-0.5 size-3.5 shrink-0 text-violet-300" />
                                <p className="text-[11px] leading-relaxed text-violet-100/70">
                                    Adds {formatDuration(censorPicsConfig.added_duration)} to the lock every{" "}
                                    {pluralize(censorPicsConfig.limit_count, "censored image")}.
                                </p>
                            </div>
                        </div>
                    )
                ) : (
                    <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-4 py-3">
                        <p className="text-xs leading-relaxed text-slate-500">
                            Enable this option to set a censored media threshold and time penalty.
                        </p>
                    </div>
                )}
            </div>
        </SectionCard>
    );
}

function ReadOnlyStat({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">{label}</p>
            <p className="mt-1 text-sm font-semibold text-slate-200">{value}</p>
        </div>
    );
}
