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

interface Template {
    id: string;
    label: string;
    description: string;
    icon: typeof Snowflake;
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

const AUTOMATION_TEMPLATES: Template[] = [
    {
        id: "lock-on-join",
        label: "Lock PuryFi on join",
        description: "When the user joins the lock, lock PuryFi and enable it.",
        icon: LogIn,
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
        payload: {
            name: "Warn when PuryFi is disabled",
            enabled: true,
            priority: 100,
            trigger: {
                event: "puryfi.state.changed",
                conditions: [
                    { field: "chaster_frozen", op: "eq", value: true },
                    { field: "puryfi_enabled", op: "eq", value: false },
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

export default function AutomationTemplates({
    onSelect,
}: {
    onSelect: (payload: AutomationCreateSchema) => void;
}) {
    return (
        <div className="grid gap-2 sm:grid-cols-2">
            {AUTOMATION_TEMPLATES.map((template) => {
                const Icon = template.icon;
                return (
                    <button
                        key={template.id}
                        type="button"
                        onClick={() => onSelect(template.payload)}
                        className="flex items-start gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-left transition-colors hover:border-cyan-400/20 hover:bg-cyan-400/[0.04]"
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
                        </span>
                    </button>
                );
            })}
        </div>
    );
}
