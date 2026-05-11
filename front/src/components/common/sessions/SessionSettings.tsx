import type { ChasterExtensionSessionSchema } from "@/types/api";
import ShowPuryfiPassword from "@/components/common/sessions/keyholder/ShowPuryfiPassword";
import ConfigurationSwitch from "@/components/common/configuration/ConfigurationSwitch";
import { Eye, Snowflake, Unlock } from "lucide-react";
import { Input } from "@/components/ui/input";

export default function SessionSettings({ session }: { session: ChasterExtensionSessionSchema }) {
    console.log(session)
    return (
        <div className="w-full px-6 py-4 flex flex-col gap-4 bg-slate-950/80 border border-slate-800 rounded-2xl text-left shadow-lg">
            <h1 className="text-xl font-bold tracking-tight text-white">
                Settings
            </h1>

            {session.lock_password && session.role === "keyholder" && (
                <ShowPuryfiPassword puryfiPassword={session.lock_password} />
            )}

            <h6 className="text-xs font-mono tracking-tight text-gray-500">
                General
            </h6>
            <div className="flex flex-col gap-4 w-full">
                <ConfigurationSwitch
                    icon={<Snowflake className="w-5 h-5 text-cyan-400" />}
                    title="Lock on Freeze"
                    description="Automatically lock Puryfi when lock is frozen"
                    checked={session.config.lock_on_freeze}
                    onChange={() => { }}
                    baseColor="cyan"
                    disabled={true}
                />
                <ConfigurationSwitch
                    icon={<Unlock className="w-5 h-5 text-emerald-400" />}
                    title="Unlock on Unfreeze"
                    description="Automatically unlock Puryfi when unfreezing"
                    checked={session.config.unlock_on_unfreeze}
                    onChange={() => { }}
                    baseColor="emerald"
                    disabled={true}
                />
            </div>

            <h6 className="text-xs font-mono tracking-tight text-gray-500">
                Censored media
            </h6>
            <div className="flex flex-col gap-4 w-full">
                <ConfigurationSwitch
                    icon={<Eye className="w-5 h-5 text-cyan-400" />}
                    title="Add time when a media is censored"
                    description="Add time to the lock when a media is censored by Puryfi"
                    checked={session.config.censorPicsConfig.enabled}
                    onChange={() => { }}
                    baseColor="cyan"
                    disabled={true}
                />

                {session.config.censorPicsConfig.enabled && (
                    <div className="flex flex-col sm:flex-row gap-4 mt-2 px-1">
                        <div className="flex-1 space-y-1">
                            <label className="text-xs font-medium text-slate-400 ml-1">
                                Every {session.config.censorPicsConfig.limit_count} images add
                            </label>
                            <Input
                                value={session.config.censorPicsConfig.added_duration}
                                onChange={() => { }}
                                disabled={true}
                                className="bg-slate-900/50 text-white border-slate-800 focus-visible:ring-cyan-500/50"
                            />
                        </div>
                        <div className="flex-1 space-y-1">
                            <label className="text-xs font-medium text-slate-400 ml-1">
                                Added Duration (seconds)
                            </label>
                            <Input
                                value={session.config.censorPicsConfig.added_duration}
                                onChange={() => { }}
                                disabled={true}
                                className="bg-slate-900/50 text-white border-slate-800 focus-visible:ring-cyan-500/50"
                            />
                        </div>
                    </div>
                )}
            </div>

        </div>

    )
}