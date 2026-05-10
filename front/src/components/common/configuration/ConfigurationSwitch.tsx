import React from "react";

interface ConfigurationSwitchProps {
    icon: React.ReactNode;
    title: string;
    description: string;
    checked: boolean;
    onChange: () => void;
    baseColor: "cyan" | "emerald";
    disabled?: boolean;
}

export default function ConfigurationSwitch({
    icon,
    title,
    description,
    checked,
    onChange,
    baseColor,
    disabled = false,
}: ConfigurationSwitchProps) {
    const activeBgColor = baseColor === "cyan" ? "bg-cyan-500" : "bg-emerald-500";
    const focusRingColor = baseColor === "cyan" ? "focus-visible:ring-cyan-500" : "focus-visible:ring-emerald-500";

    return (
        <div className={`flex items-center justify-between bg-slate-900 border border-slate-700/50 p-4 rounded-xl transition-colors ${disabled ? 'opacity-70' : 'hover:border-cyan-900/50'}`}>
            <div className="flex items-center gap-3">
                <div className="p-2 bg-slate-800 rounded-lg">
                    {icon}
                </div>
                <div className="flex flex-col text-left">
                    <span className="text-sm font-medium text-slate-200">{title}</span>
                    <span className="text-xs text-slate-500">{description}</span>
                </div>
            </div>
            <button
                type="button"
                role="switch"
                aria-checked={checked}
                onClick={disabled ? undefined : onChange}
                disabled={disabled}
                className={`relative inline-flex h-6 w-11 shrink-0 ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'} rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-opacity-75 ${focusRingColor} ${checked ? activeBgColor : "bg-slate-700"
                    }`}
            >
                <span
                    aria-hidden="true"
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${checked ? "translate-x-5" : "translate-x-0"
                        }`}
                />
            </button>
        </div>
    );
}
