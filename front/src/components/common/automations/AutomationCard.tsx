import {
    Archive,
    Copy,
    Pencil,
    Power,
    Trash2,
    UserRound,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/ui/status-pill";
import {
    LABEL_IMAGES,
    automationActionsSummary,
    triggerLabels,
    triggerSummary,
} from "@/lib/automations";
import { cn } from "@/lib/utils";
import type { AutomationSchema } from "@/types/api";

interface AutomationCardProps {
    automation: AutomationSchema;
    labelNames: Record<string, string>;
    busy?: boolean;
    onToggle?: (automation: AutomationSchema) => void;
    onEdit?: (automation: AutomationSchema) => void;
    onDuplicate?: (automation: AutomationSchema) => void;
    onDelete?: (automation: AutomationSchema) => void;
}

export default function AutomationCard({
    automation,
    labelNames,
    busy = false,
    onToggle,
    onEdit,
    onDuplicate,
    onDelete,
}: AutomationCardProps) {
    const archived = automation.status === "archived";
    const disabledByKeyholder =
        automation.disabled_by_role === "keyholder" && !automation.enabled;

    return (
        <article
            className={cn(
                "rounded-xl border p-4 transition-colors",
                archived
                    ? "border-white/[0.06] bg-white/[0.015] opacity-80"
                    : automation.enabled
                        ? "border-white/[0.08] bg-white/[0.025]"
                        : "border-white/[0.05] bg-black/10",
            )}
        >
            <div className="flex items-start gap-3">
                <div
                    className={cn(
                        "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl border [&>svg]:size-4",
                        archived
                            ? "border-white/10 bg-white/[0.03] text-slate-500"
                            : automation.enabled
                                ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-300"
                                : "border-white/10 bg-white/[0.03] text-slate-500",
                    )}
                >
                    {archived ? <Archive /> : <Power />}
                </div>

                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold text-white">
                            {automation.name}
                        </h3>
                        {archived ? (
                            <StatusPill tone="neutral">Archived</StatusPill>
                        ) : automation.enabled ? (
                            <StatusPill tone="online" dot>
                                Active
                            </StatusPill>
                        ) : (
                            <StatusPill tone="neutral" dot>
                                Disabled
                            </StatusPill>
                        )}
                        {disabledByKeyholder ? (
                            <StatusPill tone="warning">Disabled by keyholder</StatusPill>
                        ) : null}
                        <StatusPill
                            tone={automation.owner_role === "keyholder" ? "keyholder" : "wearer"}
                        >
                            <UserRound className="size-3" />
                            {automation.owner_role}
                        </StatusPill>
                        {automation.is_owner ? (
                            <span className="text-[10px] font-medium uppercase tracking-[0.08em] text-slate-500">
                                created by you
                            </span>
                        ) : null}
                    </div>

                    <p className="mt-2 text-xs leading-relaxed text-slate-400">
                        <span className="font-medium text-slate-300">When</span>{" "}
                        {triggerSummary(automation.trigger, labelNames)}
                    </p>
                    {triggerLabels(automation.trigger).length > 0 ? (
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            {triggerLabels(automation.trigger).map((value) => (
                                <span
                                    key={value}
                                    className="inline-flex items-center gap-1 rounded-md border border-white/[0.06] bg-black/10 py-0.5 pl-0.5 pr-1.5 text-[10px] text-slate-400"
                                    title={labelNames[value] ?? value}
                                >
                                    {LABEL_IMAGES[value] ? (
                                        <img
                                            src={LABEL_IMAGES[value]}
                                            alt=""
                                            width={16}
                                            height={16}
                                            className="size-4 rounded object-contain"
                                            loading="lazy"
                                        />
                                    ) : null}
                                    {labelNames[value] ?? value}
                                </span>
                            ))}
                        </div>
                    ) : null}
                    <p className="mt-1 text-xs leading-relaxed text-slate-400">
                        <span className="font-medium text-slate-300">Then</span>{" "}
                        {automationActionsSummary(automation)}
                    </p>
                    {automation.limits.cooldown_seconds > 0 ? (
                        <p className="mt-1 text-[11px] text-slate-500">
                            Cooldown: {automation.limits.cooldown_seconds}s
                        </p>
                    ) : null}
                </div>

                {!archived && automation.can_disable ? (
                    <button
                        type="button"
                        role="switch"
                        aria-checked={automation.enabled}
                        aria-label={`${automation.enabled ? "Disable" : "Enable"} ${automation.name}`}
                        disabled={busy}
                        onClick={() => onToggle?.(automation)}
                        className={cn(
                            "relative mt-1 inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[#17151F] disabled:cursor-not-allowed disabled:opacity-50",
                            automation.enabled ? "bg-emerald-500" : "bg-slate-700/80",
                        )}
                    >
                        <span
                            aria-hidden="true"
                            className={cn(
                                "pointer-events-none block size-5 rounded-full bg-white shadow-md transition-transform",
                                automation.enabled ? "translate-x-5" : "translate-x-0",
                            )}
                        />
                    </button>
                ) : null}
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-white/[0.05] pt-3">
                {automation.can_edit && onEdit ? (
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() => onEdit(automation)}
                        className="h-8 text-xs text-slate-400 hover:text-white"
                    >
                        <Pencil />
                        Edit
                    </Button>
                ) : null}
                {automation.is_owner && onDuplicate ? (
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() => onDuplicate(automation)}
                        className="h-8 text-xs text-slate-400 hover:text-white"
                    >
                        <Copy />
                        Duplicate
                    </Button>
                ) : null}
                {automation.can_delete && onDelete ? (
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() => onDelete(automation)}
                        className="h-8 text-xs text-slate-400 hover:text-rose-300"
                    >
                        <Trash2 />
                        Delete
                    </Button>
                ) : null}
            </div>
        </article>
    );
}
