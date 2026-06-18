import { ButtplugClient } from "@zendrex/buttplug.js";
import { WasmTransport } from "@zendrex/buttplug.js/wasm";
import { Bluetooth, Loader2, OctagonAlert, Plus, Radio, RotateCw, Unplug, Vibrate, Waves } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Device, FeatureValue } from "@zendrex/buttplug.js";
import type { ComponentType } from "react";

type ConnectionStatus = "unsupported" | "idle" | "connecting" | "connected";

type ActionKey = "connect" | "disconnect" | "pair" | "vibrate" | "pulse" | "rotate" | "stopAll";

type ButtonVariant = "primary" | "muted" | "danger" | "ghost";

interface DeviceRow {
	canRotate: boolean;
	canVibrate: boolean;
	index: number;
	label: string;
}

interface LogLine {
	id: number;
	text: string;
}

const VIBRATE_INTENSITY = 0.5;
const VIBRATE_DURATION_MS = 3000;
const ROTATE_SPEED = 0.6;
const ROTATE_DURATION_MS = 3000;
const PULSE_STEPS: ReadonlyArray<{ intensity: number; ms: number }> = [
	{ intensity: 0.8, ms: 250 },
	{ intensity: 0, ms: 150 },
	{ intensity: 0.8, ms: 250 },
	{ intensity: 0, ms: 150 },
	{ intensity: 0.8, ms: 250 },
];

function labelFor(device: Device): string {
	return device.displayName ?? device.name;
}

function toRow(device: Device): DeviceRow {
	return {
		index: device.index,
		label: labelFor(device),
		canVibrate: device.canOutput("Vibrate"),
		canRotate: device.canRotate,
	};
}

function useLog() {
	const [lines, setLines] = useState<LogLine[]>([]);
	const idRef = useRef(0);

	const append = useCallback((text: string) => {
		setLines((prev) => [...prev, { id: idRef.current++, text }]);
	}, []);

	const clear = useCallback(() => setLines([]), []);

	return { lines, append, clear };
}

