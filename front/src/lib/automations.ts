import type {
    AutomationActionSchema,
    AutomationConditionSchema,
    AutomationSchema,
    AutomationTriggerSchema,
} from "@/types/api";

import { formatDuration } from "./format";

export type AutomationStatusFilter = "all" | "active" | "disabled";
export type AutomationOwnerFilter = "all" | "mine" | "keyholder" | "wearer";
export type AutomationSourceFilter = "all" | "chaster" | "puryfi";
export type AutomationSort = "updated" | "created" | "name";

export interface AutomationFilters {
    query: string;
    status: AutomationStatusFilter;
    owner: AutomationOwnerFilter;
    source: AutomationSourceFilter;
}

export const DEFAULT_AUTOMATION_FILTERS: AutomationFilters = {
    query: "",
    status: "all",
    owner: "all",
    source: "all",
};

const EVENT_LABELS: Record<string, string> = {
    "chaster.session.joined": "the user joins the lock",
    "chaster.session.left": "the user leaves the lock",
    "chaster.lock.frozen": "the Chaster lock is frozen",
    "chaster.lock.unfrozen": "the Chaster lock is unfrozen",
    "puryfi.media.scan": "an image is analysed by PuryFi",
    "puryfi.connection.ready": "PuryFi connects",
    "puryfi.connection.disconnected": "PuryFi disconnects",
    "puryfi.enabled": "PuryFi is enabled",
    "puryfi.disabled": "PuryFi is disabled",
    "puryfi.locked": "PuryFi is locked",
    "puryfi.unlocked": "PuryFi is unlocked",
};

export const LABEL_IMAGES: Record<string, string> = {
    Tummy: "/puryfi-labels/belly.png",
    TummyCovered: "/puryfi-labels/belly_covered.png",
    Buttocks: "/puryfi-labels/buttocks_exposed.png",
    ButtocksCovered: "/puryfi-labels/buttocks_covered.png",
    FemaleBreast: "/puryfi-labels/breasts_female_exposed.png",
    FemaleBreastCovered: "/puryfi-labels/breasts_female_covered.png",
    FemaleGenitals: "/puryfi-labels/genitals_female_exposed.png",
    FemaleGenitalsCovered: "/puryfi-labels/genitals_female_covered.png",
    MaleGenitalsCovered: "/puryfi-labels/genitals_male_covered.png",
    MaleGenitals: "/puryfi-labels/genitals_male_exposed.png",
    MaleBreast: "/puryfi-labels/breasts_male.png",
    MaleBreastCovered: "/puryfi-labels/breasts_male_covered.png",
    FemaleFace: "/puryfi-labels/face_female.png",
    MaleFace: "/puryfi-labels/face_male.png",
    FootCovered: "/puryfi-labels/feet_covered.png",
    Foot: "/puryfi-labels/feet_exposed.png",
    ArmpitCovered: "/puryfi-labels/armpit_covered.png",
    Armpit: "/puryfi-labels/armpit_exposed.png",
    AnusCovered: "/puryfi-labels/anus_covered.png",
    Anus: "/puryfi-labels/anus_exposed.png",
    Eye: "/puryfi-labels/eye.png",
    Mouth: "/puryfi-labels/mouth.png",
    NippleCovered: "/puryfi-labels/nipple_covered.png",
    Nipple: "/puryfi-labels/nipple_exposed.png",
    HandCovered: "/puryfi-labels/hand_covered.png",
    Hand: "/puryfi-labels/hand_exposed.png",
    Silhouette: "/puryfi-labels/silhouette.png",
};

export const FALLBACK_LABELS: Record<string, string> = {
    Tummy: "Belly",
    TummyCovered: "Belly (covered)",
    Buttocks: "Buttocks",
    ButtocksCovered: "Buttocks (covered)",
    FemaleBreast: "Breasts",
    FemaleBreastCovered: "Breasts (covered)",
    FemaleGenitals: "Female genitals",
    FemaleGenitalsCovered: "Female genitals (covered)",
    MaleGenitalsCovered: "Male genitals (covered)",
    MaleGenitals: "Male genitals",
    MaleBreast: "Male chest",
    MaleBreastCovered: "Male chest (covered)",
    FemaleFace: "Female face",
    MaleFace: "Male face",
    FootCovered: "Feet (covered)",
    Foot: "Feet",
    ArmpitCovered: "Armpits (covered)",
    Armpit: "Armpits",
    AnusCovered: "Anus (covered)",
    Anus: "Anus",
    Eye: "Eyes",
    Mouth: "Mouth",
    NippleCovered: "Nipples (covered)",
    Nipple: "Nipples",
    HandCovered: "Hands (covered)",
    Hand: "Hands",
    Silhouette: "Silhouette",
};

