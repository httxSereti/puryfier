import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

import AutomationActivity from "@/components/common/automations/AutomationActivity";
import SectionCard from "@/components/ui/section-card";
import StatusPill from "@/components/ui/status-pill";
import { fetchSessionAutomations } from "@/lib/http/automations";
import { getApiErrorMessage } from "@/lib/errors";
import type { AutomationListSchema } from "@/types/api";

export default function SessionAutomationsSummary({
    mainToken,
}: {
    mainToken: string;
}) {
    const [data, setData] = useState<AutomationListSchema | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const controller = new AbortController();
        const timer = window.setTimeout(() => {
            fetchSessionAutomations(mainToken, controller.signal)
                .then((result) => {
                    if (!controller.signal.aborted) {
                        setData(result);
                        setError(null);
                    }
                })
                .catch((cause: unknown) => {
                    if (!controller.signal.aborted) {
                        setError(
                            getApiErrorMessage(cause, "Could not load automations."),
                        );
                    }
                })
                .finally(() => {
                    if (!controller.signal.aborted) setLoading(false);
                });
        }, 0);

        return () => {
            window.clearTimeout(timer);
            controller.abort();
        };
    }, [mainToken]);

    const active = (data?.automations ?? []).filter((automation) => automation.enabled);

    return (
        <SectionCard
            icon={<Sparkles />}
            title="Automations"
            description="Rules that run automatically for this lock."
            accent="cyan"
            action={
                data ? (
                    <StatusPill tone={active.length > 0 ? "online" : "neutral"}>
                        {active.length} active
                    </StatusPill>
                ) : null
            }
        >
            {error ? (
                <p className="text-xs text-rose-300">{error}</p>
            ) : loading ? (
                <p className="text-xs text-slate-500">Loading automations…</p>
            ) : (
                <div className="flex flex-col gap-4">
                    {active.length > 0 ? (
                        <ul className="flex flex-col gap-1.5">
                            {active.map((automation) => (
                                <li
                                    key={automation.id}
                                    className="rounded-lg border border-white/[0.05] bg-black/10 px-3 py-2.5 text-xs text-slate-300"
                                >
                                    <span className="font-medium text-slate-200">
                                        {automation.name}
                                    </span>
                                    <span className="ml-2 text-slate-500">
                                        {automation.owner_role}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-4 py-4 text-center text-xs text-slate-500">
                            No active automations. Create one from the Automations tab.
                        </p>
                    )}

                    <div>
                        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                            Recent activity
                        </p>
                        <AutomationActivity executions={data?.executions ?? []} />
                    </div>
                </div>
            )}
        </SectionCard>
    );
}
