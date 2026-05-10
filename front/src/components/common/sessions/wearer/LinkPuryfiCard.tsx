import type { ChasterExtensionSessionSchema } from "@/types/api"
import { Button } from "@/components/ui/button"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription, EmptyContent } from "@/components/ui/empty"
import { ArrowUpRightIcon, Link } from "lucide-react"
import { useState } from "react";
import LinkTokenModal from "@/components/common/sessions/wearer/LinkTokenModal";

export default function LinkPuryfiCard({ session }: { session: ChasterExtensionSessionSchema }) {
    const [modalOpen, setModalOpen] = useState(false);
    const [linkToken, setLinkToken] = useState<string | null>(session.link_token ?? null);

    return (
        <Empty>
            <EmptyHeader>
                <EmptyMedia variant="icon">
                    <Link />
                </EmptyMedia>
                <EmptyTitle className="text-slate-300" >Puryfier not linked</EmptyTitle>
                <EmptyDescription className="text-slate-400">
                    1. The Wearer needs to generate the WebSocket URL.
                    <br />
                    2. In Puryfi, go to <span className="text-cyan-300 font-medium">Extras: Plugins</span>, go to the <span className="text-cyan-300 font-medium">'Register new plugin'</span> section, select <span className="text-cyan-300 font-medium">WebSocket</span>, paste the URL and refresh this page.
                </EmptyDescription>
            </EmptyHeader>
            {session.role == 'wearer' ? (
                <EmptyContent className="flex-row justify-center gap-2">
                    <Button onClick={() => setModalOpen(true)}>
                        Generate WebSocket URL
                    </Button>
                </EmptyContent>
            ) : null}
            <Button
                variant="link"
                asChild
                className="text-muted-foreground"
                size="sm"
            >
                <a href="#">
                    See guide (soon) <ArrowUpRightIcon />
                </a>
            </Button>
            {modalOpen && (
                <LinkTokenModal
                    sessionId={session.id}
                    linkToken={linkToken}
                    onClose={() => setModalOpen(false)}
                    onTokenCreated={(token) => setLinkToken(token)}
                />
            )}
        </Empty>
    );
}