export function WasmDemo() {
	const clientRef = useRef<ButtplugClient | null>(null);
	const timersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
	const logRef = useRef<HTMLPreElement>(null);
	const { lines, append, clear } = useLog();

	const [status, setStatus] = useState<ConnectionStatus>("idle");
	const [busyAction, setBusyAction] = useState<ActionKey | null>(null);
	const [isPairing, setIsPairing] = useState(false);
	const [devices, setDevices] = useState<DeviceRow[]>([]);

	useEffect(() => {
		const nav = globalThis.navigator as Navigator & { bluetooth?: unknown };
		if (!nav.bluetooth) {
			// eslint-disable-next-line react-hooks/set-state-in-effect
			setStatus("unsupported");
		}
	}, []);

	useEffect(() => {
		const el = logRef.current;
		if (el && lines.length > 0) {
			el.scrollTop = el.scrollHeight;
		}
	}, [lines]);

	const scheduleTimer = useCallback((fn: () => void, ms: number) => {
		const handle = setTimeout(() => {
			timersRef.current.delete(handle);
			fn();
		}, ms);
		timersRef.current.add(handle);
		return handle;
	}, []);

	const clearTimers = useCallback(() => {
		for (const handle of timersRef.current) {
			clearTimeout(handle);
		}
		timersRef.current.clear();
	}, []);

	const syncDevices = useCallback((client: ButtplugClient) => {
		setDevices(client.devices.map(toRow));
	}, []);

	const ensureClient = useCallback(() => {
		if (clientRef.current) {
			return clientRef.current;
		}

		const client = new ButtplugClient(new WasmTransport());

		client.on("connection.connecting", () => setStatus("connecting"));

		client.on("connection.connected", () => {
			append("Server ready");
			setStatus("connected");
		});

		client.on("connection.disconnected", ({ data: { reason } }) => {
			append(`Disconnected${reason ? `: ${reason}` : ""}`);
			setStatus("idle");
			setIsPairing(false);
			setDevices([]);
			clearTimers();
		});

		client.on("device.added", ({ data: { device } }) => {
			append(`Paired: ${labelFor(device)}`);
			console.log(device)
			syncDevices(client);
		});

		client.on("device.removed", ({ data: { device } }) => {
			append(`Removed: ${labelFor(device)}`);
			syncDevices(client);
		});

		client.on("scan.started", () => {
			setIsPairing(true);
		});

		client.on("scan.finished", () => {
			setIsPairing(false);
		});

		client.on("connection.error", ({ data: { error } }) => {
			append(`Error: ${error.message}`);
		});

		clientRef.current = client;
		return client;
	}, [append, clearTimers, syncDevices]);

	useEffect(
		() => () => {
			clearTimers();
			const client = clientRef.current;
			if (client) {
				client.disconnect().catch(() => undefined);
				client.dispose();
				clientRef.current = null;
			}
		},
		[clearTimers]
	);

	const run = useCallback(
		async (key: ActionKey, action: () => Promise<void>) => {
			setBusyAction(key);
			try {
				await action();
			} catch (error) {
				append(`Failed: ${error instanceof Error ? error.message : String(error)}`);
			} finally {
				setBusyAction(null);
			}
		},
		[append]
	);

	const withDevices = useCallback(
		async (
			filter: (device: Device) => boolean,
			action: (device: Device) => Promise<void> | void,
			emptyMessage: string
		) => {
			const client = clientRef.current;
			if (!client) {
				return;
			}
			const targets = client.devices.filter(filter);
			if (targets.length === 0) {
				append(emptyMessage);
				return;
			}
			await Promise.all(targets.map((device) => Promise.resolve(action(device))));
		},
		[append]
	);

	const onConnect = () =>
		run("connect", async () => {
			const client = ensureClient();
			append("Loading WASM server…");
			await client.connect();
		});

	const onDisconnect = () =>
		run("disconnect", async () => {
			const client = clientRef.current;
			if (!client) {
				return;
			}
			clearTimers();
			await client.disconnect("demo disconnect");
			client.dispose();
			clientRef.current = null;
			setStatus("idle");
			setDevices([]);
		});

	const onPair = () =>
		run("pair", async () => {
			const client = clientRef.current;
			if (!client) {
				return;
			}
			if (client.scanning) {
				return;
			}
			append("Opening Bluetooth picker…");
			await client.startScanning();
		});

	const onVibrate = () =>
		run("vibrate", () =>
			withDevices(
				(device) => device.canOutput("Vibrate"),
				async (device) => {
					// await device.vibrate(VIBRATE_INTENSITY);
					await device.vibrate([{
						index: 0,
						value: VIBRATE_INTENSITY
					}, {
						index: 1,
						value: VIBRATE_INTENSITY
					}]);
					append(
						`Vibrating ${labelFor(device)} at ${Math.round(VIBRATE_INTENSITY * 100)}% for ${VIBRATE_DURATION_MS}ms`
					);
					scheduleTimer(() => {
						device.stop().catch(() => undefined);
					}, VIBRATE_DURATION_MS);
				},
				"No vibrating devices paired"
			)
		);

	const onPulse = () =>
		run("pulse", () =>
			withDevices(
				(device) => device.canOutput("Vibrate"),
				(device) => {
					append(`Pulsing ${labelFor(device)}`);
					let elapsed = 0;
					for (const step of PULSE_STEPS) {
						const intensity = step.intensity;
						scheduleTimer(() => {
							if (intensity === 0) {
								device.stop().catch(() => undefined);
							} else {
								device.vibrate(intensity).catch(() => undefined);
							}
						}, elapsed);
						elapsed += step.ms;
					}
					scheduleTimer(() => {
						device.stop().catch(() => undefined);
					}, elapsed);
				},
				"No vibrating devices paired"
			)
		);

	const onRotate = () =>
		run("rotate", () =>
			withDevices(
				(device) => device.canRotate,
				async (device) => {
					await device.rotate(ROTATE_SPEED, { clockwise: true });
					append(
						`Rotating ${labelFor(device)} at ${Math.round(ROTATE_SPEED * 100)}% for ${ROTATE_DURATION_MS}ms`
					);
					scheduleTimer(() => {
						device.stop().catch(() => undefined);
					}, ROTATE_DURATION_MS);
				},
				"No rotating devices paired"
			)
		);

	const onStopAll = () =>
		run("stopAll", async () => {
			clearTimers();
			const client = clientRef.current;
			if (!client) {
				return;
			}
			await client.stopAll();
			append("Stopped all devices");
		});

	const connected = status === "connected";
	const idle = status === "idle";
	const anyBusy = busyAction !== null;
	const hasDevices = devices.length > 0;
	const isActionBusy = (key: ActionKey) => busyAction === key;
	const blocksOthers = (key: ActionKey) => anyBusy && busyAction !== key;

	if (status === "unsupported") {
		return (
			<div className="not-prose my-6 rounded-xl border border-fd-border bg-fd-card p-5 text-fd-muted-foreground text-sm leading-relaxed">
				<p className="font-medium text-fd-foreground">Bluetooth Unavailable</p>
				<p className="mt-2">
					Web Bluetooth is not available in this browser. Open this page in Chrome, Edge, or Opera.
				</p>
			</div>
		);
	}

	if (!connected) {
		return (
			<div className="not-prose my-6 rounded-xl border border-fd-border bg-fd-card p-6">
				<div className="flex flex-col items-center gap-4 text-center">
					<StatusBadge status={status} />
					<div>
						<p className="font-medium text-fd-foreground text-sm">In-browser Buttplug server</p>
						<p className="mt-1 text-fd-muted-foreground text-xs">
							Loads a WASM build of the Buttplug server and pairs devices directly via Web Bluetooth.
						</p>
					</div>
					<DemoButton
						busy={isActionBusy("connect")}
						disabled={!idle || anyBusy}
						icon={Radio}
						label="Start server"
						onClick={onConnect}
					/>
				</div>
			</div>
		);
	}

	return (
		<div className="not-prose my-6 flex flex-col gap-3">
			<Section>
				<div className="flex flex-wrap items-center gap-2 px-4 py-3">
					<StatusBadge status={status} />
					<span className="text-fd-muted-foreground text-xs">{devices.length} paired</span>
					<div className="flex-1" />
					<DemoButton
						busy={isActionBusy("disconnect")}
						disabled={blocksOthers("disconnect")}
						icon={Unplug}
						label="Disconnect"
						onClick={onDisconnect}
						variant="muted"
					/>
				</div>
			</Section>

			<Section>
				<SectionHeader title="Devices">
					<DemoButton
						busy={isActionBusy("pair") || isPairing}
						disabled={blocksOthers("pair")}
						icon={isPairing ? Bluetooth : Plus}
						label={isPairing ? "Pairing…" : "Add device"}
						onClick={onPair}
					/>
				</SectionHeader>
				{hasDevices ? (
					<ul className="divide-y divide-fd-border">
						{devices.map((device) => (
							<li
								className="flex items-center justify-between gap-3 px-4 py-2 text-sm"
								key={device.index}
							>
								<span className="truncate text-fd-foreground">{device.label}</span>
								<span className="flex shrink-0 gap-1 text-fd-muted-foreground/70 text-xs">
									{device.canVibrate && <Capability icon={Vibrate} title="Vibrate" />}
									{device.canRotate && <Capability icon={RotateCw} title="Rotate" />}
								</span>
							</li>
						))}
					</ul>
				) : (
					<p className="px-4 py-3 text-fd-muted-foreground text-xs">
						No devices yet. Press <span className="text-fd-foreground">Add device</span> to open the
						Bluetooth picker.
					</p>
				)}
			</Section>

			<Section>
				<SectionHeader title="Actions" />
				<div className="flex flex-wrap items-center gap-2 px-4 py-3">
					<DemoButton
						busy={isActionBusy("vibrate")}
						disabled={!hasDevices || anyBusy}
						icon={Vibrate}
						label="Vibrate 50%"
						onClick={onVibrate}
					/>
					<DemoButton
						busy={isActionBusy("pulse")}
						disabled={!hasDevices || anyBusy}
						icon={Waves}
						label="Pulse"
						onClick={onPulse}
					/>
					<DemoButton
						busy={isActionBusy("rotate")}
						disabled={!hasDevices || anyBusy}
						icon={RotateCw}
						label="Rotate"
						onClick={onRotate}
					/>
					<div className="flex-1" />
					<DemoButton
						busy={isActionBusy("stopAll")}
						disabled={!hasDevices}
						icon={OctagonAlert}
						label="Stop all"
						onClick={onStopAll}
						variant="danger"
					/>
				</div>
			</Section>

			<Section>
				<SectionHeader title="Log">
					<button
						className="text-fd-muted-foreground text-xs hover:text-fd-foreground"
						onClick={clear}
						type="button"
					>
						Clear
					</button>
				</SectionHeader>
				<pre
					className="h-40 overflow-y-auto bg-fd-muted/30 px-4 py-3 font-mono text-fd-foreground text-xs leading-relaxed"
					ref={logRef}
				>
					{lines.length === 0 ? (
						<span className="text-fd-muted-foreground">Idle.</span>
					) : (
						lines.map((line) => <div key={line.id}>{line.text}</div>)
					)}
				</pre>
			</Section>
		</div>
	);
}

