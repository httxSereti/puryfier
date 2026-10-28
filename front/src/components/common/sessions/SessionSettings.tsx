import { LockKeyhole } from "lucide-react";

import CensoredMediaOptions from "@/components/common/configuration/CensoredMediaOptions";
import GeneralConfigurationOptions from "@/components/common/configuration/GeneralConfigurationOptions";
import type { ChasterExtensionSessionSchema } from "@/types/api";

export default function SessionSettings({ session }: { session: ChasterExtensionSessionSchema }) {
    const config = session.config;

    if (!config) {
        return null;
    }

    return (
        <div className="flex flex-col gap-3">
            <div className="flex items-start gap-2 px-1">
                <LockKeyhole className="mt-0.5 size-3.5 shrink-0 text-slate-500" />
                <p className="text-xs leading-relaxed text-slate-400">
                    {session.role === "wearer"
                        ? "You can change these settings from the extension configuration page."
                        : "These settings are read-only here. The wearer can change them from the extension configuration page."}
                </p>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
                <GeneralConfigurationOptions config={config} readOnly />
                <CensoredMediaOptions config={config} readOnly />
            </div>
        </div>
    );
}
