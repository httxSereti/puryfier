import { useState } from "react";
import type { ChasterExtensionSessionSchema } from "@/types/api";
import { Link2 } from "lucide-react";
import LinkTokenModal from "./LinkTokenModal";

export default function ChasterWearerSession({ session }: { session: ChasterExtensionSessionSchema }) {
    const [modalOpen, setModalOpen] = useState(false);
    const [linkToken, setLinkToken] = useState<string | null>(session.link_token ?? null);

    if (!session) {
        return (
            <div>
                <h1>No Chaster Session</h1>
            </div>
        );
    }

    return (
        <>
            <div className="flex flex-col gap-3 text-left">
                <div className="flex items-center justify-between">
                    <div className="flex flex-row gap-2 items-center">
                        <Link2 className="w-5 h-5 text-slate-400" />
                        <p className="text-sm font-medium text-slate-300">Puryfi Link</p>
                    </div>

                    <button
                        onClick={() => setModalOpen(true)}
                        className="text-sm font-semibold text-emerald-400 hover:text-emerald-300 transition-colors"
                    >
                        Link
                    </button>

                </div>


            </div>

            {modalOpen && (
                <LinkTokenModal
                    sessionId={session.id}
                    linkToken={linkToken}
                    onClose={() => setModalOpen(false)}
                    onTokenCreated={(token) => setLinkToken(token)}
                />
            )}
        </>
    );
}
