import { useMemo, useState } from "react";
import { Search, SearchX, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    AUTOMATION_TEMPLATES,
    TEMPLATE_TAGS,
    TEMPLATE_TAG_LABELS,
    filterAutomationTemplates,
    groupAutomationTemplates,
} from "@/lib/automationTemplates";
import type { AutomationTemplateTag } from "@/lib/automationTemplates";
import { cn } from "@/lib/utils";
import type { AutomationCreateSchema } from "@/types/api";

export default function AutomationTemplates({
    onSelect,
}: {
    onSelect: (payload: AutomationCreateSchema) => void;
}) {
    const [query, setQuery] = useState("");
    const [selectedTags, setSelectedTags] = useState<AutomationTemplateTag[]>([]);

    const visibleTemplates = useMemo(
        () => filterAutomationTemplates(AUTOMATION_TEMPLATES, query, selectedTags),
        [query, selectedTags],
    );
    const groups = useMemo(
        () => groupAutomationTemplates(visibleTemplates),
        [visibleTemplates],
    );
    const hasFilters = query.trim().length > 0 || selectedTags.length > 0;

    const toggleTag = (tag: AutomationTemplateTag) => {
        setSelectedTags((current) =>
            current.includes(tag)
                ? current.filter((value) => value !== tag)
                : [...current, tag],
        );
    };

    const resetFilters = () => {
        setQuery("");
        setSelectedTags([]);
    };

    return (
        <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2.5">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <div className="relative min-w-0 flex-1">
                        <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-slate-500" />
                        <Input
                            value={query}
                            onChange={(event) => setQuery(event.target.value)}
                            placeholder="Search templates…"
                            aria-label="Search templates"
                            className="h-9 border-white/10 bg-[#0F0E16] pl-9 pr-9 text-xs text-white placeholder:text-slate-600"
                        />
                        {query ? (
                            <button
                                type="button"
                                onClick={() => setQuery("")}
                                aria-label="Clear template search"
                                className="absolute right-2 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 hover:bg-white/[0.05] hover:text-white"
                            >
                                <X className="size-3.5" />
                            </button>
                        ) : null}
                    </div>
                    <span className="shrink-0 text-[11px] text-slate-500">
                        {visibleTemplates.length} of {AUTOMATION_TEMPLATES.length} templates
                    </span>
                </div>

                <div
                    role="group"
                    aria-label="Filter templates by tag"
                    className="flex flex-wrap items-center gap-1.5"
                >
                    <TagChip
                        active={selectedTags.length === 0}
                        onClick={() => setSelectedTags([])}
                    >
                        All
                    </TagChip>
                    {TEMPLATE_TAGS.map((tag) => (
                        <TagChip
                            key={tag}
                            active={selectedTags.includes(tag)}
                            onClick={() => toggleTag(tag)}
                        >
                            {TEMPLATE_TAG_LABELS[tag]}
                        </TagChip>
                    ))}
                </div>
            </div>

            {groups.length === 0 ? (
                <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.015] px-4 py-8 text-center">
                    <SearchX className="mx-auto size-5 text-slate-500" />
                    <p className="mt-2 text-sm font-medium text-slate-300">
                        No templates match your filters
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                        Try another search or a different tag.
                    </p>
                    {hasFilters ? (
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={resetFilters}
                            className="mt-3 text-slate-300 hover:text-white"
                        >
                            Reset filters
                        </Button>
                    ) : null}
                </div>
            ) : (
                <div className="flex flex-col gap-5">
                    {groups.map((group) => (
                        <section
                            key={group.category}
                            aria-labelledby={`template-group-${group.category}`}
                            className="space-y-2"
                        >
                            <div className="flex items-center gap-2">
                                <h3
                                    id={`template-group-${group.category}`}
                                    className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400"
                                >
                                    {group.label}
                                </h3>
                                <span className="rounded-full border border-white/[0.07] bg-white/[0.02] px-1.5 py-0.5 text-[10px] text-slate-500">
                                    {group.templates.length}
                                </span>
                            </div>
                            <div className="grid gap-2 sm:grid-cols-2">
                                {group.templates.map((template) => {
                                    const Icon = template.icon;
                                    return (
                                        <button
                                            key={template.id}
                                            type="button"
                                            onClick={() => onSelect(template.payload)}
                                            className="flex h-full items-start gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-left transition-colors hover:border-cyan-400/20 hover:bg-cyan-400/[0.04]"
                                        >
                                            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-cyan-400/15 bg-cyan-400/[0.07] text-cyan-300">
                                                <Icon className="size-4" />
                                            </span>
                                            <span className="min-w-0">
                                                <span className="block text-xs font-semibold text-slate-200">
                                                    {template.label}
                                                </span>
                                                <span className="mt-0.5 block text-[11px] leading-relaxed text-slate-500">
                                                    {template.description}
                                                </span>
                                                <span className="mt-2 flex flex-wrap gap-1">
                                                    {template.tags.map((tag) => (
                                                        <span
                                                            key={tag}
                                                            className="rounded-md border border-white/[0.06] bg-black/10 px-1.5 py-0.5 text-[10px] text-slate-500"
                                                        >
                                                            {tag}
                                                        </span>
                                                    ))}
                                                </span>
                                            </span>
                                        </button>
                                    );
                                })}
                            </div>
                        </section>
                    ))}
                </div>
            )}
        </div>
    );
}

function TagChip({
    active,
    onClick,
    children,
}: {
    active: boolean;
    onClick: () => void;
    children: string;
}) {
    return (
        <button
            type="button"
            aria-pressed={active}
            onClick={onClick}
            className={cn(
                "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                active
                    ? "border-cyan-400/25 bg-cyan-400/10 text-cyan-200"
                    : "border-white/[0.07] bg-white/[0.02] text-slate-400 hover:border-white/15 hover:text-slate-200",
            )}
        >
            {children}
        </button>
    );
}
