import { useMemo, useState } from "react";
import { LoaderCircle, Save, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import NumberInput from "@/components/ui/number-input";
import { LABEL_IMAGES } from "@/lib/automations";
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

interface EditorState {
    name: string;
    event: string;
    selectedLabels: string[];
    minScore: string;
    count: number;
    windowMinutes: number;
    cooldownSeconds: number;
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
    minScore: "0.5",
    count: 1,
    windowMinutes: 0,
    cooldownSeconds: 5,
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

function conditionValue(trigger: AutomationTriggerSchema, field: string): unknown {
    return (trigger.conditions ?? []).find((condition) => condition.field === field)?.value;
}

function stateFromInitial(
    initial: AutomationSchema | AutomationCreateSchema | null | undefined,
): EditorState {
    if (!initial) return { ...DEFAULT_STATE };

    const trigger = initial.trigger;
    const actionTypes = new Set(initial.actions.map((action) => action.type));
    const labelsValue = conditionValue(trigger, "labels");
    const scoreValue = conditionValue(trigger, "score");
    const addTime = initial.actions.find((action) => action.type === "chaster.add_time");
    const removeTime = initial.actions.find((action) => action.type === "chaster.remove_time");
    const pillory = initial.actions.find((action) => action.type === "chaster.pillory");
    const timerVisibility = initial.actions.find(
        (action) => action.type === "chaster.set_timer_visibility",
    );
    const log = initial.actions.find((action) => action.type === "chaster.log");

    return {
        ...DEFAULT_STATE,
        name: initial.name,
        event: trigger.event,
        selectedLabels: Array.isArray(labelsValue)
            ? labelsValue.map(String)
            : labelsValue
                ? [String(labelsValue)]
                : [],
        minScore:
            scoreValue !== undefined
                ? String(scoreValue)
                : String(trigger.min_score ?? 0.5),
        count: trigger.count ?? 1,
        windowMinutes: Math.round((trigger.window_seconds ?? 0) / 60),
        cooldownSeconds: Math.max(5, initial.limits?.cooldown_seconds ?? 5),
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
                condition.field !== "labels" && condition.field !== "score",
        ),
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
    const [state, setState] = useState<EditorState>(() => stateFromInitial(initial));
    const [error, setError] = useState<string | null>(null);

    const labelNames = useMemo(
        () => Object.fromEntries(labels.map((label) => [label.value, label.label])),
        [labels],
    );

    if (!open) return null;

    const update = <K extends keyof EditorState>(key: K, value: EditorState[K]) => {
        setState((current) => ({ ...current, [key]: value }));
    };

    const toggleLabel = (value: string) => {
        setState((current) => ({
            ...current,
            selectedLabels: current.selectedLabels.includes(value)
                ? current.selectedLabels.filter((label) => label !== value)
                : [...current.selectedLabels, value],
        }));
    };

    const handleEventChange = (nextEvent: string) => {
        if (initial) {
            update("event", nextEvent);
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
            extraConditions: [],
            ...defaults,
        }));
    };

    const handleSave = async () => {
        const name = state.name.trim();
        if (!name) {
            setError("Give this automation a name.");
            return;
        }

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
            actions.push({ type: "chaster.unfreeze", params: {}, on_failure: "stop" });
        }
        if (state.toggleFreeze) {
            actions.push({ type: "chaster.toggle_freeze", params: {}, on_failure: "stop" });
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

        if (actions.length === 0) {
            setError("Add at least one action.");
            return;
        }

        const conditions: NonNullable<AutomationTriggerSchema["conditions"]> = [
            ...state.extraConditions,
        ];
        if (state.event === "puryfi.media.scan" && state.selectedLabels.length > 0) {
            conditions.push({
                field: "labels",
                op: "contains_all",
                value: state.selectedLabels,
            });
        }
        const minScore =
            state.event === "puryfi.media.scan" && state.minScore.trim() !== ""
                ? Math.min(1, Math.max(0, Number(state.minScore)))
                : 0;

        const payload: AutomationCreateSchema = {
            name,
            enabled: state.enabled,
            priority: state.priority,
            trigger: {
                event: state.event,
                conditions,
                min_score: minScore,
                count: state.event === "puryfi.media.scan" ? Math.max(1, state.count) : 1,
                window_seconds:
                    state.event === "puryfi.media.scan"
                        ? Math.max(0, state.windowMinutes) * 60
                        : 0,
                count_mode: "images",
            },
            actions,
            limits: {
                cooldown_seconds:
                    state.event === "puryfi.media.scan"
                        ? Math.max(5, state.cooldownSeconds)
                        : 0,
                max_per_day: 0,
            },
        };

        setError(null);
        await onSave(payload);
    };

    const isMedia = state.event === "puryfi.media.scan";
    const title = initial && "id" in initial ? "Edit automation" : "New automation";

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-3 backdrop-blur-sm sm:p-6"
            onClick={onClose}
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="automation-editor-title"
                className="relative flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#17151F] shadow-2xl shadow-black/50"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="flex items-start justify-between gap-3 border-b border-white/[0.06] px-5 py-4">
                    <div className="flex items-center gap-3">
                        <div className="flex size-9 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-cyan-300">
                            <Sparkles className="size-4" />
                        </div>
                        <div>
                            <h2 id="automation-editor-title" className="text-sm font-semibold text-white">
                                {title}
                            </h2>
                            <p className="text-xs text-slate-400">
                                When this happens, then do these actions.
                            </p>
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close editor"
                        className="flex size-8 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-white/[0.05] hover:text-white"
                    >
                        <X className="size-4" />
                    </button>
                </div>

                <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5">
                    <label className="block space-y-1.5">
                        <span className="text-xs font-medium text-slate-300">Name</span>
                        <Input
                            value={state.name}
                            onChange={(event) => update("name", event.target.value)}
                            placeholder="e.g. Eyes and Belly"
                            className="border-white/10 bg-[#0F0E16] text-white placeholder:text-slate-600"
                        />
                    </label>

                    <label className="block space-y-1.5">
                        <span className="text-xs font-medium text-slate-300">When</span>
                        <select
                            value={state.event}
                            onChange={(event) => handleEventChange(event.target.value)}
                            className="h-11 w-full rounded-xl border border-white/10 bg-[#0F0E16] px-3 text-sm text-white outline-none focus:border-cyan-400/50 focus:ring-4 focus:ring-cyan-400/10"
                        >
                            <option value="chaster.session.joined">The user joins the lock</option>
                            <option value="chaster.session.left">The user leaves the lock</option>
                            <option value="chaster.lock.frozen">The Chaster lock is frozen</option>
                            <option value="chaster.lock.unfrozen">The Chaster lock is unfrozen</option>
                            <option value="puryfi.media.scan">An image is analysed by PuryFi</option>
                            <option value="puryfi.connection.ready">PuryFi connects</option>
                            <option value="puryfi.connection.disconnected">PuryFi disconnects</option>
                            <option value="puryfi.enabled">PuryFi is enabled</option>
                            <option value="puryfi.disabled">PuryFi is disabled</option>
                            <option value="puryfi.locked">PuryFi is locked</option>
                            <option value="puryfi.unlocked">PuryFi is unlocked</option>
                        </select>
                    </label>

                    {isMedia ? (
                        <div className="space-y-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
                            <div className="flex items-center justify-between gap-2">
                                <span className="text-xs font-medium text-slate-300">
                                    Only if the image contains
                                </span>
                                <span className="text-[10px] text-slate-500">
                                    {state.selectedLabels.length === 0
                                        ? "any image"
                                        : `${state.selectedLabels.length} label(s)`}
                                </span>
                            </div>
                            <div className="grid max-h-48 grid-cols-2 gap-1.5 overflow-y-auto sm:grid-cols-3">
                                {labels.map((label) => (
                                    <label
                                        key={label.value}
                                        className={cn(
                                            "flex cursor-pointer items-center gap-1.5 rounded-lg border px-2 py-1.5 text-[11px]",
                                            state.selectedLabels.includes(label.value)
                                                ? "border-cyan-400/25 bg-cyan-400/10 text-cyan-100"
                                                : "border-white/[0.06] bg-black/10 text-slate-400 hover:border-white/15",
                                        )}
                                    >
                                        <input
                                            type="checkbox"
                                            checked={state.selectedLabels.includes(label.value)}
                                            onChange={() => toggleLabel(label.value)}
                                            className="size-3.5 shrink-0 accent-cyan-500"
                                        />
                                        {LABEL_IMAGES[label.value] ? (
                                            <img
                                                src={LABEL_IMAGES[label.value]}
                                                alt=""
                                                width={20}
                                                height={20}
                                                className="size-5 shrink-0 rounded object-contain"
                                                loading="lazy"
                                            />
                                        ) : null}
                                        <span className="min-w-0 leading-snug">
                                            {labelNames[label.value] ?? label.value}
                                        </span>
                                    </label>
                                ))}
                            </div>

                            <div className="grid gap-3 sm:grid-cols-3">
                                <label className="space-y-1.5">
                                    <span className="text-[11px] text-slate-400">
                                        Minimum score (0–1)
                                    </span>
                                    <Input
                                        type="number"
                                        min={0}
                                        max={1}
                                        step={0.05}
                                        value={state.minScore}
                                        onChange={(event) => update("minScore", event.target.value)}
                                        placeholder="Any"
                                        className="border-white/10 bg-[#0F0E16] text-white"
                                    />
                                </label>
                                <label className="space-y-1.5">
                                    <span className="text-[11px] text-slate-400">
                                        Matching images
                                    </span>
                                    <NumberInput
                                        id="automation-count"
                                        value={state.count}
                                        onChange={(value) => update("count", value)}
                                        min={1}
                                        max={10_000}
                                    />
                                </label>
                                <label className="space-y-1.5">
                                    <span className="text-[11px] text-slate-400">
                                        Within (minutes, 0 = no limit)
                                    </span>
                                    <NumberInput
                                        id="automation-window"
                                        value={state.windowMinutes}
                                        onChange={(value) => update("windowMinutes", value)}
                                        min={0}
                                        max={1_440}
                                    />
                                </label>
                            </div>
                        </div>
                    ) : null}

                    <div className="space-y-2">
                        <span className="text-xs font-medium text-slate-300">Then</span>
                        <div className="grid gap-2 sm:grid-cols-2">
                            <ActionToggle
                                label="Lock PuryFi with the stored or a generated password"
                                checked={state.lockPuryfi}
                                onChange={(checked) => update("lockPuryfi", checked)}
                            />
                            <ActionToggle
                                label="Enable PuryFi"
                                checked={state.enablePuryfi}
                                onChange={(checked) => update("enablePuryfi", checked)}
                            />
                            <ActionToggle
                                label="Unlock PuryFi with the stored password"
                                checked={state.unlockPuryfi}
                                onChange={(checked) => update("unlockPuryfi", checked)}
                            />
                            <ActionToggle
                                label="Disable PuryFi"
                                checked={state.disablePuryfi}
                                onChange={(checked) => update("disablePuryfi", checked)}
                            />
                            <ActionToggle
                                label="Freeze the Chaster lock"
                                checked={state.freezeChaster}
                                onChange={(checked) => update("freezeChaster", checked)}
                            />
                            <ActionToggle
                                label="Unfreeze the Chaster lock"
                                checked={state.unfreezeChaster}
                                onChange={(checked) => update("unfreezeChaster", checked)}
                            />
                            <ActionToggle
                                label="Toggle the Chaster freeze state"
                                checked={state.toggleFreeze}
                                onChange={(checked) => update("toggleFreeze", checked)}
                            />
                            <ActionToggle
                                label="Put the wearer in pillory"
                                checked={state.pillory}
                                onChange={(checked) => update("pillory", checked)}
                            />
                            <ActionToggle
                                label="Show or hide the remaining time"
                                checked={state.timerVisibility}
                                onChange={(checked) => update("timerVisibility", checked)}
                            />
                            <ActionToggle
                                label="Add time to the Chaster lock"
                                checked={state.addTime}
                                onChange={(checked) => update("addTime", checked)}
                            />
                            <ActionToggle
                                label="Remove time from the Chaster lock"
                                checked={state.removeTime}
                                onChange={(checked) => update("removeTime", checked)}
                            />
                            <ActionToggle
                                label="Write a Chaster log"
                                checked={state.writeLog}
                                onChange={(checked) => update("writeLog", checked)}
                            />
                        </div>

                        {state.pillory ? (
                            <div className="space-y-2 rounded-lg border border-white/[0.06] bg-black/10 px-3 py-2.5">
                                <div className="flex items-center gap-3">
                                    <span className="text-xs text-slate-400">Pillory duration</span>
                                    <NumberInput
                                        id="automation-pillory-duration"
                                        value={state.pilloryDuration}
                                        onChange={(value) => update("pilloryDuration", value)}
                                        min={1}
                                        max={604_800}
                                        suffix="seconds"
                                        className="max-w-48"
                                    />
                                </div>
                                <Input
                                    value={state.pilloryReason}
                                    onChange={(event) =>
                                        update("pilloryReason", event.target.value)
                                    }
                                    placeholder="Reason (optional)"
                                    className="border-white/10 bg-[#0F0E16] text-white"
                                />
                            </div>
                        ) : null}

                        {state.timerVisibility ? (
                            <div className="flex items-center gap-3 rounded-lg border border-white/[0.06] bg-black/10 px-3 py-2.5">
                                <span className="text-xs text-slate-400">Remaining time</span>
                                <select
                                    value={state.displayRemainingTime ? "show" : "hide"}
                                    onChange={(event) =>
                                        update(
                                            "displayRemainingTime",
                                            event.target.value === "show",
                                        )
                                    }
                                    className="h-9 rounded-lg border border-white/10 bg-[#0F0E16] px-3 text-xs text-white outline-none focus:border-cyan-400/50"
                                >
                                    <option value="show">Show to the wearer</option>
                                    <option value="hide">Hide from the wearer</option>
                                </select>
                            </div>
                        ) : null}

                        {state.addTime ? (
                            <div className="flex items-center gap-3 rounded-lg border border-white/[0.06] bg-black/10 px-3 py-2.5">
                                <span className="text-xs text-slate-400">Added time</span>
                                <NumberInput
                                    id="automation-add-time"
                                    value={state.addTimeSeconds}
                                    onChange={(value) => update("addTimeSeconds", value)}
                                    min={1}
                                    max={604_800}
                                    suffix="seconds"
                                    className="max-w-48"
                                />
                            </div>
                        ) : null}

                        {state.removeTime ? (
                            <div className="flex items-center gap-3 rounded-lg border border-white/[0.06] bg-black/10 px-3 py-2.5">
                                <span className="text-xs text-slate-400">Removed time</span>
                                <NumberInput
                                    id="automation-remove-time"
                                    value={state.removeTimeSeconds}
                                    onChange={(value) => update("removeTimeSeconds", value)}
                                    min={1}
                                    max={604_800}
                                    suffix="seconds"
                                    className="max-w-48"
                                />
                            </div>
                        ) : null}

                        {state.writeLog ? (
                            <div className="rounded-lg border border-white/[0.06] bg-black/10 px-3 py-2.5">
                                <Input
                                    value={state.logTitle}
                                    onChange={(event) => update("logTitle", event.target.value)}
                                    placeholder="Log title"
                                    className="border-white/10 bg-[#0F0E16] text-white"
                                />
                            </div>
                        ) : null}
                    </div>

                    {isMedia ? (
                        <label className="block space-y-1.5">
                            <span className="text-xs font-medium text-slate-300">
                                Cooldown before this automation can run again
                            </span>
                            <NumberInput
                                id="automation-cooldown"
                                value={state.cooldownSeconds}
                                onChange={(value) =>
                                    update("cooldownSeconds", Math.max(5, value))
                                }
                                min={5}
                                max={604_800}
                                suffix="seconds"
                            />
                            <span className="text-[11px] text-slate-500">
                                Minimum cooldown for media automations: 5 seconds.
                            </span>
                        </label>
                    ) : null}

                    {error ? (
                        <p className="rounded-lg border border-rose-400/20 bg-rose-400/[0.07] px-3 py-2 text-xs text-rose-200">
                            {error}
                        </p>
                    ) : null}
                </div>

                <div className="flex items-center justify-end gap-2 border-t border-white/[0.06] px-5 py-3.5">
                    <Button
                        type="button"
                        variant="ghost"
                        onClick={onClose}
                        className="text-slate-400 hover:text-white"
                    >
                        Cancel
                    </Button>
                    <Button
                        type="button"
                        onClick={handleSave}
                        disabled={busy}
                        className="bg-cyan-500 text-slate-950 hover:bg-cyan-400"
                    >
                        {busy ? <LoaderCircle className="animate-spin" /> : <Save />}
                        Save automation
                    </Button>
                </div>
            </div>
        </div>
    );
}

function ActionToggle({
    label,
    checked,
    onChange,
}: {
    label: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
}) {
    return (
        <label
            className={cn(
                "flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2.5 text-xs",
                checked
                    ? "border-cyan-400/20 bg-cyan-400/[0.07] text-cyan-100"
                    : "border-white/[0.06] bg-black/10 text-slate-400 hover:border-white/15",
            )}
        >
            <input
                type="checkbox"
                checked={checked}
                onChange={(event) => onChange(event.target.checked)}
                className="size-3.5 accent-cyan-500"
            />
            {label}
        </label>
    );
}
