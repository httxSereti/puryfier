import { useCallback, useEffect, useMemo, useState } from "react";
import {
    Copy,
    LayoutTemplate,
    ListChecks,
    Plus,
    SearchX,
    Sparkles,
    Trash2,
    X,
} from "lucide-react";

import AutomationActivity from "@/components/common/automations/AutomationActivity";
import AutomationCard from "@/components/common/automations/AutomationCard";
import AutomationEditor from "@/components/common/automations/AutomationEditor";
import AutomationTemplates from "@/components/common/automations/AutomationTemplates";
import AutomationToolbar from "@/components/common/automations/AutomationToolbar";
import ErrorAlert from "@/components/ui/error-alert";
import SectionCard from "@/components/ui/section-card";
import { Button } from "@/components/ui/button";
import Tabs from "@/components/ui/tabs";
import type { TabItem } from "@/components/ui/tabs";
import {
    createAutomation,
    createSessionAutomation,
    deleteAutomation,
    deleteSessionAutomation,
    duplicateAutomation,
    duplicateSessionAutomation,
    fetchAutomationCatalog,
    fetchAutomations,
    fetchSessionAutomationCatalog,
    fetchSessionAutomations,
    updateAutomation,
    updateSessionAutomation,
} from "@/lib/http/automations";
import {
    DEFAULT_AUTOMATION_FILTERS,
    FALLBACK_LABELS,
    filterAndSortAutomations,
} from "@/lib/automations";
import type { AutomationFilters, AutomationSort } from "@/lib/automations";
import { getApiErrorMessage } from "@/lib/errors";
import type {
    AutomationCatalogSchema,
    AutomationCreateSchema,
    AutomationListSchema,
    AutomationSchema,
} from "@/types/api";

interface AutomationsSectionProps {
    configurationToken?: string;
    mainToken?: string;
    onChanged?: () => void;
}

type AutomationsView = "mine" | "templates";

const VIEW_TABS: TabItem[] = [
    { value: "mine", label: "My automations", icon: <ListChecks /> },
    { value: "templates", label: "Templates", icon: <LayoutTemplate /> },
];

