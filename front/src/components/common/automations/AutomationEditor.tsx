import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
    ArrowDown,
    Check,
    ChevronDown,
    CircleMinus,
    CirclePlus,
    Clock3,
    Eye,
    Gauge,
    Gavel,
    Image as ImageIcon,
    LoaderCircle,
    LockKeyhole,
    LogIn,
    LogOut,
    Pause,
    Pencil,
    Play,
    Power,
    PowerOff,
    Save,
    ScrollText,
    Search,
    ShieldCheck,
    Shuffle,
    Snowflake,
    Sparkles,
    Sun,
    Timer,
    Unlock,
    Wifi,
    WifiOff,
    X,
    Zap,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import NumberInput from "@/components/ui/number-input";
import {
    LABEL_IMAGES,
    actionName,
    actionSummary,
    eventName,
    triggerSummary,
} from "@/lib/automations";
import type { AutomationSource } from "@/lib/automations";
import { cn } from "@/lib/utils";
import type {
    AutomationActionSchema,
    AutomationConditionSchema,
    AutomationCreateSchema,
    AutomationLabelCatalogSchema,
    AutomationSchema,
    AutomationTriggerSchema,
} from "@/types/api";

interface AutomationEditorProps {
    open: boolean;
    initial?: AutomationSchema | AutomationCreateSchema | null;
    labels: AutomationLabelCatalogSchema[];
    busy?: boolean;
    onClose: () => void;
    onSave: (payload: AutomationCreateSchema) => Promise<void> | void;
}

type EditorIcon = typeof Sparkles;
type LabelMatch = "all" | "any";

interface EditorState {
    name: string;
    event: string;
    selectedLabels: string[];
    labelMatch: LabelMatch;
    minScore: string;
    count: number;
    windowMinutes: number;
    cooldownSeconds: number;
    maxPerDay: number;
    enabled: boolean;
    priority: number;
    lockPuryfi: boolean;
    enablePuryfi: boolean;
    unlockPuryfi: boolean;
    disablePuryfi: boolean;
    freezeChaster: boolean;
    unfreezeChaster: boolean;
    toggleFreeze: boolean;
    pillory: boolean;
    pilloryDuration: number;
    pilloryReason: string;
    timerVisibility: boolean;
    displayRemainingTime: boolean;
    addTime: boolean;
    addTimeSeconds: number;
    removeTime: boolean;
    removeTimeSeconds: number;
    writeLog: boolean;
    logTitle: string;
    // Conditions that are not edited by the simple form (for example
    // chaster_frozen) are preserved on save.
    extraConditions: AutomationConditionSchema[];
}

type ActionKey =
    | "lockPuryfi"
    | "enablePuryfi"
    | "unlockPuryfi"
    | "disablePuryfi"
    | "freezeChaster"
    | "unfreezeChaster"
    | "toggleFreeze"
    | "pillory"
    | "timerVisibility"
    | "addTime"
    | "removeTime"
    | "writeLog";

interface EventMeta {
    value: string;
    label: string;
    description: string;
    source: AutomationSource;
    icon: EditorIcon;
}

interface EventGroupMeta {
    id: AutomationSource;
    label: string;
    events: EventMeta[];
}

interface ActionMeta {
    key: ActionKey;
    type: string;
    title: string;
    ariaLabel: string;
    description: string;
    icon: EditorIcon;
}

interface ActionGroupMeta {
    id: AutomationSource;
    label: string;
    description: string;
    icon: EditorIcon;
    actions: ActionMeta[];
}

const LOG_ONLY_EVENTS = new Set([
    "puryfi.connection.disconnected",
    "puryfi.enabled",
    "puryfi.disabled",
    "puryfi.locked",
    "puryfi.unlocked",
]);

const DEFAULT_STATE: EditorState = {
    name: "",
    event: "chaster.lock.frozen",
    selectedLabels: [],
    labelMatch: "all",
    minScore: "0.5",
    count: 1,
    windowMinutes: 0,
    cooldownSeconds: 0,
    maxPerDay: 0,
    enabled: true,
    priority: 100,
    lockPuryfi: true,
    enablePuryfi: true,
    unlockPuryfi: false,
    disablePuryfi: false,
    freezeChaster: false,
    unfreezeChaster: false,
    toggleFreeze: false,
    pillory: false,
    pilloryDuration: 300,
    pilloryReason: "",
    timerVisibility: false,
    displayRemainingTime: true,
    addTime: false,
    addTimeSeconds: 120,
    removeTime: false,
    removeTimeSeconds: 120,
    writeLog: false,
    logTitle: "Automation triggered",
    extraConditions: [],
};

const EVENT_GROUPS: EventGroupMeta[] = [
    {
        id: "chaster",
        label: "Chaster events",
        events: [
            {
                value: "chaster.session.joined",
                label: "The user joins the lock",
                description: "Runs when the wearer joins this Chaster lock.",
                source: "chaster",
                icon: LogIn,
            },
            {
                value: "chaster.session.left",
                label: "The user leaves the lock",
                description: "Runs when the wearer leaves this Chaster lock.",
                source: "chaster",
                icon: LogOut,
            },
            {
                value: "chaster.lock.frozen",
                label: "The Chaster lock is frozen",
                description: "Runs when the Chaster lock enters the frozen state.",
                source: "chaster",
                icon: Snowflake,
            },
            {
                value: "chaster.lock.unfrozen",
                label: "The Chaster lock is unfrozen",
                description: "Runs when the Chaster lock leaves the frozen state.",
                source: "chaster",
                icon: Sun,
            },
        ],
    },
    {
        id: "puryfi",
        label: "PuryFi events",
        events: [
            {
                value: "puryfi.media.scan",
                label: "An image is analysed by PuryFi",
                description: "Runs every time PuryFi analyses an image.",
                source: "puryfi",
                icon: ImageIcon,
            },
            {
                value: "puryfi.connection.ready",
                label: "PuryFi connects",
                description: "Runs when the PuryFi device comes online.",
                source: "puryfi",
                icon: Wifi,
            },
            {
                value: "puryfi.connection.disconnected",
                label: "PuryFi disconnects",
                description: "Runs when PuryFi stops responding.",
                source: "puryfi",
                icon: WifiOff,
            },
            {
                value: "puryfi.enabled",
                label: "PuryFi is enabled",
                description: "Runs when PuryFi is switched on.",
                source: "puryfi",
                icon: Power,
            },
            {
                value: "puryfi.disabled",
                label: "PuryFi is disabled",
                description: "Runs when PuryFi is switched off.",
                source: "puryfi",
                icon: PowerOff,
            },
            {
                value: "puryfi.locked",
                label: "PuryFi is locked",
                description: "Runs when the PuryFi lock is engaged.",
                source: "puryfi",
                icon: LockKeyhole,
            },
            {
                value: "puryfi.unlocked",
                label: "PuryFi is unlocked",
                description: "Runs when the PuryFi lock is released.",
                source: "puryfi",
                icon: Unlock,
            },
        ],
    },
];

const EVENT_META: Record<string, EventMeta> = Object.fromEntries(
    EVENT_GROUPS.flatMap((group) =>
        group.events.map((event) => [event.value, event] as const),
    ),
);

