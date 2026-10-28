import type { ReactNode } from "react";
import { useState } from "react";
import { Info, KeyRound, Unplug } from "lucide-react";

import LinkTokenModal from "@/components/common/sessions/wearer/LinkTokenModal";
import { Button } from "@/components/ui/button";
import StatusPill from "@/components/ui/status-pill";
import type { ChasterExtensionSessionSchema } from "@/types/api";

export default function LinkPuryfiCard({ session }: { session: ChasterExtensionSessionSchema }) {
    const [modalOpen, setModalOpen] = useState(false);
    const [linkToken, setLinkToken] = useState<string | null>(session.link_token ?? null);

    const isWearer = session.role === "wearer";
    const hasToken = Boolean(linkToken || session.has_linked_plugin);

    return (
        <section
            className={
                hasToken
                    ? "flex h-full flex-col gap-5 rounded-2xl border border-red-400/15 bg-gradient-to-br from-red-400/[0.06] via-[#17151F] to-[#17151F] p-5 shadow-xl shadow-black/20"
                    : "flex h-full flex-col gap-5 rounded-2xl border border-amber-400/15 bg-gradient-to-br from-amber-400/[0.06] via-[#17151F] to-[#17151F] p-5 shadow-xl shadow-black/20"
            }
        >
            <div className="flex items-start gap-3">
                <div
                    className={
                        hasToken
                            ? "flex size-11 shrink-0 items-center justify-center rounded-2xl border border-red-400/20 bg-red-400/10 text-red-300"
                            : "flex size-11 shrink-0 items-center justify-center rounded-2xl border border-amber-400/20 bg-amber-400/10 text-amber-300"
                    }
                >
                    <Unplug className="size-5" />
                </div>

                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-sm font-semibold text-white">
                            {hasToken ? "Puryfi is offline" : "Puryfi is not linked"}
                        </h2>
                        <StatusPill tone={hasToken ? "offline" : "warning"} dot>
                            {hasToken ? "Offline" : "Not linked"}
                        </StatusPill>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-slate-400">
                        {hasToken
                            ? "The plugin is registered, but the WebSocket connection is not active right now."
                            : "Connect your Puryfi client to start syncing censorship events with this lock."}
                    </p>
                </div>
            </div>

            {isWearer ? (
                <>
                    <ol className="grid gap-2 text-xs text-slate-400 sm:grid-cols-2">
                        <Step index={1}>Generate a WebSocket URL for this lock.</Step>
                        <Step index={2}>
                            In Puryfi, open <span className="text-cyan-300">Extras → Plugins</span>.
                        </Step>
                        <Step index={3}>
                            Add a <span className="text-cyan-300">WebSocket</span> plugin and paste the URL.
                        </Step>
                        <Step index={4}>Save the plugin — this page updates automatically.</Step>
                    </ol>

                    <Button
                        type="button"
                        onClick={() => setModalOpen(true)}
                        className="mt-auto h-10 w-full rounded-xl bg-cyan-500 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-500/15 hover:bg-cyan-400 focus-visible:ring-cyan-400 focus-visible:ring-offset-[#17151F] sm:w-auto sm:self-start"
                    >
                        <KeyRound />
                        {hasToken ? "View WebSocket URL" : "Generate WebSocket URL"}
                    </Button>
                </>
            ) : (
                <div className="mt-auto flex items-start gap-2 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3 text-xs leading-relaxed text-slate-400">
                    <Info className="mt-0.5 size-4 shrink-0 text-slate-500" />
                    <p>
                        <span className="font-medium text-slate-300">Waiting for the wearer.</span> Only the
                        wearer can generate the WebSocket URL and connect Puryfi.
                    </p>
                </div>
            )}

            {modalOpen ? (
                <LinkTokenModal
                    linkToken={linkToken}
                    onClose={() => setModalOpen(false)}
                    onTokenCreated={(token) => setLinkToken(token)}
                />
            ) : null}
        </section>
    );
}

function Step({ index, children }: { index: number; children: ReactNode }) {
    return (
        <li className="flex items-start gap-2.5 rounded-lg border border-white/[0.04] bg-black/10 px-2.5 py-2">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-[10px] font-semibold text-slate-300">
                {index}
            </span>
            <span className="leading-relaxed">{children}</span>
        </li>
    );
}