export default function AutomationsSection({
    configurationToken,
    mainToken,
    onChanged,
}: AutomationsSectionProps) {
    const token = configurationToken ?? mainToken ?? "";
    const isSession = !configurationToken && Boolean(mainToken);
    const [data, setData] = useState<AutomationListSchema | null>(null);
    const [catalog, setCatalog] = useState<AutomationCatalogSchema | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const [editorOpen, setEditorOpen] = useState(false);
    const [editing, setEditing] = useState<AutomationSchema | AutomationCreateSchema | null>(null);
    const [duplicateSource, setDuplicateSource] = useState<AutomationSchema | null>(null);
    const [duplicateTarget, setDuplicateTarget] = useState("");
    const [deleteSource, setDeleteSource] = useState<AutomationSchema | null>(null);

    const [view, setView] = useState<AutomationsView>("mine");
    const [filters, setFilters] = useState<AutomationFilters>({
        ...DEFAULT_AUTOMATION_FILTERS,
    });
    const [sort, setSort] = useState<AutomationSort>("updated");

    const resetFilters = () => {
        setFilters({ ...DEFAULT_AUTOMATION_FILTERS });
        setSort("updated");
    };

    const load = useCallback(async () => {
        try {
            const [automations, catalogData] = await Promise.all([
                isSession
                    ? fetchSessionAutomations(token)
                    : fetchAutomations(token),
                (isSession
                    ? fetchSessionAutomationCatalog(token)
                    : fetchAutomationCatalog(token)
                ).catch(() => null),
            ]);
            setData(automations);
            setCatalog(catalogData);
            setError(null);
        } catch (cause) {
            setError(getApiErrorMessage(cause, "Could not load automations."));
        } finally {
            setIsLoading(false);
        }
    }, [isSession, token]);

    useEffect(() => {
        // Defer the initial fetch by one task so the effect body itself does
        // not trigger a synchronous state update.
        const timer = window.setTimeout(() => {
            void load();
        }, 0);
        return () => window.clearTimeout(timer);
    }, [load]);

    const labels = useMemo(() => {
        if (catalog?.labels?.length) {
            return catalog.labels;
        }
        return Object.entries(FALLBACK_LABELS).map(([value, label]) => ({
            value,
            label,
            censorable: false,
        }));
    }, [catalog]);

    const labelNames = useMemo(
        () => Object.fromEntries(labels.map((label) => [label.value, label.label])),
        [labels],
    );

    const run = async (operation: () => Promise<void>) => {
        setBusy(true);
        setError(null);
        try {
            await operation();
            await load();
            onChanged?.();
        } catch (cause) {
            setError(getApiErrorMessage(cause, "The automation could not be saved."));
        } finally {
            setBusy(false);
        }
    };

    const handleSave = async (payload: AutomationCreateSchema) => {
        const isNew = !(editing && "id" in editing);
        await run(async () => {
            if (editing && "id" in editing) {
                if (isSession) {
                    await updateSessionAutomation(token, editing.id, payload);
                } else {
                    await updateAutomation(token, editing.id, payload);
                }
            } else if (isSession) {
                await createSessionAutomation(token, payload);
            } else {
                await createAutomation(token, payload);
            }
            setEditorOpen(false);
            setEditing(null);
            if (isNew) {
                setView("mine");
                resetFilters();
            }
        });
    };

    const handleToggle = async (automation: AutomationSchema) => {
        await run(async () => {
            const payload = { enabled: !automation.enabled };
            if (isSession) {
                await updateSessionAutomation(token, automation.id, payload);
            } else {
                await updateAutomation(token, automation.id, payload);
            }
        });
    };

    const handleDelete = (automation: AutomationSchema) => {
        setDeleteSource(automation);
    };

    const confirmDelete = async () => {
        if (!deleteSource) return;
        await run(async () => {
            if (isSession) {
                await deleteSessionAutomation(token, deleteSource.id);
            } else {
                await deleteAutomation(token, deleteSource.id);
            }
            setDeleteSource(null);
        });
    };

    const handleDuplicate = async () => {
        if (!duplicateSource || !duplicateTarget) return;
        await run(async () => {
            if (isSession) {
                await duplicateSessionAutomation(
                    token,
                    duplicateSource.id,
                    duplicateTarget,
                );
            } else {
                await duplicateAutomation(
                    token,
                    duplicateSource.id,
                    duplicateTarget,
                );
            }
            setDuplicateSource(null);
            setDuplicateTarget("");
        });
    };

    const active = data?.automations ?? [];
    const archived = data?.archived_automations ?? [];
    const canManage = Boolean(
        data && (data.role === "keyholder" || data.effective_wearer_can_manage),
    );
    const visibleAutomations = useMemo(
        () =>
            filterAndSortAutomations(
                data?.automations ?? [],
                filters,
                labelNames,
                sort,
            ),
        [data, filters, labelNames, sort],
    );

    return (
        <div className="flex flex-col gap-5">
            <SectionCard
                icon={<Sparkles />}
                title="Automations"
                description="Rules that run automatically for this lock."
                accent="cyan"
                action={
                    canManage ? (
                        <Button
                            type="button"
                            size="sm"
                            onClick={() => {
                                setEditing(null);
                                setEditorOpen(true);
                            }}
                            className="ml-auto bg-cyan-500 text-slate-950 hover:bg-cyan-400"
                        >
                            <Plus />
                            New automation
                        </Button>
                    ) : null
                }
            >
                <div className="flex flex-col gap-4">
                    <Tabs
                        items={VIEW_TABS}
                        value={view}
                        onChange={(value) => {
                            if (value === "mine" || value === "templates") {
                                setView(value);
                            }
                        }}
                        ariaLabel="Automation views"
                        className="sm:w-fit"
                    />

                    {view === "mine" ? (
                        <div
                            role="tabpanel"
                            aria-label="My automations"
                            className="flex flex-col gap-3"
                        >
                            {error ? (
                                <ErrorAlert message={error} onRetry={load} />
                            ) : isLoading ? (
                                <p className="px-1 py-4 text-xs text-slate-500">
                                    Loading automations…
                                </p>
                            ) : active.length === 0 ? (
                                <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-4 py-5 text-center">
                                    <p className="text-sm font-medium text-slate-300">
                                        No automations yet
                                    </p>
                                    <p className="mt-1 text-xs text-slate-500">
                                        {canManage
                                            ? "Start from a template or create your own rule."
                                            : "You do not have permission to create automations for this lock."}
                                    </p>
                                    {canManage ? (
                                        <Button
                                            type="button"
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => setView("templates")}
                                            className="mt-3 border border-white/10 bg-white/[0.04] text-slate-200 hover:bg-white/[0.08]"
                                        >
                                            <LayoutTemplate />
                                            Browse templates
                                        </Button>
                                    ) : null}
                                </div>
                            ) : (
                                <>
                                    <AutomationToolbar
                                        filters={filters}
                                        sort={sort}
                                        resultCount={visibleAutomations.length}
                                        totalCount={active.length}
                                        onFiltersChange={setFilters}
                                        onSortChange={setSort}
                                        onReset={resetFilters}
                                    />

                                    {visibleAutomations.length === 0 ? (
                                        <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-4 py-7 text-center">
                                            <SearchX className="mx-auto size-5 text-slate-500" />
                                            <p className="mt-2 text-sm font-medium text-slate-300">
                                                No automations match your filters
                                            </p>
                                            <p className="mt-1 text-xs text-slate-500">
                                                Adjust the search or filters to see more
                                                rules.
                                            </p>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                onClick={resetFilters}
                                                className="mt-3 text-slate-300 hover:text-white"
                                            >
                                                Reset filters
                                            </Button>
                                        </div>
                                    ) : (
                                        <div className="flex flex-col gap-2.5">
                                            {visibleAutomations.map((automation) => (
                                                <AutomationCard
                                                    key={automation.id}
                                                    automation={automation}
                                                    labelNames={labelNames}
                                                    busy={busy}
                                                    onToggle={handleToggle}
                                                    onEdit={(rule) => {
                                                        setEditing(rule);
                                                        setEditorOpen(true);
                                                    }}
                                                    onDuplicate={(rule) => {
                                                        setDuplicateSource(rule);
                                                        setDuplicateTarget(
                                                            data?.targets?.[0]
                                                                ?.session_id ?? "",
                                                        );
                                                    }}
                                                    onDelete={handleDelete}
                                                />
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    ) : (
                        <div
                            role="tabpanel"
                            aria-label="Templates"
                            className="flex flex-col gap-3"
                        >
                            {error ? (
                                <ErrorAlert message={error} onRetry={load} />
                            ) : isLoading ? (
                                <p className="px-1 py-4 text-xs text-slate-500">
                                    Loading templates…
                                </p>
                            ) : canManage ? (
                                <AutomationTemplates
                                    onSelect={(payload) => {
                                        setEditing(payload);
                                        setEditorOpen(true);
                                    }}
                                />
                            ) : (
                                <p className="rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-4 py-5 text-center text-xs text-slate-500">
                                    You do not have permission to create automations
                                    for this lock.
                                </p>
                            )}
                        </div>
                    )}
                </div>
            </SectionCard>

            {view === "mine" && !error && !isLoading ? (
                <>
                    {archived.length > 0 ? (
                        <SectionCard
                            icon={<Copy />}
                            title="Archived automations"
                            description="Kept for 30 days. Duplicate one into another lock."
                            accent="neutral"
                        >
                            <div className="flex flex-col gap-2.5">
                                {archived.map((automation) => (
                                    <AutomationCard
                                        key={automation.id}
                                        automation={automation}
                                        labelNames={labelNames}
                                        busy={busy}
                                        onDuplicate={(rule) => {
                                            setDuplicateSource(rule);
                                            setDuplicateTarget(
                                                data?.targets?.[0]?.session_id ?? "",
                                            );
                                        }}
                                    />
                                ))}
                            </div>
                        </SectionCard>
                    ) : null}

                    <SectionCard
                        icon={<Sparkles />}
                        title="Recent activity"
                        description="The latest automation runs for this lock."
                        accent="violet"
                    >
                        <AutomationActivity executions={data?.executions ?? []} />
                    </SectionCard>
                </>
            ) : null}

            {editorOpen ? (
                <AutomationEditor
                    key={editing && "id" in editing ? editing.id : "new"}
                    open
                    initial={editing}
                    labels={labels}
                    busy={busy}
                    onClose={() => {
                        setEditorOpen(false);
                        setEditing(null);
                    }}
                    onSave={handleSave}
                />
            ) : null}

            {deleteSource ? (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
                    onClick={() => {
                        if (!busy) setDeleteSource(null);
                    }}
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="delete-automation-title"
                        className="w-full max-w-md rounded-2xl border border-white/10 bg-[#17151F] p-5 shadow-2xl"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-3">
                                <div className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-rose-400/20 bg-rose-400/10 text-rose-300">
                                    <Trash2 className="size-4" />
                                </div>
                                <div>
                                    <h2
                                        id="delete-automation-title"
                                        className="text-sm font-semibold text-white"
                                    >
                                        Delete automation
                                    </h2>
                                    <p className="mt-1 text-xs leading-relaxed text-slate-400">
                                        Delete “{deleteSource.name}”? This cannot be undone.
                                    </p>
                                </div>
                            </div>
                            <button
                                type="button"
                                onClick={() => setDeleteSource(null)}
                                disabled={busy}
                                aria-label="Close delete dialog"
                                className="text-slate-500 hover:text-white disabled:opacity-50"
                            >
                                <X className="size-4" />
                            </button>
                        </div>

                        <div className="mt-5 flex justify-end gap-2">
                            <Button
                                type="button"
                                variant="ghost"
                                onClick={() => setDeleteSource(null)}
                                disabled={busy}
                                className="text-slate-400 hover:text-white"
                            >
                                Cancel
                            </Button>
                            <Button
                                type="button"
                                onClick={confirmDelete}
                                disabled={busy}
                                className="bg-rose-500 text-white hover:bg-rose-400"
                            >
                                <Trash2 />
                                Delete
                            </Button>
                        </div>
                    </div>
                </div>
            ) : null}

            {duplicateSource ? (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
                    onClick={() => setDuplicateSource(null)}
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="duplicate-title"
                        className="w-full max-w-md rounded-2xl border border-white/10 bg-[#17151F] p-5 shadow-2xl"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="flex items-start justify-between gap-3">
                            <div>
                                <h2 id="duplicate-title" className="text-sm font-semibold text-white">
                                    Duplicate automation
                                </h2>
                                <p className="mt-1 text-xs text-slate-400">
                                    The copy is created disabled. Review it before enabling.
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={() => setDuplicateSource(null)}
                                aria-label="Close duplicate dialog"
                                className="text-slate-500 hover:text-white"
                            >
                                <X className="size-4" />
                            </button>
                        </div>

                        {data?.targets?.length ? (
                            <div className="mt-4 space-y-2">
                                <label className="text-xs font-medium text-slate-300">
                                    Target lock
                                </label>
                                <select
                                    value={duplicateTarget}
                                    onChange={(event) => setDuplicateTarget(event.target.value)}
                                    className="h-11 w-full rounded-xl border border-white/10 bg-[#0F0E16] px-3 text-sm text-white"
                                >
                                    {data.targets.map((target) => (
                                        <option key={target.session_id} value={target.session_id}>
                                            {target.lock_label ?? target.session_id}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        ) : (
                            <p className="mt-4 rounded-lg border border-amber-400/20 bg-amber-400/[0.07] px-3 py-2 text-xs text-amber-100">
                                Open another lock once to make it available as a duplication target.
                            </p>
                        )}

                        <div className="mt-5 flex justify-end gap-2">
                            <Button
                                type="button"
                                variant="ghost"
                                onClick={() => setDuplicateSource(null)}
                                className="text-slate-400 hover:text-white"
                            >
                                Cancel
                            </Button>
                            <Button
                                type="button"
                                disabled={busy || !duplicateTarget}
                                onClick={handleDuplicate}
                                className="bg-cyan-500 text-slate-950 hover:bg-cyan-400"
                            >
                                <Copy />
                                Duplicate
                            </Button>
                        </div>
                    </div>
                </div>
            ) : null}
        </div>
    );
}
