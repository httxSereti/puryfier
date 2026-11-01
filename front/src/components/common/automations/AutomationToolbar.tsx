import { Search, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import type {
    AutomationFilters,
    AutomationOwnerFilter,
    AutomationSort,
    AutomationSourceFilter,
    AutomationStatusFilter,
} from "@/lib/automations";

const SELECT_CLASS =
    "h-9 w-full rounded-lg border border-white/10 bg-[#0F0E16] px-2.5 text-xs text-white outline-none transition-colors focus:border-cyan-400/50 focus:ring-4 focus:ring-cyan-400/10";

interface AutomationToolbarProps {
    filters: AutomationFilters;
    sort: AutomationSort;
    resultCount: number;
    totalCount: number;
    onFiltersChange: (filters: AutomationFilters) => void;
    onSortChange: (sort: AutomationSort) => void;
    onReset: () => void;
}

export default function AutomationToolbar({
    filters,
    sort,
    resultCount,
    totalCount,
    onFiltersChange,
    onSortChange,
    onReset,
}: AutomationToolbarProps) {
    const hasFilters =
        filters.query.trim().length > 0 ||
        filters.status !== "all" ||
        filters.owner !== "all" ||
        filters.source !== "all";

    const updateFilter = <Key extends keyof AutomationFilters>(
        key: Key,
        value: AutomationFilters[Key],
    ) => {
        onFiltersChange({ ...filters, [key]: value });
    };

    return (
        <div className="flex flex-col gap-2.5">
            <div className="relative min-w-0">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-slate-500" />
                <Input
                    value={filters.query}
                    onChange={(event) => updateFilter("query", event.target.value)}
                    placeholder="Search automations…"
                    aria-label="Search automations"
                    className="h-9 border-white/10 bg-[#0F0E16] pl-9 pr-9 text-xs text-white placeholder:text-slate-600"
                />
                {filters.query ? (
                    <button
                        type="button"
                        onClick={() => updateFilter("query", "")}
                        aria-label="Clear automation search"
                        className="absolute right-2 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 hover:bg-white/[0.05] hover:text-white"
                    >
                        <X className="size-3.5" />
                    </button>
                ) : null}
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <select
                    value={filters.status}
                    onChange={(event) =>
                        updateFilter(
                            "status",
                            event.target.value as AutomationStatusFilter,
                        )
                    }
                    aria-label="Filter by status"
                    className={SELECT_CLASS}
                >
                    <option value="all">All statuses</option>
                    <option value="active">Active</option>
                    <option value="disabled">Disabled</option>
                </select>

                <select
                    value={filters.owner}
                    onChange={(event) =>
                        updateFilter(
                            "owner",
                            event.target.value as AutomationOwnerFilter,
                        )
                    }
                    aria-label="Filter by owner"
                    className={SELECT_CLASS}
                >
                    <option value="all">All owners</option>
                    <option value="mine">Mine</option>
                    <option value="keyholder">Keyholder</option>
                    <option value="wearer">Wearer</option>
                </select>

                <select
                    value={filters.source}
                    onChange={(event) =>
                        updateFilter(
                            "source",
                            event.target.value as AutomationSourceFilter,
                        )
                    }
                    aria-label="Filter by trigger"
                    className={SELECT_CLASS}
                >
                    <option value="all">All triggers</option>
                    <option value="chaster">Chaster</option>
                    <option value="puryfi">PuryFi</option>
                </select>

                <select
                    value={sort}
                    onChange={(event) =>
                        onSortChange(event.target.value as AutomationSort)
                    }
                    aria-label="Sort automations"
                    className={SELECT_CLASS}
                >
                    <option value="updated">Recently updated</option>
                    <option value="created">Recently created</option>
                    <option value="name">Name A–Z</option>
                </select>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
                <span>
                    {resultCount} of {totalCount} automation
                    {totalCount === 1 ? "" : "s"}
                </span>
                {hasFilters ? (
                    <button
                        type="button"
                        onClick={onReset}
                        className="font-medium text-cyan-300 transition-colors hover:text-cyan-200"
                    >
                        Reset filters
                    </button>
                ) : null}
            </div>
        </div>
    );
}