function Section({ children }: { children: React.ReactNode }) {
	return <div className="overflow-hidden rounded-xl border border-fd-border bg-fd-card">{children}</div>;
}

function SectionHeader({ title, children }: { title: string; children?: React.ReactNode }) {
	return (
		<div className="flex items-center justify-between border-fd-border border-b px-4 py-2">
			<span className="font-medium text-fd-muted-foreground text-xs uppercase tracking-wide">{title}</span>
			{children}
		</div>
	);
}

function StatusBadge({ status }: { status: ConnectionStatus }) {
	const labels: Record<ConnectionStatus, string> = {
		unsupported: "Unsupported",
		idle: "Server stopped",
		connecting: "Starting…",
		connected: "Server running",
	};

	const colors: Record<ConnectionStatus, string> = {
		unsupported: "bg-fd-muted text-fd-muted-foreground",
		idle: "bg-fd-muted text-fd-muted-foreground",
		connecting: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
		connected: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
	};

	return (
		<span
			className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-medium text-xs ${colors[status]}`}
		>
			{status === "connecting" && <Loader2 className="size-3 animate-spin" />}
			{labels[status]}
		</span>
	);
}

const BUTTON_VARIANT_CLASSES: Record<ButtonVariant, string> = {
	primary: "border border-transparent bg-fd-primary text-fd-primary-foreground hover:bg-fd-primary/90",
	muted: "border border-fd-border bg-fd-background text-fd-foreground hover:bg-fd-accent",
	danger: "border border-transparent bg-red-600 text-white hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600",
	ghost: "border border-transparent bg-transparent text-fd-muted-foreground hover:bg-fd-accent",
};

function DemoButton({
	label,
	onClick,
	disabled,
	busy,
	icon: Icon,
	variant = "primary",
}: {
	label: string;
	onClick: () => void;
	disabled?: boolean;
	busy?: boolean;
	icon: ComponentType<{ className?: string }>;
	variant?: ButtonVariant;
}) {
	return (
		<button
			className={`inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg px-3 font-medium text-sm leading-none transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_VARIANT_CLASSES[variant]}`}
			disabled={disabled || busy}
			onClick={onClick}
			type="button"
		>
			{busy ? <Loader2 className="size-3.5 animate-spin" /> : <Icon className="size-3.5" />}
			{label}
		</button>
	);
}

function Capability({ icon: Icon, title }: { icon: ComponentType<{ className?: string }>; title: string }) {
	return (
		<span aria-label={title} className="inline-flex" role="img" title={title}>
			<Icon className="size-3.5" />
		</span>
	);
}