const ACTION_GROUPS: ActionGroupMeta[] = [
    {
        id: "puryfi",
        label: "PuryFi",
        description: "Control the PuryFi app.",
        icon: Eye,
        actions: [
            {
                key: "lockPuryfi",
                type: "puryfi.lock",
                title: "Lock PuryFi",
                ariaLabel: "Lock PuryFi with the stored or a generated password",
                description: "Use the stored password or generate a new one.",
                icon: LockKeyhole,
            },
            {
                key: "enablePuryfi",
                type: "puryfi.enable",
                title: "Enable PuryFi",
                ariaLabel: "Enable PuryFi",
                description: "Turn PuryFi on for this session.",
                icon: Power,
            },
            {
                key: "unlockPuryfi",
                type: "puryfi.unlock",
                title: "Unlock PuryFi",
                ariaLabel: "Unlock PuryFi with the stored password",
                description: "Unlock using the saved password.",
                icon: Unlock,
            },
            {
                key: "disablePuryfi",
                type: "puryfi.disable",
                title: "Disable PuryFi",
                ariaLabel: "Disable PuryFi",
                description: "Turn PuryFi off for this session.",
                icon: PowerOff,
            },
        ],
    },
    {
        id: "chaster",
        label: "Chaster",
        description: "Adjust the Chaster lock.",
        icon: LockKeyhole,
        actions: [
            {
                key: "freezeChaster",
                type: "chaster.freeze",
                title: "Freeze lock",
                ariaLabel: "Freeze the Chaster lock",
                description: "Pause the lock timer.",
                icon: Snowflake,
            },
            {
                key: "unfreezeChaster",
                type: "chaster.unfreeze",
                title: "Unfreeze lock",
                ariaLabel: "Unfreeze the Chaster lock",
                description: "Resume the lock timer.",
                icon: Sun,
            },
            {
                key: "toggleFreeze",
                type: "chaster.toggle_freeze",
                title: "Toggle freeze",
                ariaLabel: "Toggle the Chaster freeze state",
                description: "Flip between frozen and unfrozen.",
                icon: Shuffle,
            },
            {
                key: "pillory",
                type: "chaster.pillory",
                title: "Pillory",
                ariaLabel: "Put the wearer in pillory",
                description: "Temporarily display the wearer in pillory.",
                icon: Gavel,
            },
            {
                key: "timerVisibility",
                type: "chaster.set_timer_visibility",
                title: "Timer visibility",
                ariaLabel: "Show or hide the remaining time",
                description: "Choose what the wearer sees.",
                icon: Timer,
            },
            {
                key: "addTime",
                type: "chaster.add_time",
                title: "Add time",
                ariaLabel: "Add time to the Chaster lock",
                description: "Extend the Chaster lock.",
                icon: CirclePlus,
            },
            {
                key: "removeTime",
                type: "chaster.remove_time",
                title: "Remove time",
                ariaLabel: "Remove time from the Chaster lock",
                description: "Shorten the Chaster lock.",
                icon: CircleMinus,
            },
            {
                key: "writeLog",
                type: "chaster.log",
                title: "Write log",
                ariaLabel: "Write a Chaster log",
                description: "Add an entry to the Chaster log.",
                icon: ScrollText,
            },
        ],
    },
];

const SOURCE_META: Record<
    AutomationSource,
    {
        label: string;
        icon: EditorIcon;
        pill: string;
        tile: string;
        dot: string;
    }
> = {
    puryfi: {
        label: "PuryFi",
        icon: Eye,
        pill: "border-cyan-400/25 bg-cyan-400/10 text-cyan-200",
        tile: "border-cyan-400/20 bg-cyan-400/10 text-cyan-300",
        dot: "bg-cyan-400",
    },
    chaster: {
        label: "Chaster",
        icon: LockKeyhole,
        pill: "border-violet-400/25 bg-violet-400/10 text-violet-200",
        tile: "border-violet-400/20 bg-violet-400/10 text-violet-300",
        dot: "bg-violet-400",
    },
};

function conditionValue(
    trigger: AutomationTriggerSchema,
    field: string,
): unknown {
    return (trigger.conditions ?? []).find(
        (condition) => condition.field === field,
    )?.value;
}

function stateFromInitial(
    initial: AutomationSchema | AutomationCreateSchema | null | undefined,
): EditorState {
    if (!initial) return { ...DEFAULT_STATE };

    const trigger = initial.trigger;
    const actionTypes = new Set(initial.actions.map((action) => action.type));
    const labelsCondition = (trigger.conditions ?? []).find(
        (condition) => condition.field === "labels",
    );
    const labelsValue = labelsCondition?.value;
    const scoreValue = conditionValue(trigger, "score");
    const addTime = initial.actions.find(
        (action) => action.type === "chaster.add_time",
    );
    const removeTime = initial.actions.find(
        (action) => action.type === "chaster.remove_time",
    );
    const pillory = initial.actions.find(
        (action) => action.type === "chaster.pillory",
    );
    const timerVisibility = initial.actions.find(
        (action) => action.type === "chaster.set_timer_visibility",
    );
    const log = initial.actions.find(
        (action) => action.type === "chaster.log",
    );

    return {
        ...DEFAULT_STATE,
        name: initial.name,
        event: trigger.event,
        selectedLabels: Array.isArray(labelsValue)
            ? labelsValue.map(String)
            : labelsValue
              ? [String(labelsValue)]
              : [],
        labelMatch: labelsCondition?.op === "contains_any" ? "any" : "all",
        minScore:
            scoreValue !== undefined
                ? String(scoreValue)
                : String(trigger.min_score ?? 0.5),
        count: trigger.count ?? 1,
        windowMinutes: Math.round((trigger.window_seconds ?? 0) / 60),
        cooldownSeconds:
            trigger.event === "puryfi.media.scan"
                ? Math.max(5, initial.limits?.cooldown_seconds ?? 5)
                : Math.max(0, initial.limits?.cooldown_seconds ?? 0),
        maxPerDay: Math.max(0, initial.limits?.max_per_day ?? 0),
        enabled: initial.enabled,
        priority: initial.priority ?? 100,
        lockPuryfi: actionTypes.has("puryfi.lock"),
        enablePuryfi: actionTypes.has("puryfi.enable"),
        unlockPuryfi: actionTypes.has("puryfi.unlock"),
        disablePuryfi: actionTypes.has("puryfi.disable"),
        freezeChaster: actionTypes.has("chaster.freeze"),
        unfreezeChaster: actionTypes.has("chaster.unfreeze"),
        toggleFreeze: actionTypes.has("chaster.toggle_freeze"),
        pillory: Boolean(pillory),
        pilloryDuration: Number(pillory?.params?.duration ?? 300),
        pilloryReason: String(pillory?.params?.reason ?? ""),
        timerVisibility: Boolean(timerVisibility),
        displayRemainingTime:
            timerVisibility?.params?.display_remaining_time === undefined
                ? true
                : Boolean(timerVisibility.params.display_remaining_time),
        addTime: Boolean(addTime),
        addTimeSeconds: Number(addTime?.params?.seconds ?? 120),
        removeTime: Boolean(removeTime),
        removeTimeSeconds: Number(removeTime?.params?.seconds ?? 120),
        writeLog: Boolean(log),
        logTitle: String(log?.params?.title ?? "Automation triggered"),
        extraConditions: (trigger.conditions ?? []).filter(
            (condition) =>
                condition.field !== "labels" &&
                condition.field !== "score",
        ),
    };
}

