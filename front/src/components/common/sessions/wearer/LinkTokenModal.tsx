import { useEffect, useState } from "react";
import { Check, Copy, KeyRound, LoaderCircle, TriangleAlert, X } from "lucide-react";

import { copyText } from "@/lib/clipboard";
import { getPuryfiWebSocketUrl } from "@/lib/backend";
import { createLinkToken } from "@/lib/http/session";
import { readChasterIframeParams } from "@/lib/chaster";
import { getApiErrorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

interface LinkTokenModalProps {
    linkToken: string | null;
    onClose: () => void;
    onTokenCreated: (token: string) => void;
}

export default function LinkTokenModal({ linkToken, onClose, onTokenCreated }: LinkTokenModalProps) {
    const [token, setToken] = useState<string | null>(linkToken);
    const [copied, setCopied] = useState(false);
    const [copyFailed, setCopyFailed] = useState(false);
    const [isCreating, setIsCreating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                onClose();
            }
        };

        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [onClose]);

    const handleCopy = async () => {
        if (!token) return;

        setCopyFailed(false);
        const ok = await copyText(getPuryfiWebSocketUrl(token));

        if (ok) {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } else {
            setCopyFailed(true);
            setTimeout(() => setCopyFailed(false), 3000);
        }
    };

    const handleCreate = async () => {
        setIsCreating(true);
        setError(null);

        try {
            // The link-token endpoint authenticates with the Chaster-issued
            // mainToken from the iframe URL (REVIEW.md #8).
            const { mainToken } = readChasterIframeParams();

            if (!mainToken) {
                throw new Error("mainToken not found in parameters.");
            }

            const session = await createLinkToken(mainToken);
            const newToken = session.link_token;

            if (!newToken) {
                throw new Error("The server did not return a link token.");
            }

            setToken(newToken);
            onTokenCreated(newToken);
        } catch (err: unknown) {
            setError(getApiErrorMessage(err, "Failed to create token."));
        } finally {
            setIsCreating(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
            onClick={onClose}
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="link-token-title"
                className="relative w-full max-w-md overflow-hidden rounded-2xl border border-white/10 bg-[#17151F] shadow-2xl shadow-black/50"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="flex items-start justify-between gap-3 border-b border-white/[0.06] px-5 py-4">
                    <div className="flex items-center gap-3">
                        <div className="flex size-9 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-400/10 text-cyan-300">
                            <KeyRound className="size-4" />
                        </div>
                        <div>
                            <h2 id="link-token-title" className="text-sm font-semibold text-white">
                                WebSocket URL
                            </h2>
                            <p className="text-xs text-slate-400">Connect Puryfi to this lock.</p>
                        </div>
                    </div>

                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close dialog"
                        title="Close"
                        className="flex size-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-white/[0.05] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                    >
                        <X className="size-4" />
                    </button>
                </div>

                <div className="space-y-4 px-5 py-5">
                    {token ? (
                        <>
                            <p className="text-xs leading-relaxed text-slate-400">
                                Paste this URL into a WebSocket plugin in Puryfi. Puryfi will connect
                                automatically after saving.
                            </p>

                            <div className="rounded-xl border border-white/10 bg-[#0F0E16] p-3">
                                <div className="flex items-start justify-between gap-3">
                                    <code className="min-w-0 break-all text-xs font-mono leading-relaxed text-cyan-300 select-all">
                                        {getPuryfiWebSocketUrl(token)}
                                    </code>
                                    <button
                                        type="button"
                                        onClick={handleCopy}
                                        aria-label="Copy WebSocket URL"
                                        title="Copy WebSocket URL"
                                        className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-slate-400 transition-colors hover:border-emerald-400/20 hover:bg-emerald-400/10 hover:text-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60"
                                    >
                                        {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                                    </button>
                                </div>
                            </div>

                            <p
                                aria-live="polite"
                                className={cn(
                                    "text-center text-[11px] leading-relaxed",
                                    copyFailed ? "text-amber-400" : copied ? "text-emerald-400" : "text-slate-500",
                                )}
                            >
                                {copyFailed
                                    ? "Copy blocked by the browser — select the URL and copy it manually."
                                    : copied
                                        ? "Copied to clipboard."
                                        : "Keep this URL private: anyone with it can connect to this lock."}
                            </p>
                        </>
                    ) : (
                        <>
                            <p className="text-xs leading-relaxed text-slate-400">
                                Generate a unique WebSocket URL for this lock, then register it in Puryfi.
                            </p>

                            {error ? (
                                <div className="flex items-start gap-2 rounded-lg border border-red-400/20 bg-red-400/[0.07] px-3 py-2.5 text-[11px] leading-relaxed text-red-200">
                                    <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                                    {error}
                                </div>
                            ) : null}

                            <button
                                type="button"
                                onClick={handleCreate}
                                disabled={isCreating}
                                className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-500/15 transition-colors hover:bg-cyan-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#17151F] disabled:cursor-not-allowed disabled:opacity-60"
                            >
                                {isCreating ? (
                                    <>
                                        <LoaderCircle className="size-4 animate-spin" />
                                        Generating…
                                    </>
                                ) : (
                                    <>
                                        <KeyRound className="size-4" />
                                        Generate WebSocket URL
                                    </>
                                )}
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
