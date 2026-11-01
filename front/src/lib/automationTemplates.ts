import {
    BellRing,
    Eye,
    Gavel,
    Gift,
    Image,
    LogIn,
    LogOut,
    RefreshCw,
    Shuffle,
    Snowflake,
    Timer,
    TimerOff,
    TriangleAlert,
    Unlock,
} from "lucide-react";

import type { AutomationCreateSchema } from "@/types/api";

export const TEMPLATE_TAGS = ["puryfi", "chaster"] as const;
export type AutomationTemplateTag = (typeof TEMPLATE_TAGS)[number];

export const TEMPLATE_TAG_LABELS: Record<AutomationTemplateTag, string> = {
    puryfi: "PuryFi",
    chaster: "Chaster",
};

export const TEMPLATE_CATEGORIES = ["sync", "media", "alerts"] as const;
export type AutomationTemplateCategory = (typeof TEMPLATE_CATEGORIES)[number];

export const TEMPLATE_CATEGORY_LABELS: Record<AutomationTemplateCategory, string> = {
    sync: "Synchronization",
    media: "Media & punishments",
    alerts: "Alerts & logs",
};

export interface AutomationTemplate {
    id: string;
    label: string;
    description: string;
    icon: typeof Snowflake;
    category: AutomationTemplateCategory;
    tags: AutomationTemplateTag[];
    payload: AutomationCreateSchema;
}

const CENSORABLE_LABELS = [
    "Buttocks",
    "FemaleBreast",
    "FemaleGenitals",
    "MaleGenitals",
    "Anus",
    "Nipple",
];