function buildActions(state: EditorState): AutomationActionSchema[] {
    const actions: AutomationActionSchema[] = [];
    if (state.lockPuryfi) {
        actions.push({ type: "puryfi.lock", params: {}, on_failure: "stop" });
    }
    if (state.enablePuryfi) {
        actions.push({ type: "puryfi.enable", params: {}, on_failure: "stop" });
    }
    if (state.unlockPuryfi) {
        actions.push({ type: "puryfi.unlock", params: {}, on_failure: "stop" });
    }
    if (state.disablePuryfi) {
        actions.push({ type: "puryfi.disable", params: {}, on_failure: "stop" });
    }
    if (state.freezeChaster) {
        actions.push({ type: "chaster.freeze", params: {}, on_failure: "stop" });
    }
    if (state.unfreezeChaster) {
        actions.push({
            type: "chaster.unfreeze",
            params: {},
            on_failure: "stop",
        });
    }
    if (state.toggleFreeze) {
        actions.push({
            type: "chaster.toggle_freeze",
            params: {},
            on_failure: "stop",
        });
    }
    if (state.pillory) {
        const reason = state.pilloryReason.trim();
        actions.push({
            type: "chaster.pillory",
            params: {
                duration: Math.max(1, state.pilloryDuration),
                ...(reason ? { reason } : {}),
            },
            on_failure: "stop",
        });
    }
    if (state.timerVisibility) {
        actions.push({
            type: "chaster.set_timer_visibility",
            params: { display_remaining_time: state.displayRemainingTime },
            on_failure: "stop",
        });
    }
    if (state.addTime) {
        actions.push({
            type: "chaster.add_time",
            params: { seconds: Math.max(1, state.addTimeSeconds) },
            on_failure: "stop",
        });
    }
    if (state.removeTime) {
        actions.push({
            type: "chaster.remove_time",
            params: { seconds: Math.max(1, state.removeTimeSeconds) },
            on_failure: "stop",
        });
    }
    if (state.writeLog) {
        actions.push({
            type: "chaster.log",
            params: {
                title: state.logTitle.trim() || "Automation triggered",
                description: "",
            },
            on_failure: "continue",
        });
    }
    return actions;
}

function buildTrigger(state: EditorState): AutomationTriggerSchema {
    const conditions: NonNullable<AutomationTriggerSchema["conditions"]> = [
        ...state.extraConditions,
    ];
    if (
        state.event === "puryfi.media.scan" &&
        state.selectedLabels.length > 0
    ) {
        conditions.push({
            field: "labels",
            op: state.labelMatch === "any" ? "contains_any" : "contains_all",
            value: state.selectedLabels,
        });
    }

    const isMedia = state.event === "puryfi.media.scan";
    const parsedScore = Number(state.minScore);
    const minScore =
        isMedia && state.minScore.trim() !== "" && Number.isFinite(parsedScore)
            ? Math.min(1, Math.max(0, parsedScore))
            : 0;

    return {
        event: state.event,
        conditions,
        min_score: minScore,
        count: isMedia ? Math.max(1, state.count) : 1,
        window_seconds: isMedia ? Math.max(0, state.windowMinutes) * 60 : 0,
        count_mode: "images",
    };
}

function buildPayload(
    state: EditorState,
    name: string,
): AutomationCreateSchema {
    const isMedia = state.event === "puryfi.media.scan";
    return {
        name,
        enabled: state.enabled,
        priority: state.priority,
        trigger: buildTrigger(state),
        actions: buildActions(state),
        limits: {
            cooldown_seconds: isMedia
                ? Math.max(5, state.cooldownSeconds)
                : Math.max(0, state.cooldownSeconds),
            max_per_day: Math.max(0, state.maxPerDay),
        },
    };
}

