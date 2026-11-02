import {
    Archive,
    ArrowRight,
    CalendarClock,
    Clock3,
    Copy,
    Eye,
    LockKeyhole,
    Pencil,
    Power,
    PowerOff,
    Trash2,
    UserRound,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/ui/status-pill";
import {
    LABEL_IMAGES,
    actionName,
    actionSummary,
    automationSource,
    conditionLabel,
    eventName,
    triggerLabels,
} from "@/lib/automations";
import type { AutomationSource } from "@/lib/automations";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AutomationSchema, AutomationTriggerSchema } from "@/types/api";

const SOURCE_META = {
    puryfi: {
        label: "PuryFi",
        Icon: Eye,
        badge: "border-cyan-400/25 bg-cyan-400/10 text-cyan-200",
        icon: "text-cyan-300",
        tile: "border-cyan-400/20 bg-cyan-400/10 text-cyan-300",
    },
    chaster: {
        label: "Chaster",
        Icon: LockKeyhole,
        badge: "border-violet-400/25 bg-violet-400/10 text-violet-200",
        icon: "text-violet-300",
        tile: "border-violet-400/20 bg-violet-400/10 text-violet-300",
    },
} as const;

function SourceIcon({
    source,
    className,
}: {
    source: AutomationSource;
    className?: string;
}) {
    const Icon = SOURCE_META[source].Icon;
    return <Icon aria-hidden="true" className={cn(SOURCE_META[source].icon, className)} />;
}

function SourceBadge({ source }: { source: AutomationSource }) {
    return (
        <span
            className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.08em]",
                SOURCE_META[source].badge,
            )}
        >
            <SourceIcon source={source} className="size-2.5" />
            {SOURCE_META[source].label}
        </span>
    );
}

