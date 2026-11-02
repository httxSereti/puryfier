import {
    Check,
    CheckCircle2,
    Clock3,
    Cog,
    Eye,
    LockKeyhole,
    TriangleAlert,
    X,
    XCircle,
} from "lucide-react";

import StatusPill from "@/components/ui/status-pill";
import {
    actionName,
    automationSource,
    eventName,
} from "@/lib/automations";
import type { AutomationSource } from "@/lib/automations";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AutomationExecutionSchema } from "@/types/api";

interface ExecutionAction {
    type: string;
    status: string;
    error: string | null;
}

const STATUS_META = {
    success: {
        label: "Success",
        tone: "online",
        Icon: CheckCircle2,
        tile: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
    },
    partial: {
        label: "Partial",
        tone: "warning",
        Icon: TriangleAlert,
        tile: "border-amber-400/20 bg-amber-400/10 text-amber-300",
    },
    failed: {
        label: "Failed",
        tone: "offline",
        Icon: XCircle,
        tile: "border-rose-400/20 bg-rose-400/10 text-rose-300",
    },
    running: {
        label: "Running",
        tone: "info",
        Icon: Clock3,
        tile: "border-cyan-400/20 bg-cyan-400/10 text-cyan-300",
    },
    unknown: {
        label: "Unknown",
        tone: "neutral",
        Icon: Clock3,
        tile: "border-white/10 bg-white/[0.04] text-slate-400",
    },
} as const;

const SOURCE_META = {
    puryfi: {
        label: "PuryFi",
        Icon: Eye,
        badge: "border-cyan-400/25 bg-cyan-400/10 text-cyan-200",
        icon: "text-cyan-300",
    },
    chaster: {
        label: "Chaster",
        Icon: LockKeyhole,
        badge: "border-violet-400/25 bg-violet-400/10 text-violet-200",
        icon: "text-violet-300",
    },
} as const;

function statusMeta(status: string) {
    return (
        STATUS_META[status as keyof typeof STATUS_META] ?? STATUS_META.unknown
    );
}

function SourceIcon({
    source,
    className,
}: {
    source: AutomationSource;
    className?: string;
}) {
    const Icon = SOURCE_META[source].Icon;
    return (
        <Icon
            aria-hidden="true"
            className={cn(SOURCE_META[source].icon, className)}
        />
    );
}

function SourceBadge({ source }: { source: AutomationSource }) {
    return (
        <span
            className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]",
                SOURCE_META[source].badge,
            )}
        >
            <SourceIcon source={source} className="size-3" />
            {SOURCE_META[source].label}
        </span>
    );
}

function ExecutionActionBadge({ action }: { action: ExecutionAction }) {
    const source = automationSource(action.type);
    const failed = action.status === "failed";
    const success = action.status === "success";
    const StatusIcon = success ? Check : failed ? X : Clock3;

    return (
        <span
            title={action.error ?? undefined}
            aria-label={`${actionName(action.type)}: ${action.status}${
                action.error ? ` — ${action.error}` : ""
            }`}
            className={cn(
                "inline-flex items-center gap-1.5 rounded-md border px-1.5 py-1 text-[10px] leading-none",
                failed
                    ? "border-rose-400/25 bg-rose-400/[0.07] text-rose-200"
                    : success
                        ? "border-white/[0.07] bg-white/[0.025] text-slate-300"
                        : "border-amber-400/20 bg-amber-400/[0.06] text-amber-200",
            )}
        >
            {source ? (
                <SourceIcon source={source} className="size-3 shrink-0" />
            ) : (
                <Cog
                    aria-hidden="true"
                    className="size-3 shrink-0 text-slate-500"
                />
            )}
            <span>{actionName(action.type)}</span>
            <StatusIcon
                aria-hidden="true"
                className={cn(
                    "size-3 shrink-0",
                    success
                        ? "text-emerald-400"
                        : failed
                            ? "text-rose-400"
                            : "text-amber-400",
                )}
            />
        </span>
    );
}