export default function AutomationEditor({
    open,
    initial,
    labels,
    busy = false,
    onClose,
    onSave,
}: AutomationEditorProps) {
    const [state, setState] = useState<EditorState>(() =>
        stateFromInitial(initial),
    );
    const [error, setError] = useState<string | null>(null);
    const [labelQuery, setLabelQuery] = useState("");
    const nameRef = useRef<HTMLInputElement>(null);

    const labelNames = useMemo(
        () =>
            Object.fromEntries(
                labels.map((label) => [label.value, label.label]),
            ),
        [labels],
    );

    const filteredLabels = useMemo(() => {
        const query = labelQuery.trim().toLocaleLowerCase();
        if (!query) return labels;
        return labels.filter((label) =>
            `${label.label} ${label.value}`.toLocaleLowerCase().includes(query),
        );
    }, [labelQuery, labels]);

    const actions = useMemo(() => buildActions(state), [state]);
    const triggerPreview = useMemo(() => buildTrigger(state), [state]);

    const isMedia = state.event === "puryfi.media.scan";
    const isEditing = Boolean(initial && "id" in initial);
    const title = isEditing ? "Edit automation" : "New automation";
    const eventMeta = EVENT_META[state.event];
    const eventSource = eventMeta?.source ?? null;
    const EventIcon = eventMeta?.icon ?? Sparkles;
    const parsedScore = Number(state.minScore);
    const safeScore = Number.isFinite(parsedScore)
        ? Math.min(1, Math.max(0, parsedScore))
        : 0;
    const selectedActionCount = actions.length;
    const actionsStep = isMedia ? 3 : 2;
    const limitsStep = isMedia ? 4 : 3;

    const update = <K extends keyof EditorState>(
        key: K,
        value: EditorState[K],
    ) => {
        setError(null);
        setState((current) => ({ ...current, [key]: value }));
    };

    const toggleLabel = (value: string) => {
        setError(null);
        setState((current) => ({
            ...current,
            selectedLabels: current.selectedLabels.includes(value)
                ? current.selectedLabels.filter((label) => label !== value)
                : [...current.selectedLabels, value],
        }));
    };

    const handleEventChange = (nextEvent: string) => {
        setError(null);

        if (initial) {
            setState((current) => ({
                ...current,
                event: nextEvent,
                cooldownSeconds:
                    nextEvent === "puryfi.media.scan"
                        ? Math.max(5, current.cooldownSeconds)
                        : current.cooldownSeconds,
            }));
            return;
        }

        const defaults = {
            lockPuryfi: false,
            enablePuryfi: false,
            unlockPuryfi: false,
            disablePuryfi: false,
            freezeChaster: false,
            unfreezeChaster: false,
            toggleFreeze: false,
            pillory: false,
            timerVisibility: false,
            addTime: false,
            removeTime: false,
            writeLog: false,
        };
        if (nextEvent === "chaster.lock.unfrozen") {
            Object.assign(defaults, { unlockPuryfi: true, disablePuryfi: true });
        } else if (nextEvent === "puryfi.media.scan") {
            Object.assign(defaults, { addTime: true });
        } else if (nextEvent === "puryfi.connection.ready") {
            Object.assign(defaults, { lockPuryfi: true, enablePuryfi: true });
        } else if (LOG_ONLY_EVENTS.has(nextEvent)) {
            Object.assign(defaults, { writeLog: true });
        } else {
            Object.assign(defaults, { lockPuryfi: true, enablePuryfi: true });
        }

        setState((current) => ({
            ...current,
            event: nextEvent,
            cooldownSeconds:
                nextEvent === "puryfi.media.scan"
                    ? Math.max(5, current.cooldownSeconds)
                    : current.cooldownSeconds,
            extraConditions: [],
            ...defaults,
        }));
    };

    const handleSave = async () => {
        if (busy) return;

        const name = state.name.trim();
        if (!name) {
            setError("Give this automation a name.");
            nameRef.current?.focus();
            return;
        }

        if (actions.length === 0) {
            setError("Add at least one action before saving.");
            document
                .getElementById("automation-actions")
                ?.scrollIntoView?.({ behavior: "smooth", block: "start" });
            return;
        }

        setError(null);
        await onSave(buildPayload(state, name));
    };

    const handleSaveRef = useRef(handleSave);
    useEffect(() => {
        handleSaveRef.current = handleSave;
    });

    useEffect(() => {
        if (!open) return;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () => {
            document.body.style.overflow = previousOverflow;
        };
    }, [open]);

    useEffect(() => {
        if (!open) return;
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape" && !busy) {
                event.preventDefault();
                onClose();
                return;
            }
            if (
                event.key === "Enter" &&
                (event.metaKey || event.ctrlKey)
            ) {
                event.preventDefault();
                void handleSaveRef.current();
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [busy, onClose, open]);

    if (!open) return null;

    const requestClose = () => {
        if (!busy) onClose();
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 backdrop-blur-md sm:p-6"
            onClick={requestClose}
            role="presentation"
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="automation-editor-title"
                className="relative flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#15131D] shadow-2xl shadow-black/60"
                onClick={(event) => event.stopPropagation()}
            >
                <header className="relative flex items-start justify-between gap-3 border-b border-white/[0.06] px-4 py-4 sm:px-5">
                    <span
                        aria-hidden="true"
                        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/70 to-transparent"
                    />

                    <div className="flex min-w-0 items-center gap-3">
                        <div className="relative flex size-10 shrink-0 items-center justify-center rounded-xl border border-cyan-400/25 bg-gradient-to-br from-cyan-400/20 to-cyan-400/5 text-cyan-300 shadow-inner shadow-cyan-400/10">
                            <Sparkles className="size-4" />
                        </div>
                        <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                                <h2
                                    id="automation-editor-title"
                                    className="text-sm font-semibold tracking-tight text-white"
                                >
                                    {title}
                                </h2>
                                <span className="rounded-full border border-white/[0.08] bg-white/[0.03] px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.1em] text-slate-400">
                                    {isEditing ? "Editing" : "New rule"}
                                </span>
                            </div>
                            <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-slate-400">
                                Pick a trigger, choose actions, and PuryFi
                                handles the rest.
                            </p>
                        </div>
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                        <button
                            type="button"
                            role="switch"
                            aria-checked={state.enabled}
                            aria-label="Automation enabled"
                            title={
                                state.enabled
                                    ? "Pause this automation"
                                    : "Activate this automation"
                            }
                            onClick={() => update("enabled", !state.enabled)}
                            className={cn(
                                "group inline-flex h-8 items-center gap-2 rounded-full border px-2.5 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[#15131D]",
                                state.enabled
                                    ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200"
                                    : "border-white/10 bg-white/[0.03] text-slate-400 hover:border-white/20",
                            )}
                        >
                            {state.enabled ? (
                                <Play className="size-3 fill-current" />
                            ) : (
                                <Pause className="size-3" />
                            )}
                            <span className="hidden text-[11px] font-semibold sm:inline">
                                {state.enabled ? "Active" : "Paused"}
                            </span>
                            <span
                                aria-hidden="true"
                                className={cn(
                                    "relative flex h-4 w-7 items-center rounded-full p-0.5 transition-colors",
                                    state.enabled
                                        ? "bg-emerald-500"
                                        : "bg-slate-700",
                                )}
                            >
                                <span
                                    className={cn(
                                        "block size-3 rounded-full bg-white shadow-sm transition-transform",
                                        state.enabled
                                            ? "translate-x-3"
                                            : "translate-x-0",
                                    )}
                                />
                            </span>
                        </button>

                        <button
                            type="button"
                            onClick={requestClose}
                            disabled={busy}
                            aria-label="Close editor"
                            className="flex size-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-white/[0.05] hover:text-white disabled:opacity-50"
                        >
                            <X className="size-4" />
                        </button>
                    </div>
                </header>

                <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_19rem]">
                    <div className="min-h-0 space-y-4 overflow-y-auto px-4 py-4 sm:px-5 sm:py-5">
                        <EditorSection
                            step={1}
                            icon={Pencil}
                            title="Name & trigger"
                            description="Give this rule a clear name and choose when it should run."
                        >
                            <label
                                htmlFor="automation-name"
                                className="block space-y-1.5"
                            >
                                <span className="flex items-center justify-between gap-2">
                                    <span className="text-[11px] font-medium text-slate-300">
                                        Name
                                    </span>
                                    <span className="text-[10px] tabular-nums text-slate-600">
                                        {state.name.length}/120
                                    </span>
                                </span>
                                <Input
                                    ref={nameRef}
                                    id="automation-name"
                                    autoFocus
                                    value={state.name}
                                    maxLength={120}
                                    onChange={(event) =>
                                        update("name", event.target.value)
                                    }
                                    placeholder="e.g. Eyes and Belly"
                                    className="h-11 rounded-xl border-white/10 bg-[#0F0E16] text-white placeholder:text-slate-600 hover:border-white/20 focus-visible:border-cyan-400/50 focus-visible:ring-4 focus-visible:ring-cyan-400/10"
                                />
                            </label>

                            <div className="space-y-1.5">
                                <div className="flex items-center justify-between gap-2">
                                    <label
                                        htmlFor="automation-event"
                                        className="text-[11px] font-medium text-slate-300"
                                    >
                                        When this happens
                                    </label>
                                    {eventSource ? (
                                        <SourcePill source={eventSource} />
                                    ) : null}
                                </div>
                                <div className="relative">
                                    <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-500">
                                        <EventIcon className="size-4" />
                                    </span>
                                    <select
                                        id="automation-event"
                                        aria-label="Trigger event"
                                        aria-describedby="automation-event-description"
                                        value={state.event}
                                        onChange={(event) =>
                                            handleEventChange(
                                                event.target.value,
                                            )
                                        }
                                        className="h-11 w-full appearance-none rounded-xl border border-white/10 bg-[#0F0E16] pl-10 pr-10 text-sm text-white outline-none transition-colors hover:border-white/20 focus:border-cyan-400/50 focus:ring-4 focus:ring-cyan-400/10"
                                    >
                                        {EVENT_GROUPS.map((group) => (
                                            <optgroup
                                                key={group.id}
                                                label={group.label}
                                            >
                                                {group.events.map((event) => (
                                                    <option
                                                        key={event.value}
                                                        value={event.value}
                                                    >
                                                        {event.label}
                                                    </option>
                                                ))}
                                            </optgroup>
                                        ))}
                                    </select>
                                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                                </div>
                                <p
                                    id="automation-event-description"
                                    className="text-[11px] leading-relaxed text-slate-500"
                                >
                                    {eventMeta?.description ??
                                        "Choose the event that starts this automation."}
                                </p>
                            </div>
                        </EditorSection>

                        {isMedia ? (
                            <EditorSection
                                step={2}
                                icon={ImageIcon}
                                title="Media conditions"
                                description="Filter which analysed images can trigger this rule."
                                badge={
                                    <span className="rounded-full border border-cyan-400/20 bg-cyan-400/[0.08] px-2 py-0.5 text-[9px] font-semibold text-cyan-200">
                                        {state.selectedLabels.length === 0
                                            ? "Any image"
                                            : `${state.selectedLabels.length} label${state.selectedLabels.length > 1 ? "s" : ""}`}
                                    </span>
                                }
                            >
                                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                                    <div className="relative min-w-0 flex-1">
                                        <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-slate-500" />
                                        <Input
                                            value={labelQuery}
                                            onChange={(event) =>
                                                setLabelQuery(
                                                    event.target.value,
                                                )
                                            }
                                            placeholder="Search labels…"
                                            aria-label="Search labels"
                                            className="h-10 rounded-xl border-white/10 bg-[#0F0E16] pl-9 pr-9 text-xs text-white placeholder:text-slate-600 focus-visible:border-cyan-400/50 focus-visible:ring-4 focus-visible:ring-cyan-400/10"
                                        />
                                        {labelQuery ? (
                                            <button
                                                type="button"
                                                onClick={() =>
                                                    setLabelQuery("")
                                                }
                                                aria-label="Clear label search"
                                                className="absolute right-2 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 hover:bg-white/[0.05] hover:text-white"
                                            >
                                                <X className="size-3.5" />
                                            </button>
                                        ) : null}
                                    </div>

                                    {state.selectedLabels.length > 0 ? (
                                        <div className="flex shrink-0 items-center gap-2">
                                            <span className="text-[10px] text-slate-500">
                                                {state.selectedLabels.length}{" "}
                                                selected
                                            </span>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="sm"
                                                onClick={() =>
                                                    setState((current) => ({
                                                        ...current,
                                                        selectedLabels: [],
                                                    }))
                                                }
                                                className="h-8 rounded-lg px-2 text-[10px] text-slate-400 hover:bg-white/[0.06] hover:text-white"
                                            >
                                                Clear
                                            </Button>
                                        </div>
                                    ) : null}
                                </div>

                                <div className="flex flex-wrap items-center gap-2">
                                    <span className="text-[11px] text-slate-400">
                                        Match
                                    </span>
                                    <div
                                        role="group"
                                        aria-label="Label match mode"
                                        className="inline-flex items-center rounded-lg border border-white/[0.07] bg-black/20 p-0.5"
                                    >
                                        {(
                                            [
                                                ["all", "all labels"],
                                                ["any", "any label"],
                                            ] as const
                                        ).map(([value, label]) => (
                                            <button
                                                key={value}
                                                type="button"
                                                aria-pressed={
                                                    state.labelMatch === value
                                                }
                                                onClick={() =>
                                                    update(
                                                        "labelMatch",
                                                        value,
                                                    )
                                                }
                                                className={cn(
                                                    "rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors",
                                                    state.labelMatch === value
                                                        ? "bg-cyan-400/15 text-cyan-200"
                                                        : "text-slate-500 hover:text-slate-300",
                                                )}
                                            >
                                                {label}
                                            </button>
                                        ))}
                                    </div>
                                    <span className="text-[10px] text-slate-600">
                                        Combine the selected labels.
                                    </span>
                                </div>

                                <div className="grid max-h-56 grid-cols-1 gap-1.5 overflow-y-auto pr-1 sm:grid-cols-2">
                                    {filteredLabels.map((label) => {
                                        const selected =
                                            state.selectedLabels.includes(
                                                label.value,
                                            );
                                        return (
                                            <label
                                                key={label.value}
                                                className={cn(
                                                    "group flex cursor-pointer items-center gap-2 rounded-lg border px-2 py-1.5 transition-colors focus-within:ring-2 focus-within:ring-cyan-400/40",
                                                    selected
                                                        ? "border-cyan-400/25 bg-cyan-400/[0.08]"
                                                        : "border-white/[0.06] bg-black/10 hover:border-white/15 hover:bg-white/[0.02]",
                                                )}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={selected}
                                                    onChange={() =>
                                                        toggleLabel(
                                                            label.value,
                                                        )
                                                    }
                                                    className="sr-only"
                                                />
                                                {LABEL_IMAGES[label.value] ? (
                                                    <img
                                                        src={
                                                            LABEL_IMAGES[
                                                                label.value
                                                            ]
                                                        }
                                                        alt=""
                                                        width={24}
                                                        height={24}
                                                        className="size-6 shrink-0 rounded object-contain"
                                                        loading="lazy"
                                                    />
                                                ) : (
                                                    <span className="flex size-6 shrink-0 items-center justify-center rounded-md border border-white/[0.07] bg-white/[0.02] text-slate-500">
                                                        <Eye className="size-3" />
                                                    </span>
                                                )}
                                                <span className="min-w-0 flex-1 truncate text-[11px] leading-snug text-slate-300">
                                                    {labelNames[label.value] ??
                                                        label.value}
                                                </span>
                                                <span
                                                    aria-hidden="true"
                                                    className={cn(
                                                        "flex size-4 shrink-0 items-center justify-center rounded-full border transition-colors",
                                                        selected
                                                            ? "border-cyan-400 bg-cyan-400 text-slate-950"
                                                            : "border-white/15 text-transparent",
                                                    )}
                                                >
                                                    <Check className="size-2.5" />
                                                </span>
                                            </label>
                                        );
                                    })}

                                    {filteredLabels.length === 0 ? (
                                        <p className="col-span-full rounded-lg border border-dashed border-white/10 px-3 py-4 text-center text-[11px] text-slate-500">
                                            No labels match “{labelQuery}”.
                                        </p>
                                    ) : null}
                                </div>

                                <div className="grid gap-3 rounded-xl border border-white/[0.06] bg-black/15 p-3 sm:grid-cols-3">
                                    <div>
                                        <div className="flex items-center justify-between gap-2">
                                            <span className="text-[11px] text-slate-400">
                                                Minimum score
                                            </span>
                                            <span className="font-mono text-[10px] font-semibold text-cyan-300">
                                                {safeScore.toFixed(2)}
                                            </span>
                                        </div>
                                        <input
                                            type="range"
                                            aria-label="Minimum detection score"
                                            min={0}
                                            max={1}
                                            step={0.05}
                                            value={safeScore}
                                            onChange={(event) =>
                                                update(
                                                    "minScore",
                                                    event.target.value,
                                                )
                                            }
                                            className="mt-2.5 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-cyan-400"
                                        />
                                        <p className="mt-1.5 text-[10px] leading-relaxed text-slate-600">
                                            0 ignores confidence.
                                        </p>
                                    </div>

                                    <label className="space-y-1.5">
                                        <span className="text-[11px] text-slate-400">
                                            Matching images
                                        </span>
                                        <NumberInput
                                            id="automation-count"
                                            value={state.count}
                                            onChange={(value) =>
                                                update("count", value)
                                            }
                                            min={1}
                                            max={10_000}
                                        />
                                        <span className="block text-[10px] text-slate-600">
                                            Images needed to trigger.
                                        </span>
                                    </label>

                                    <label className="space-y-1.5">
                                        <span className="text-[11px] text-slate-400">
                                            Within (minutes)
                                        </span>
                                        <NumberInput
                                            id="automation-window"
                                            value={state.windowMinutes}
                                            onChange={(value) =>
                                                update(
                                                    "windowMinutes",
                                                    value,
                                                )
                                            }
                                            min={0}
                                            max={1_440}
                                        />
                                        <span className="block text-[10px] text-slate-600">
                                            0 = no time limit.
                                        </span>
                                    </label>
                                </div>
                            </EditorSection>
                        ) : null}

                        <EditorSection
                            id="automation-actions"
                            step={actionsStep}
                            icon={Zap}
                            title="Actions"
                            description="Choose what PuryFi should do when the trigger fires."
                            badge={
                                <span
                                    className={cn(
                                        "rounded-full border px-2 py-0.5 text-[9px] font-semibold",
                                        selectedActionCount > 0
                                            ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-200"
                                            : "border-amber-400/20 bg-amber-400/10 text-amber-200",
                                    )}
                                >
                                    {selectedActionCount} selected
                                </span>
                            }
                        >
                            <div className="space-y-4">
                                {ACTION_GROUPS.map((group) => {
                                    const GroupIcon = group.icon;
                                    return (
                                        <div key={group.id}>
                                            <div className="mb-2 flex items-center gap-2">
                                                <span
                                                    className={cn(
                                                        "flex size-6 items-center justify-center rounded-md border",
                                                        SOURCE_META[group.id]
                                                            .tile,
                                                    )}
                                                >
                                                    <GroupIcon className="size-3" />
                                                </span>
                                                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                                    {group.label}
                                                </p>
                                                <span className="hidden text-[10px] text-slate-600 sm:inline">
                                                    {group.description}
                                                </span>
                                            </div>
                                            <div className="grid gap-2 sm:grid-cols-2">
                                                {group.actions.map((action) => (
                                                    <ActionCard
                                                        key={action.key}
                                                        meta={action}
                                                        checked={
                                                            state[action.key]
                                                        }
                                                        onToggle={(checked) =>
                                                            update(
                                                                action.key,
                                                                checked,
                                                            )
                                                        }
                                                    />
                                                ))}
                                            </div>
                                        </div>
                                    );
                                })}

                                {state.pillory ||
                                state.timerVisibility ||
                                state.addTime ||
                                state.removeTime ||
                                state.writeLog ? (
                                    <div className="space-y-2 rounded-xl border border-white/[0.05] bg-black/15 p-3">
                                        <div className="flex items-center gap-2">
                                            <ShieldCheck className="size-3.5 text-cyan-300" />
                                            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                                Action options
                                            </p>
                                        </div>

                                        {state.pillory ? (
                                            <OptionPanel
                                                icon={Gavel}
                                                title="Pillory options"
                                            >
                                                <div className="grid gap-2 sm:grid-cols-[minmax(0,150px)_minmax(0,1fr)]">
                                                    <label className="space-y-1.5">
                                                        <span className="text-[11px] text-slate-400">
                                                            Duration
                                                        </span>
                                                        <NumberInput
                                                            id="automation-pillory-duration"
                                                            value={
                                                                state.pilloryDuration
                                                            }
                                                            onChange={(value) =>
                                                                update(
                                                                    "pilloryDuration",
                                                                    value,
                                                                )
                                                            }
                                                            min={1}
                                                            max={604_800}
                                                            suffix="seconds"
                                                        />
                                                    </label>
                                                    <label className="space-y-1.5">
                                                        <span className="text-[11px] text-slate-400">
                                                            Reason
                                                        </span>
                                                        <Input
                                                            value={
                                                                state.pilloryReason
                                                            }
                                                            onChange={(event) =>
                                                                update(
                                                                    "pilloryReason",
                                                                    event.target
                                                                        .value,
                                                                )
                                                            }
                                                            placeholder="Reason (optional)"
                                                            className="h-11 rounded-xl border-white/10 bg-[#0F0E16] text-white placeholder:text-slate-600 focus-visible:border-cyan-400/50 focus-visible:ring-4 focus-visible:ring-cyan-400/10"
                                                        />
                                                    </label>
                                                </div>
                                            </OptionPanel>
                                        ) : null}

                                        {state.timerVisibility ? (
                                            <OptionPanel
                                                icon={Timer}
                                                title="Timer visibility"
                                            >
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <span className="text-[11px] text-slate-400">
                                                        Remaining time
                                                    </span>
                                                    <select
                                                        value={
                                                            state.displayRemainingTime
                                                                ? "show"
                                                                : "hide"
                                                        }
                                                        onChange={(event) =>
                                                            update(
                                                                "displayRemainingTime",
                                                                event.target
                                                                    .value ===
                                                                    "show",
                                                            )
                                                        }
                                                        aria-label="Remaining time visibility"
                                                        className="h-9 rounded-lg border border-white/10 bg-[#0F0E16] px-3 text-xs text-white outline-none focus:border-cyan-400/50"
                                                    >
                                                        <option value="show">
                                                            Show to the wearer
                                                        </option>
                                                        <option value="hide">
                                                            Hide from the wearer
                                                        </option>
                                                    </select>
                                                </div>
                                            </OptionPanel>
                                        ) : null}

                                        {state.addTime ? (
                                            <OptionPanel
                                                icon={CirclePlus}
                                                title="Added time"
                                            >
                                                <div className="flex flex-wrap items-center gap-3">
                                                    <span className="text-[11px] text-slate-400">
                                                        Add
                                                    </span>
                                                    <NumberInput
                                                        id="automation-add-time"
                                                        value={
                                                            state.addTimeSeconds
                                                        }
                                                        onChange={(value) =>
                                                            update(
                                                                "addTimeSeconds",
                                                                value,
                                                            )
                                                        }
                                                        min={1}
                                                        max={604_800}
                                                        suffix="seconds"
                                                        className="max-w-48"
                                                    />
                                                    <span className="text-[11px] text-slate-500">
                                                        to the Chaster lock.
                                                    </span>
                                                </div>
                                            </OptionPanel>
                                        ) : null}

                                        {state.removeTime ? (
                                            <OptionPanel
                                                icon={CircleMinus}
                                                title="Removed time"
                                            >
                                                <div className="flex flex-wrap items-center gap-3">
                                                    <span className="text-[11px] text-slate-400">
                                                        Remove
                                                    </span>
                                                    <NumberInput
                                                        id="automation-remove-time"
                                                        value={
                                                            state.removeTimeSeconds
                                                        }
                                                        onChange={(value) =>
                                                            update(
                                                                "removeTimeSeconds",
                                                                value,
                                                            )
                                                        }
                                                        min={1}
                                                        max={604_800}
                                                        suffix="seconds"
                                                        className="max-w-48"
                                                    />
                                                    <span className="text-[11px] text-slate-500">
                                                        from the Chaster lock.
                                                    </span>
                                                </div>
                                            </OptionPanel>
                                        ) : null}

                                        {state.writeLog ? (
                                            <OptionPanel
                                                icon={ScrollText}
                                                title="Chaster log"
                                            >
                                                <Input
                                                    value={state.logTitle}
                                                    onChange={(event) =>
                                                        update(
                                                            "logTitle",
                                                            event.target.value,
                                                        )
                                                    }
                                                    placeholder="Log title"
                                                    className="h-10 rounded-xl border-white/10 bg-[#0F0E16] text-white placeholder:text-slate-600 focus-visible:border-cyan-400/50 focus-visible:ring-4 focus-visible:ring-cyan-400/10"
                                                />
                                            </OptionPanel>
                                        ) : null}
                                    </div>
                                ) : null}
                            </div>
                        </EditorSection>

                        {isMedia ? (
                            <EditorSection
                                step={limitsStep}
                                icon={Gauge}
                                title="Run limits"
                                description="Prevent repeated triggers and runaway actions."
                            >
                                <div className="grid gap-3 sm:grid-cols-2">
                                    <label className="space-y-1.5">
                                        <span className="text-[11px] font-medium text-slate-300">
                                            Cooldown before running again
                                        </span>
                                        <NumberInput
                                            id="automation-cooldown"
                                            value={state.cooldownSeconds}
                                            onChange={(value) =>
                                                update(
                                                    "cooldownSeconds",
                                                    Math.max(5, value),
                                                )
                                            }
                                            min={5}
                                            max={604_800}
                                            suffix="seconds"
                                        />
                                        <span className="block text-[10px] text-slate-600">
                                            Minimum 5 seconds for media
                                            automations.
                                        </span>
                                    </label>

                                    <label className="space-y-1.5">
                                        <span className="text-[11px] font-medium text-slate-300">
                                            Maximum runs per day
                                        </span>
                                        <NumberInput
                                            id="automation-max-per-day"
                                            value={state.maxPerDay}
                                            onChange={(value) =>
                                                update("maxPerDay", value)
                                            }
                                            min={0}
                                            max={1_000}
                                            suffix="/ day"
                                        />
                                        <span className="block text-[10px] text-slate-600">
                                            0 = unlimited.
                                        </span>
                                    </label>
                                </div>
                            </EditorSection>
                        ) : null}
                    </div>

                    <aside
                        aria-label="Automation preview"
                        className="hidden min-h-0 flex-col overflow-y-auto border-l border-white/[0.06] bg-black/10 p-4 lg:flex"
                    >
                        <div className="flex items-center justify-between gap-2">
                            <div>
                                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                                    Live preview
                                </p>
                                <p className="mt-0.5 text-[11px] text-slate-500">
                                    How this rule will read.
                                </p>
                            </div>
                            <span
                                className={cn(
                                    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.08em]",
                                    state.enabled
                                        ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-300"
                                        : "border-white/10 bg-white/[0.04] text-slate-400",
                                )}
                            >
                                <span
                                    className={cn(
                                        "size-1.5 rounded-full",
                                        state.enabled
                                            ? "bg-emerald-400"
                                            : "bg-slate-500",
                                    )}
                                />
                                {state.enabled ? "Active" : "Paused"}
                            </span>
                        </div>

                        <div className="mt-4 overflow-hidden rounded-2xl border border-white/[0.07] bg-gradient-to-b from-[#1B1826] to-[#121019]">
                            <div className="border-b border-white/[0.06] px-3.5 py-3">
                                <p className="truncate text-sm font-semibold text-white">
                                    {state.name.trim() || "Untitled automation"}
                                </p>
                                <p className="mt-0.5 text-[10px] text-slate-500">
                                    {selectedActionCount} action
                                    {selectedActionCount === 1 ? "" : "s"} ·{" "}
                                    {eventSource
                                        ? SOURCE_META[eventSource].label
                                        : "Automation"}
                                </p>
                            </div>

                            <div className="p-3.5">
                                <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3">
                                    <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                                        When
                                    </p>
                                    <div className="mt-1.5 flex items-start gap-2">
                                        <span
                                            className={cn(
                                                "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-lg border",
                                                eventSource
                                                    ? SOURCE_META[eventSource]
                                                          .tile
                                                    : "border-white/10 bg-white/[0.03] text-slate-400",
                                            )}
                                        >
                                            <EventIcon className="size-3" />
                                        </span>
                                        <div className="min-w-0">
                                            <p className="text-xs font-medium leading-snug text-slate-100">
                                                {eventName(state.event)}
                                            </p>
                                            <p className="mt-0.5 text-[10px] leading-relaxed text-slate-500">
                                                {triggerSummary(
                                                    triggerPreview,
                                                    labelNames,
                                                )}
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                <div className="my-1.5 flex justify-center">
                                    <span className="flex size-5 items-center justify-center rounded-full border border-white/[0.07] bg-white/[0.025] text-slate-500">
                                        <ArrowDown className="size-3" />
                                    </span>
                                </div>

                                <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3">
                                    <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                                        Then
                                    </p>
                                    {actions.length > 0 ? (
                                        <ul className="mt-1.5 flex flex-col gap-1.5">
                                            {actions.map((action, index) => {
                                                const source =
                                                    action.type.startsWith(
                                                        "puryfi.",
                                                    )
                                                        ? "puryfi"
                                                        : "chaster";
                                                return (
                                                    <li
                                                        key={`${action.type}-${index}`}
                                                        className="flex items-start gap-1.5"
                                                    >
                                                        <span
                                                            className={cn(
                                                                "mt-1 size-1.5 shrink-0 rounded-full",
                                                                SOURCE_META[
                                                                    source
                                                                ].dot,
                                                            )}
                                                        />
                                                        <div className="min-w-0">
                                                            <p className="text-[11px] font-medium leading-snug text-slate-200">
                                                                {actionName(
                                                                    action.type,
                                                                )}
                                                            </p>
                                                            <p
                                                                className="mt-0.5 line-clamp-2 text-[10px] leading-relaxed text-slate-500"
                                                                title={actionSummary(
                                                                    action,
                                                                )}
                                                            >
                                                                {actionSummary(
                                                                    action,
                                                                )}
                                                            </p>
                                                        </div>
                                                    </li>
                                                );
                                            })}
                                        </ul>
                                    ) : (
                                        <p className="mt-1.5 text-[11px] text-slate-500">
                                            No actions selected yet.
                                        </p>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="mt-4 rounded-2xl border border-white/[0.06] bg-white/[0.015] p-3.5">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                                Details
                            </p>
                            <dl className="mt-2 space-y-1.5 text-[11px]">
                                <div className="flex items-center justify-between gap-2">
                                    <dt className="text-slate-500">Status</dt>
                                    <dd
                                        className={
                                            state.enabled
                                                ? "font-medium text-emerald-300"
                                                : "font-medium text-slate-400"
                                        }
                                    >
                                        {state.enabled ? "Active" : "Paused"}
                                    </dd>
                                </div>
                                <div className="flex items-center justify-between gap-2">
                                    <dt className="text-slate-500">Actions</dt>
                                    <dd className="font-medium text-slate-300">
                                        {selectedActionCount}
                                    </dd>
                                </div>
                                {isMedia ? (
                                    <>
                                        <div className="flex items-center justify-between gap-2">
                                            <dt className="text-slate-500">
                                                Cooldown
                                            </dt>
                                            <dd className="font-medium text-slate-300">
                                                {state.cooldownSeconds}s
                                            </dd>
                                        </div>
                                        <div className="flex items-center justify-between gap-2">
                                            <dt className="text-slate-500">
                                                Max / day
                                            </dt>
                                            <dd className="font-medium text-slate-300">
                                                {state.maxPerDay > 0
                                                    ? state.maxPerDay
                                                    : "Unlimited"}
                                            </dd>
                                        </div>
                                    </>
                                ) : null}
                            </dl>
                        </div>

                        <div className="mt-auto pt-4">
                            <div className="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] p-3">
                                <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-cyan-300">
                                    <Sparkles className="size-3" />
                                    Tip
                                </div>
                                <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
                                    Pause a rule at any time without deleting
                                    it. Changes apply when you save.
                                </p>
                            </div>
                        </div>
                    </aside>
                </div>

                <footer className="border-t border-white/[0.06] bg-[#14121B] px-4 py-3 sm:px-5">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                        <div className="min-w-0">
                            {error ? (
                                <p
                                    role="alert"
                                    className="rounded-lg border border-rose-400/20 bg-rose-400/[0.07] px-3 py-2 text-xs text-rose-200"
                                >
                                    {error}
                                </p>
                            ) : (
                                <p className="hidden items-center gap-1.5 text-[10px] text-slate-500 sm:flex">
                                    <Clock3 className="size-3" />
                                    Tip:{" "}
                                    <kbd className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5 font-sans text-[9px] text-slate-400">
                                        Ctrl
                                    </kbd>
                                    <span>/</span>
                                    <kbd className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5 font-sans text-[9px] text-slate-400">
                                        ⌘
                                    </kbd>
                                    <span>+</span>
                                    <kbd className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5 font-sans text-[9px] text-slate-400">
                                        Enter
                                    </kbd>{" "}
                                    to save
                                </p>
                            )}
                        </div>

                        <div className="flex items-center justify-end gap-2">
                            <Button
                                type="button"
                                variant="ghost"
                                onClick={requestClose}
                                disabled={busy}
                                className="h-10 rounded-xl px-3.5 text-slate-400 hover:bg-white/[0.05] hover:text-white"
                            >
                                Cancel
                            </Button>
                            <Button
                                type="button"
                                onClick={handleSave}
                                disabled={busy}
                                className="h-10 min-w-40 rounded-xl bg-cyan-500 px-4 font-semibold text-slate-950 shadow-lg shadow-cyan-500/20 hover:bg-cyan-400"
                            >
                                {busy ? (
                                    <LoaderCircle className="animate-spin" />
                                ) : (
                                    <Save />
                                )}
                                Save automation
                            </Button>
                        </div>
                    </div>
                </footer>
            </div>
        </div>
    );
}

function EditorSection({
    id,
    step,
    icon: Icon,
    title,
    description,
    badge,
    children,
}: {
    id?: string;
    step: number;
    icon: EditorIcon;
    title: string;
    description: string;
    badge?: ReactNode;
    children: ReactNode;
}) {
    return (
        <section
            id={id}
            className="overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.02]"
        >
            <header className="flex items-start gap-3 border-b border-white/[0.05] bg-black/[0.06] px-4 py-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-xl border border-cyan-400/15 bg-cyan-400/[0.07] text-cyan-300">
                    <Icon className="size-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                        <div className="min-w-0">
                            <p className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                                Step {step}
                            </p>
                            <h3 className="text-xs font-semibold text-white">
                                {title}
                            </h3>
                        </div>
                        {badge}
                    </div>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                        {description}
                    </p>
                </div>
            </header>
            <div className="space-y-4 p-4">{children}</div>
        </section>
    );
}

function SourcePill({ source }: { source: AutomationSource }) {
    const meta = SOURCE_META[source];
    const Icon = meta.icon;
    return (
        <span
            className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.08em]",
                meta.pill,
            )}
        >
            <Icon className="size-2.5" />
            {meta.label}
        </span>
    );
}