function triggerDetails(
    trigger: AutomationTriggerSchema,
    labelNames: Record<string, string>,
): string[] {
    const details = (trigger.conditions ?? []).map((condition) =>
        conditionLabel(condition, labelNames),
    );
    if (trigger.event === "puryfi.media.scan" && trigger.count > 1) {
        details.push(
            `${trigger.count} matching ${trigger.count === 1 ? "image" : "images"}`,
        );
    }
    return details;
}

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

    const triggerSource = automationSource(automation.trigger.event);
    const details = triggerDetails(automation.trigger, labelNames);
    const labels = triggerLabels(automation.trigger);
    const cooldown = automation.limits.cooldown_seconds;
    const maxPerDay = automation.limits.max_per_day;

    const hasActions = Boolean(
        (automation.can_edit && onEdit) ||
            (automation.is_owner && onDuplicate) ||
            (automation.can_delete && onDelete),
    );
    const hasLimits = cooldown > 0 || maxPerDay > 0;
    const showToggle = !archived && automation.can_disable && Boolean(onToggle);

    return (
        <article
            className={cn(
                "group relative overflow-hidden rounded-2xl border transition-colors",
                archived
                    ? "border-white/[0.06] bg-white/[0.015]"
                    : automation.enabled
                        ? "border-emerald-400/[0.14] bg-[#17151F]/80 hover:border-emerald-400/25"
                        : "border-white/[0.06] bg-black/20 hover:border-white/10",
            )}
        >
            <span
                aria-hidden="true"
                className={cn(
                    "absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent to-transparent",
                    archived
                        ? "via-white/10"
                        : automation.enabled
                            ? "via-emerald-400/60"
                            : disabledByKeyholder
                                ? "via-amber-400/50"
                                : "via-slate-500/40",
                )}
            />

            <div className="p-3.5 sm:p-4">
                <div className="flex items-start gap-3">
                    <div
                        className={cn(
                            "flex size-10 shrink-0 items-center justify-center rounded-xl border [&>svg]:size-4",
                            archived
                                ? "border-white/10 bg-white/[0.03] text-slate-500"
                                : automation.enabled
                                    ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-300"
                                    : disabledByKeyholder
                                        ? "border-amber-400/20 bg-amber-400/10 text-amber-300"
                                        : "border-white/10 bg-white/[0.03] text-slate-500",
                        )}
                    >
                        {archived ? (
                            <Archive />
                        ) : automation.enabled ? (
                            <Power />
                        ) : (
                            <PowerOff />
                        )}
                    </div>

                    <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                            <h3
                                className="min-w-0 truncate text-sm font-semibold text-white"
                                title={automation.name}
                            >
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
                                <StatusPill tone="warning">
                                    Disabled by keyholder
                                </StatusPill>
                            ) : null}
                        </div>

                        <div className="mt-1.5 flex flex-wrap items-center gap-2">
                            <StatusPill
                                tone={
                                    automation.owner_role === "keyholder"
                                        ? "keyholder"
                                        : "wearer"
                                }
                            >
                                <UserRound className="size-3" />
                                {automation.owner_role}
                            </StatusPill>
                            {automation.is_owner ? (
                                <span className="text-[10px] font-medium uppercase tracking-[0.08em] text-slate-500">
                                    Created by you
                                </span>
                            ) : null}
                        </div>
                    </div>

                    {showToggle ? (
                        <button
                            type="button"
                            role="switch"
                            aria-checked={automation.enabled}
                            aria-label={`${automation.enabled ? "Disable" : "Enable"} ${automation.name}`}
                            disabled={busy}
                            onClick={() => onToggle?.(automation)}
                            className={cn(
                                "relative mt-0.5 inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[#17151F] disabled:cursor-not-allowed disabled:opacity-50",
                                automation.enabled
                                    ? "bg-emerald-500"
                                    : "bg-slate-700/80",
                            )}
                        >
                            <span
                                aria-hidden="true"
                                className={cn(
                                    "pointer-events-none block size-5 rounded-full bg-white shadow-md transition-transform",
                                    automation.enabled
                                        ? "translate-x-5"
                                        : "translate-x-0",
                                )}
                            />
                        </button>
                    ) : null}
                </div>

                <div className="mt-4 grid gap-2 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:items-stretch">
                    <div className="rounded-xl border border-white/[0.06] bg-black/15 px-3 py-2.5">
                        <div className="flex items-center justify-between gap-2">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500">
                                When
                            </p>
                            {triggerSource ? (
                                <SourceBadge source={triggerSource} />
                            ) : null}
                        </div>

                        <div className="mt-2 flex items-start gap-2">
                            {triggerSource ? (
                                <span
                                    className={cn(
                                        "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-lg border [&>svg]:size-3",
                                        SOURCE_META[triggerSource].tile,
                                    )}
                                >
                                    <SourceIcon source={triggerSource} />
                                </span>
                            ) : null}
                            <div className="min-w-0">
                                <p className="text-xs font-medium leading-snug text-slate-100">
                                    {eventName(automation.trigger.event)}
                                </p>
                                {details.length > 0 ? (
                                    <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                                        {details.join(", ")}
                                    </p>
                                ) : null}
                            </div>
                        </div>

                        {labels.length > 0 ? (
                            <div className="mt-2 flex flex-wrap items-center gap-1.5">
                                {labels.map((value) => (
                                    <span
                                        key={value}
                                        className="inline-flex items-center gap-1 rounded-md border border-white/[0.07] bg-white/[0.025] py-0.5 pl-0.5 pr-1.5 text-[10px] text-slate-300"
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
                    </div>

                    <div className="flex items-center justify-center">
                        <span className="flex size-6 items-center justify-center rounded-full border border-white/[0.07] bg-white/[0.025] text-slate-500">
                            <ArrowRight
                                aria-hidden="true"
                                className="size-3 rotate-90 md:rotate-0"
                            />
                        </span>
                    </div>

                    <div className="rounded-xl border border-white/[0.06] bg-black/15 px-3 py-2.5">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500">
                            Then
                        </p>

                        {automation.actions.length > 0 ? (
                            <ul className="mt-2 flex flex-col gap-1.5">
                                {automation.actions.map((action, index) => {
                                    const source = automationSource(action.type);
                                    return (
                                        <li
                                            key={`${action.type}-${index}`}
                                            className="flex items-start gap-2"
                                        >
                                            <span
                                                className={cn(
                                                    "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-lg border [&>svg]:size-3",
                                                    source
                                                        ? SOURCE_META[source].tile
                                                        : "border-white/10 bg-white/[0.03] text-slate-400",
                                                )}
                                            >
                                                {source ? (
                                                    <SourceIcon source={source} />
                                                ) : (
                                                    <Power />
                                                )}
                                            </span>
                                            <div className="min-w-0">
                                                <p className="text-xs font-medium leading-snug text-slate-200">
                                                    {actionName(action.type)}
                                                </p>
                                                <p
                                                    className="mt-0.5 text-[10px] leading-relaxed text-slate-500"
                                                    title={actionSummary(action)}
                                                >
                                                    {actionSummary(action)}
                                                </p>
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        ) : (
                            <p className="mt-2 text-[11px] text-slate-500">
                                No actions configured.
                            </p>
                        )}
                    </div>
                </div>

                {hasActions || hasLimits ? (
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.05] pt-3">
                        <div className="flex flex-wrap items-center gap-1.5">
                            {cooldown > 0 ? (
                                <span className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1 text-[10px] text-slate-400">
                                    <Clock3
                                        aria-hidden="true"
                                        className="size-3 text-slate-500"
                                    />
                                    {formatDuration(cooldown)} cooldown
                                </span>
                            ) : null}
                            {maxPerDay > 0 ? (
                                <span className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1 text-[10px] text-slate-400">
                                    <CalendarClock
                                        aria-hidden="true"
                                        className="size-3 text-slate-500"
                                    />
                                    {maxPerDay}× per day
                                </span>
                            ) : null}
                        </div>

                        <div className="flex flex-wrap items-center gap-1">
                            {automation.can_edit && onEdit ? (
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    disabled={busy}
                                    onClick={() => onEdit(automation)}
                                    className="h-8 gap-1.5 rounded-lg px-2.5 text-[11px] text-slate-400 hover:bg-white/[0.06] hover:text-white"
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
                                    className="h-8 gap-1.5 rounded-lg px-2.5 text-[11px] text-slate-400 hover:bg-white/[0.06] hover:text-white"
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
                                    className="h-8 gap-1.5 rounded-lg px-2.5 text-[11px] text-slate-400 hover:bg-rose-400/10 hover:text-rose-300"
                                >
                                    <Trash2 />
                                    Delete
                                </Button>
                            ) : null}
                        </div>
                    </div>
                ) : null}
            </div>
        </article>
    );
}
