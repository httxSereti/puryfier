import { CheckCircle2, Clock3, XCircle } from "lucide-react";

import type { AutomationExecutionSchema } from "@/types/api";

function formatTime(value: string | null | undefined): string {
    if (!value) return "";
    try {
        return new Date(value).toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return value;
    }
}

export default function AutomationActivity({
    executions,
}: {
    executions: AutomationExecutionSchema[];
}) {
    if (executions.length === 0) {
        return (
            <p className="rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-4 py-5 text-center text-xs text-slate-500">
                No automation has run yet.
            </p>
        );
    }

    return (
        <ul className="flex flex-col gap-1.5">
            {executions.map((execution) => {
                const failed = execution.status === "failed" || execution.status === "partial";
                const Icon = execution.status === "success" ? CheckCircle2 : failed ? XCircle : Clock3;
                const actions = execution.actions ?? [];
                return (
                    <li
                        key={execution.id}
                        className="flex items-start gap-2.5 rounded-lg border border-white/[0.05] bg-black/10 px-3 py-2.5"
                    >
                        <Icon
                            className={
                                execution.status === "success"
                                    ? "mt-0.5 size-4 shrink-0 text-emerald-400"
                                    : failed
                                        ? "mt-0.5 size-4 shrink-0 text-rose-400"
                                        : "mt-0.5 size-4 shrink-0 text-amber-400"
                            }
                        />
                        <div className="min-w-0 flex-1">
                            <p className="text-xs text-slate-300">
                                <span className="font-medium text-slate-200">
                                    {execution.automation_name ?? "Automation"}
                                </span>{" "}
                                ran
                                {actions.length > 0 ? (
                                    <span className="text-slate-500">
                                        {" "}
                                        · {actions.length} action
                                        {actions.length === 1 ? "" : "s"}
                                    </span>
                                ) : null}
                            </p>
                            <p className="mt-0.5 text-[10px] text-slate-500">
                                {formatTime(execution.started_at)}
                                {execution.error ? ` · ${execution.error}` : ""}
                            </p>
                        </div>
                    </li>
                );
            })}
        </ul>
    );
}