function ActionCard({
    meta,
    checked,
    onToggle,
}: {
    meta: ActionMeta;
    checked: boolean;
    onToggle: (checked: boolean) => void;
}) {
    const Icon = meta.icon;
    return (
        <label
            className={cn(
                "group relative flex cursor-pointer items-start gap-2.5 rounded-xl border p-2.5 transition-colors focus-within:ring-2 focus-within:ring-cyan-400/40",
                checked
                    ? "border-cyan-400/25 bg-cyan-400/[0.06]"
                    : "border-white/[0.06] bg-black/10 hover:border-white/15 hover:bg-white/[0.03]",
            )}
        >
            <input
                type="checkbox"
                aria-label={meta.ariaLabel}
                checked={checked}
                onChange={(event) => onToggle(event.target.checked)}
                className="sr-only"
            />
            <span
                className={cn(
                    "flex size-8 shrink-0 items-center justify-center rounded-lg border transition-colors",
                    checked
                        ? "border-cyan-400/25 bg-cyan-400/10 text-cyan-300"
                        : "border-white/[0.07] bg-white/[0.02] text-slate-500",
                )}
            >
                <Icon className="size-3.5" />
            </span>
            <span className="min-w-0 flex-1">
                <span className="block text-[11px] font-semibold text-slate-200">
                    {meta.title}
                </span>
                <span className="mt-0.5 block text-[10px] leading-relaxed text-slate-500">
                    {meta.description}
                </span>
            </span>
            <span
                aria-hidden="true"
                className={cn(
                    "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors",
                    checked
                        ? "border-cyan-400 bg-cyan-400 text-slate-950"
                        : "border-white/15 bg-black/20 text-transparent",
                )}
            >
                <Check className="size-3" />
            </span>
        </label>
    );
}

function OptionPanel({
    icon: Icon,
    title,
    children,
}: {
    icon: EditorIcon;
    title: string;
    children: ReactNode;
}) {
    return (
        <div className="rounded-xl border border-white/[0.07] bg-[#121019] p-3">
            <div className="mb-2.5 flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-md border border-white/[0.08] bg-white/[0.03] text-slate-400">
                    <Icon className="size-3" />
                </span>
                <p className="text-[11px] font-semibold text-slate-200">
                    {title}
                </p>
            </div>
            {children}
        </div>
    );
}