export const AUTOMATION_TEMPLATES: AutomationTemplate[] = [
    {
        id: "lock-on-join",
        label: "Lock PuryFi on join",
        description: "When the user joins the lock, lock PuryFi and enable it.",
        icon: LogIn,
        category: "sync",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Lock PuryFi on join",
            enabled: true,
            priority: 100,
            trigger: {
                event: "chaster.session.joined",
                conditions: [],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                { type: "puryfi.lock", params: {}, on_failure: "stop" },
                { type: "puryfi.enable", params: {}, on_failure: "stop" },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
    {
        id: "unlock-on-leave",
        label: "Unlock PuryFi on leave",
        description: "When the user leaves the lock, unlock and disable PuryFi.",
        icon: LogOut,
        category: "sync",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Unlock PuryFi on leave",
            enabled: true,
            priority: 100,
            trigger: {
                event: "chaster.session.left",
                conditions: [],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                { type: "puryfi.unlock", params: {}, on_failure: "stop" },
                { type: "puryfi.disable", params: {}, on_failure: "stop" },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
    {
        id: "lock-on-freeze",
        label: "Lock PuryFi on freeze",
        description: "When the Chaster lock is frozen, lock PuryFi and enable it.",
        icon: Snowflake,
        category: "sync",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Lock PuryFi on freeze",
            enabled: true,
            priority: 100,
            trigger: {
                event: "chaster.lock.frozen",
                conditions: [],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                { type: "puryfi.lock", params: {}, on_failure: "stop" },
                { type: "puryfi.enable", params: {}, on_failure: "stop" },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
    {
        id: "unlock-on-unfreeze",
        label: "Unlock PuryFi on unfreeze",
        description: "When the Chaster lock is unfrozen, unlock and disable PuryFi.",
        icon: Unlock,
        category: "sync",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Unlock PuryFi on unfreeze",
            enabled: true,
            priority: 100,
            trigger: {
                event: "chaster.lock.unfrozen",
                conditions: [],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                { type: "puryfi.unlock", params: {}, on_failure: "stop" },
                { type: "puryfi.disable", params: {}, on_failure: "stop" },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
    {
        id: "freeze-on-disconnect",
        label: "Freeze the lock when PuryFi disconnects",
        description:
            "If PuryFi disconnects, freeze the Chaster lock and write a log.",
        icon: Snowflake,
        category: "alerts",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Freeze the lock when PuryFi disconnects",
            enabled: true,
            priority: 100,
            trigger: {
                event: "puryfi.connection.disconnected",
                conditions: [{ field: "chaster_frozen", op: "eq", value: false }],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                { type: "chaster.freeze", params: {}, on_failure: "stop" },
                {
                    type: "chaster.log",
                    params: {
                        title: "PuryFi disconnected",
                        description:
                            "PuryFi disconnected, so the Chaster lock was frozen.",
                    },
                    on_failure: "continue",
                },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
    {
        id: "toggle-freeze-on-disconnect",
        label: "Toggle the freeze state when PuryFi disconnects",
        description:
            "If PuryFi disconnects, toggle the Chaster freeze state and write a log.",
        icon: Shuffle,
        category: "alerts",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Toggle the freeze state when PuryFi disconnects",
            enabled: true,
            priority: 100,
            trigger: {
                event: "puryfi.connection.disconnected",
                conditions: [],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                { type: "chaster.toggle_freeze", params: {}, on_failure: "stop" },
                {
                    type: "chaster.log",
                    params: {
                        title: "PuryFi disconnected",
                        description:
                            "PuryFi disconnected, so the Chaster freeze state was toggled.",
                    },
                    on_failure: "continue",
                },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
    {
        id: "hide-time-on-freeze",
        label: "Hide the remaining time when frozen",
        description:
            "When the Chaster lock is frozen, hide its remaining time from the wearer.",
        icon: TimerOff,
        category: "sync",
        tags: ["chaster"],
        payload: {
            name: "Hide the remaining time when frozen",
            enabled: true,
            priority: 100,
            trigger: {
                event: "chaster.lock.frozen",
                conditions: [],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                {
                    type: "chaster.set_timer_visibility",
                    params: { display_remaining_time: false },
                    on_failure: "continue",
                },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
    {
        id: "show-time-on-unfreeze",
        label: "Show the remaining time when unfrozen",
        description:
            "When the Chaster lock is unfrozen, show its remaining time to the wearer.",
        icon: Timer,
        category: "sync",
        tags: ["chaster"],
        payload: {
            name: "Show the remaining time when unfrozen",
            enabled: true,
            priority: 100,
            trigger: {
                event: "chaster.lock.unfrozen",
                conditions: [],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                {
                    type: "chaster.set_timer_visibility",
                    params: { display_remaining_time: true },
                    on_failure: "continue",
                },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
    {
        id: "pillory-censored-media",
        label: "Pillory for censored media",
        description:
            "When an image contains a censorable label, put the wearer in pillory for 5 minutes.",
        icon: Gavel,
        category: "media",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Pillory for censored media",
            enabled: true,
            priority: 100,
            trigger: {
                event: "puryfi.media.scan",
                conditions: [
                    {
                        field: "labels",
                        op: "contains_any",
                        value: CENSORABLE_LABELS,
                    },
                ],
                min_score: 0.5,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                {
                    type: "chaster.pillory",
                    params: {
                        duration: 300,
                        reason: "Censored media detected",
                    },
                    on_failure: "stop",
                },
            ],
            limits: { cooldown_seconds: 5, max_per_day: 0 },
        },
    },
    {
        id: "censored-media",
        label: "Add time for censored media",
        description: "Every 100 censorable images, add 10 minutes to the lock.",
        icon: Image,
        category: "media",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Add time for censored media",
            enabled: true,
            priority: 100,
            trigger: {
                event: "puryfi.media.scan",
                conditions: [
                    {
                        field: "labels",
                        op: "contains_any",
                        value: CENSORABLE_LABELS,
                    },
                ],
                min_score: 0.5,
                count: 100,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                {
                    type: "chaster.add_time",
                    params: { seconds: 600 },
                    on_failure: "stop",
                },
            ],
            limits: { cooldown_seconds: 5, max_per_day: 0 },
        },
    },
    {
        id: "eyes-and-belly",
        label: "Eyes and Belly",
        description: "When an image contains eyes and belly, add 2 minutes.",
        icon: Eye,
        category: "media",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Eyes and Belly",
            enabled: true,
            priority: 100,
            trigger: {
                event: "puryfi.media.scan",
                conditions: [
                    {
                        field: "labels",
                        op: "contains_all",
                        value: ["Eye", "Tummy"],
                    },
                ],
                min_score: 0.5,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                {
                    type: "chaster.add_time",
                    params: { seconds: 120 },
                    on_failure: "stop",
                },
            ],
            limits: { cooldown_seconds: 300, max_per_day: 0 },
        },
    },
    {
        id: "eyes-and-belly-reward",
        label: "Reward: Eyes and Belly",
        description: "When an image contains eyes and belly, remove 2 minutes.",
        icon: Gift,
        category: "media",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Reward: Eyes and Belly",
            enabled: true,
            priority: 100,
            trigger: {
                event: "puryfi.media.scan",
                conditions: [
                    {
                        field: "labels",
                        op: "contains_all",
                        value: ["Eye", "Tummy"],
                    },
                ],
                min_score: 0.5,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                {
                    type: "chaster.remove_time",
                    params: { seconds: 120 },
                    on_failure: "stop",
                },
            ],
            limits: { cooldown_seconds: 300, max_per_day: 0 },
        },
    },
    {
        id: "reapply-lock-on-connect",
        label: "Reapply the lock when PuryFi connects",
        description:
            "When PuryFi reconnects while the Chaster lock is frozen, reapply the stored PuryFi lock and enable it.",
        icon: RefreshCw,
        category: "sync",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Reapply PuryFi lock on connect",
            enabled: true,
            priority: 100,
            trigger: {
                event: "puryfi.connection.ready",
                conditions: [{ field: "chaster_frozen", op: "eq", value: true }],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                { type: "puryfi.lock", params: {}, on_failure: "stop" },
                { type: "puryfi.enable", params: {}, on_failure: "stop" },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
    {
        id: "warn-on-disconnect",
        label: "Warn when PuryFi disconnects",
        description:
            "Write a Chaster log when PuryFi disconnects while the Chaster lock is frozen.",
        icon: TriangleAlert,
        category: "alerts",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Warn when PuryFi disconnects",
            enabled: true,
            priority: 100,
            trigger: {
                event: "puryfi.connection.disconnected",
                conditions: [{ field: "chaster_frozen", op: "eq", value: true }],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                {
                    type: "chaster.log",
                    params: {
                        title: "PuryFi disconnected",
                        description:
                            "PuryFi disconnected while the Chaster lock is frozen.",
                    },
                    on_failure: "continue",
                },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
    {
        id: "warn-on-manual-disable",
        label: "Warn when PuryFi is disabled manually",
        description:
            "Write a Chaster log when PuryFi is disabled while the Chaster lock is frozen.",
        icon: BellRing,
        category: "alerts",
        tags: ["puryfi", "chaster"],
        payload: {
            name: "Warn when PuryFi is disabled",
            enabled: true,
            priority: 100,
            trigger: {
                event: "puryfi.disabled",
                conditions: [
                    { field: "chaster_frozen", op: "eq", value: true },
                ],
                min_score: 0,
                count: 1,
                window_seconds: 0,
                count_mode: "images",
            },
            actions: [
                {
                    type: "chaster.log",
                    params: {
                        title: "PuryFi disabled manually",
                        description:
                            "PuryFi was disabled while the Chaster lock is frozen.",
                    },
                    on_failure: "continue",
                },
            ],
            limits: { cooldown_seconds: 0, max_per_day: 0 },
        },
    },
];

function normalize(value: string): string {
    return value.trim().toLocaleLowerCase();
}

export function templateMatchesQuery(
    template: AutomationTemplate,
    query: string,
): boolean {
    const tokens = normalize(query).split(/\s+/).filter(Boolean);
    if (tokens.length === 0) return true;

    const haystack = [
        template.label,
        template.description,
        TEMPLATE_CATEGORY_LABELS[template.category],
        ...template.tags.map((tag) => TEMPLATE_TAG_LABELS[tag]),
        ...template.tags,
    ]
        .join(" ")
        .toLocaleLowerCase();

    return tokens.every((token) => haystack.includes(token));
}

export function filterAutomationTemplates(
    templates: AutomationTemplate[],
    query: string,
    selectedTags: AutomationTemplateTag[],
): AutomationTemplate[] {
    return templates.filter(
        (template) =>
            templateMatchesQuery(template, query) &&
            (selectedTags.length === 0 ||
                selectedTags.every((tag) => template.tags.includes(tag))),
    );
}

export function groupAutomationTemplates(
    templates: AutomationTemplate[],
): Array<{
    category: AutomationTemplateCategory;
    label: string;
    templates: AutomationTemplate[];
}> {
    return TEMPLATE_CATEGORIES.map((category) => ({
        category,
        label: TEMPLATE_CATEGORY_LABELS[category],
        templates: templates.filter((template) => template.category === category),
    })).filter((group) => group.templates.length > 0);
}