const ACTION_LABELS: Record<string, string> = {
    "puryfi.lock": "lock PuryFi with the stored or a generated password",
    "puryfi.enable": "enable PuryFi",
    "puryfi.unlock": "unlock PuryFi with the stored password",
    "puryfi.disable": "disable PuryFi",
    "puryfi.set_lock": "set the PuryFi lock",
    "puryfi.enter_emergency_token": "enter the emergency PuryFi token",
    "chaster.add_time": "add time to the Chaster lock",
    "chaster.remove_time": "remove time from the Chaster lock",
    "chaster.freeze": "freeze the Chaster lock",
    "chaster.unfreeze": "unfreeze the Chaster lock",
    "chaster.toggle_freeze": "toggle the Chaster freeze state",
    "chaster.pillory": "put the wearer in pillory",
    "chaster.set_timer_visibility": "change the remaining-time visibility",
    "chaster.log": "write a Chaster log",
};

const EVENT_NAMES: Record<string, string> = {
    "chaster.session.joined": "Session joined",
    "chaster.session.left": "Session left",
    "chaster.lock.frozen": "Lock frozen",
    "chaster.lock.unfrozen": "Lock unfrozen",
    "puryfi.media.scan": "Media scanned",
    "puryfi.connection.ready": "Connection ready",
    "puryfi.connection.disconnected": "Connection lost",
    "puryfi.enabled": "Enabled",
    "puryfi.disabled": "Disabled",
    "puryfi.locked": "Locked",
    "puryfi.unlocked": "Unlocked",
};

const ACTION_NAMES: Record<string, string> = {
    "puryfi.lock": "Lock PuryFi",
    "puryfi.enable": "Enable PuryFi",
    "puryfi.unlock": "Unlock PuryFi",
    "puryfi.disable": "Disable PuryFi",
    "puryfi.set_lock": "Update PuryFi lock",
    "puryfi.enter_emergency_token": "Use emergency token",
    "chaster.add_time": "Add time",
    "chaster.remove_time": "Remove time",
    "chaster.freeze": "Freeze lock",
    "chaster.unfreeze": "Unfreeze lock",
    "chaster.toggle_freeze": "Toggle freeze",
    "chaster.pillory": "Pillory",
    "chaster.set_timer_visibility": "Timer visibility",
    "chaster.log": "Write log",
};

export type AutomationSource = "puryfi" | "chaster";

export function automationSource(value: string): AutomationSource | null {
    if (value.startsWith("puryfi.")) return "puryfi";
    if (value.startsWith("chaster.")) return "chaster";
    return null;
}

export function eventLabel(event: string): string {
    return EVENT_LABELS[event] ?? event;
}

export function eventName(event: string): string {
    return EVENT_NAMES[event] ?? eventLabel(event);
}

export function actionName(type: string): string {
    return ACTION_NAMES[type] ?? type;
}

export function conditionLabel(
    condition: AutomationConditionSchema,
    labels: Record<string, string>,
): string {
    if (condition.field === "labels") {
        const values = Array.isArray(condition.value)
            ? condition.value
            : [condition.value];
        const names = values.map((value) => labels[String(value)] ?? String(value));
        if (condition.op === "contains_all") return names.join(" and ");
        if (condition.op === "contains_any") return names.join(" or ");
        if (condition.op === "not_contains") return `not ${names.join(" or ")}`;
        return names.join(", ");
    }
    if (condition.field === "score") {
        return `detection score ${condition.op === "lte" ? "≤" : "≥"} ${condition.value}`;
    }
    if (condition.field === "object_count") {
        return `at least ${condition.value} objects`;
    }
    if (condition.field === "chaster_frozen") {
        return condition.value ? "the Chaster lock is frozen" : "the Chaster lock is not frozen";
    }
    if (condition.field === "puryfi_enabled") {
        return condition.value ? "PuryFi is enabled" : "PuryFi is disabled";
    }
    if (condition.field === "puryfi_has_lock") {
        return condition.value ? "PuryFi has a lock" : "PuryFi has no lock";
    }
    return `${condition.field} ${condition.op} ${String(condition.value ?? "")}`;
}

export function triggerLabels(trigger: AutomationTriggerSchema): string[] {
    const values = new Set<string>();
    for (const condition of trigger.conditions ?? []) {
        if (condition.field !== "labels") continue;
        const raw = Array.isArray(condition.value)
            ? condition.value
            : [condition.value];
        for (const value of raw) values.add(String(value));
    }
    return [...values];
}

