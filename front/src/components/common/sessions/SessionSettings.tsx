import type { ChasterExtensionSessionSchema } from "@/types/api";
import ShowPuryfiPassword from "@/components/common/sessions/keyholder/ShowPuryfiPassword";
import ConfigurationSwitch from "@/components/common/configuration/ConfigurationSwitch";
import { Snowflake, Unlock } from "lucide-react";

export default function SessionSettings({ session }: { session: ChasterExtensionSessionSchema }) {
    return (
        <div className="w-full px-6 py-4 flex flex-col gap-4 bg-slate-950/80 border border-slate-800 rounded-2xl text-left shadow-lg">
            <h1 className="text-xl font-bold tracking-tight text-white">
                Settings
            </h1>

            {session.lock_password && session.role === "keyholder" && (
                <ShowPuryfiPassword puryfiPassword={session.lock_password} />
            )}

            <div className="flex flex-col gap-4 w-full">
                <ConfigurationSwitch
                    icon={<Snowflake className="w-5 h-5 text-cyan-400" />}
                    title="Lock on Freeze"
                    description="Automatically lock Puryfi when lock is frozen"
                    checked={session.lock_on_freeze}
                    onChange={() => { }}
                    baseColor="cyan"
                    disabled={true}
                />
                <ConfigurationSwitch
                    icon={<Unlock className="w-5 h-5 text-emerald-400" />}
                    title="Unlock on Unfreeze"
                    description="Automatically unlock Puryfi when unfreezing"
                    checked={session.unlock_on_unfreeze}
                    onChange={() => { }}
                    baseColor="emerald"
                    disabled={true}
                />
            </div>

        </div>

    )
}