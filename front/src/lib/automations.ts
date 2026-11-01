import type {
    AutomationActionSchema,
    AutomationConditionSchema,
    AutomationSchema,
    AutomationTriggerSchema,
} from "@/types/api";

import { formatDuration } from "./format";

const EVENT_LABELS: Record<string, string> = {
    "chaster.session.joined": "the user joins the lock",
    "chaster.session.left": "the user leaves the lock",
    "chaster.lock.frozen": "the Chaster lock is frozen",
    "chaster.lock.unfrozen": "the Chaster lock is unfrozen",
    "puryfi.media.scan": "an image is analysed by PuryFi",
    "puryfi.connection.ready": "PuryFi connects",
    "puryfi.connection.disconnected": "PuryFi disconnects",
    "puryfi.state.changed": "the PuryFi state changes",
    "puryfi.user.changed": "the PuryFi account changes",
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
    "chaster.log": "write a Chaster log",
};

export function eventLabel(event: string): string {
    return EVENT_LABELS[event] ?? event;
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