export function triggerSummary(
    trigger: AutomationTriggerSchema,
    labels: Record<string, string>,
): string {
    const parts: string[] = [];
    for (const condition of trigger.conditions ?? []) {
        parts.push(conditionLabel(condition, labels));
    }
    if (trigger.event === "puryfi.media.scan" && trigger.count > 1) {
        parts.push(
            `${trigger.count} matching ${trigger.count === 1 ? "image" : "images"}`,
        );
    }
    if (parts.length === 0) return eventLabel(trigger.event);
    return `${eventLabel(trigger.event)} — ${parts.join(", ")}`;
}

export function actionSummary(action: AutomationActionSchema): string {
    if (action.type === "chaster.add_time" || action.type === "chaster.remove_time") {
        const seconds = Number(action.params?.seconds ?? 0);
        const verb = action.type === "chaster.add_time" ? "add" : "remove";
        return `${verb} ${formatDuration(seconds)} ${verb === "add" ? "to" : "from"} the Chaster lock`;
    }
    if (action.type === "chaster.pillory") {
        const seconds = Number(action.params?.duration ?? 0);
        const reason = action.params?.reason
            ? ` (${String(action.params.reason)})`
            : "";
        return `put the wearer in pillory for ${formatDuration(seconds)}${reason}`;
    }
    if (action.type === "chaster.set_timer_visibility") {
        return action.params?.display_remaining_time
            ? "show the remaining lock time"
            : "hide the remaining lock time";
    }
    if (action.type === "chaster.log") {
        return `write a log${action.params?.title ? `: “${action.params.title}”` : ""}`;
    }
    return ACTION_LABELS[action.type] ?? action.type;
}

export function automationActionsSummary(automation: AutomationSchema): string {
    return automation.actions.map(actionSummary).join(", ");
}

export function automationTitle(automation: AutomationSchema): string {
    return automation.name;
}

function searchTokens(query: string): string[] {
    return query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
}

export function automationSearchText(
    automation: AutomationSchema,
    labels: Record<string, string>,
): string {
    return [
        automation.name,
        automation.lock_label ?? "",
        automation.owner_role,
        automation.trigger.event,
        ...automation.actions.map((action) => action.type),
        triggerSummary(automation.trigger, labels),
        automationActionsSummary(automation),
    ]
        .join(" ")
        .toLocaleLowerCase();
}

export function matchesAutomationFilters(
    automation: AutomationSchema,
    filters: AutomationFilters,
    labels: Record<string, string>,
): boolean {
    if (filters.status === "active" && !automation.enabled) return false;
    if (filters.status === "disabled" && automation.enabled) return false;

    if (filters.owner === "mine" && !automation.is_owner) return false;
    if (
        (filters.owner === "keyholder" || filters.owner === "wearer") &&
        automation.owner_role !== filters.owner
    ) {
        return false;
    }

    if (
        filters.source !== "all" &&
        !automation.trigger.event.startsWith(`${filters.source}.`)
    ) {
        return false;
    }

    const tokens = searchTokens(filters.query);
    if (tokens.length === 0) return true;

    const haystack = automationSearchText(automation, labels);
    return tokens.every((token) => haystack.includes(token));
}

function timestamp(value: string | null | undefined): number {
    if (!value) return 0;
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? 0 : parsed;
}

export function sortAutomations(
    automations: AutomationSchema[],
    sort: AutomationSort,
): AutomationSchema[] {
    const sorted = [...automations];

    if (sort === "name") {
        return sorted.sort((a, b) =>
            a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
        );
    }

    if (sort === "created") {
        return sorted.sort(
            (a, b) =>
                timestamp(b.created_at) - timestamp(a.created_at) ||
                a.name.localeCompare(b.name),
        );
    }

    return sorted.sort((a, b) => {
        const updated = timestamp(b.updated_at) - timestamp(a.updated_at);
        if (updated !== 0) return updated;
        return (
            timestamp(b.created_at) - timestamp(a.created_at) ||
            a.name.localeCompare(b.name)
        );
    });
}

export function filterAndSortAutomations(
    automations: AutomationSchema[],
    filters: AutomationFilters,
    labels: Record<string, string>,
    sort: AutomationSort,
): AutomationSchema[] {
    return sortAutomations(
        automations.filter((automation) =>
            matchesAutomationFilters(automation, filters, labels),
        ),
        sort,
    );
}