function formatTime(value: string | null | undefined): string {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function formatFullTime(value: string | null | undefined): string | undefined {
    if (!value) return undefined;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return undefined;
    return date.toLocaleString();
}

function formatElapsed(
    startedAt: string | null | undefined,
    finishedAt: string | null | undefined,
): string | null {
    if (!startedAt || !finishedAt) return null;
    const started = Date.parse(startedAt);
    const finished = Date.parse(finishedAt);
    if (!Number.isFinite(started) || !Number.isFinite(finished)) return null;

    const elapsed = Math.max(0, finished - started);
    if (elapsed < 1_000) return `${elapsed} ms`;
    if (elapsed < 10_000) return `${(elapsed / 1_000).toFixed(1)} s`;
    return formatDuration(Math.round(elapsed / 1_000));
}

function executionActions(
    execution: AutomationExecutionSchema,
): ExecutionAction[] {
    return (execution.actions ?? []).flatMap((action) => {
        if (typeof action.type !== "string") return [];
        return [
            {
                type: action.type,
                status:
                    typeof action.status === "string"
                        ? action.status
                        : "unknown",
                error:
                    typeof action.error === "string" ? action.error : null,
            },
        ];
    });
}

export default function AutomationActivity({
    executions,
}: {
    executions: AutomationExecutionSchema[];
}) {
    if (executions.length === 0) {
        return (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-4 py-6 text-center">
                <div className="flex size-9 items-center justify-center rounded-full border border-white/10 bg-white/[0.03] text-slate-500">
                    <Clock3 className="size-4" />
                </div>
                <div>
                    <p className="text-xs font-medium text-slate-300">
                        No runs yet
                    </p>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                        Automation results will appear here after the next
                        trigger.
                    </p>
                </div>
            </div>
        );
    }

    return (
        <ul
            aria-label="Recent automation activity"
            className="flex flex-col gap-2"
        >
            {executions.map((execution) => {
                const status = statusMeta(execution.status);
                const source = automationSource(execution.event_type);
                const actions = executionActions(execution);
                const elapsed = formatElapsed(
                    execution.started_at,
                    execution.finished_at,
                );
                const startedAt = formatTime(execution.started_at);
                const fullStartedAt = formatFullTime(execution.started_at);

                return (
                    <li
                        key={execution.id}
                        className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-3 transition-colors hover:border-white/10 hover:bg-white/[0.03]"
                    >
                        <div className="flex items-start gap-3">
                            <div
                                className={cn(
                                    "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border [&>svg]:size-4",
                                    status.tile,
                                )}
                            >
                                <status.Icon aria-hidden="true" />
                            </div>

                            <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                    <p className="min-w-0 flex-1 truncate text-xs font-semibold text-slate-100">
                                        {execution.automation_name ??
                                            "Automation"}
                                    </p>
                                    <StatusPill tone={status.tone}>
                                        {status.label}
                                    </StatusPill>
                                </div>

                                <div className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[10px] text-slate-500">
                                    {source ? (
                                        <SourceBadge source={source} />
                                    ) : null}
                                    <span className="text-slate-400">
                                        {eventName(execution.event_type)}
                                    </span>
                                    {startedAt ? (
                                        <>
                                            <span aria-hidden="true">·</span>
                                            <time
                                                dateTime={
                                                    execution.started_at ??
                                                    undefined
                                                }
                                                title={fullStartedAt}
                                            >
                                                {startedAt}
                                            </time>
                                        </>
                                    ) : null}
                                    {elapsed ? (
                                        <>
                                            <span aria-hidden="true">·</span>
                                            <span title="Execution duration">
                                                {elapsed}
                                            </span>
                                        </>
                                    ) : null}
                                </div>

                                {actions.length > 0 ? (
                                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                                        {actions.map((action, index) => (
                                            <ExecutionActionBadge
                                                key={`${action.type}-${index}`}
                                                action={action}
                                            />
                                        ))}
                                    </div>
                                ) : (
                                    <p className="mt-2 text-[10px] text-slate-500">
                                        No action recorded.
                                    </p>
                                )}

                                {execution.error ? (
                                    <p className="mt-2 flex items-start gap-1.5 rounded-lg border border-rose-400/15 bg-rose-400/[0.06] px-2.5 py-2 text-[10px] leading-relaxed text-rose-200">
                                        <TriangleAlert
                                            aria-hidden="true"
                                            className="mt-0.5 size-3 shrink-0"
                                        />
                                        <span className="min-w-0 break-words">
                                            {execution.error}
                                        </span>
                                    </p>
                                ) : null}
                            </div>
                        </div>
                    </li>
                );
            })}
        </ul>
    );
}
