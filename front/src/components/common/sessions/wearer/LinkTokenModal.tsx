import { useState } from "react";
import { Copy, Check, Key, Loader2, X } from "lucide-react";
import axios from "axios";

interface LinkTokenModalProps {
    sessionId: string;
    linkToken: string | null;
    onClose: () => void;
    onTokenCreated: (token: string) => void;
}

export default function LinkTokenModal({ sessionId, linkToken, onClose, onTokenCreated }: LinkTokenModalProps) {
    const [token, setToken] = useState<string | null>(linkToken);
    const [copied, setCopied] = useState(false);
    const [isCreating, setIsCreating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleCopy = async () => {
        if (!token) return;
        await navigator.clipboard.writeText(`${import.meta.env.VITE_PURYFI_WS_URL}/${token}`);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleCreate = async () => {
        setIsCreating(true);
        setError(null);
        try {
            const backendUrl = import.meta.env.VITE_BACKEND_URL;
            const response = await axios.post(`${backendUrl}/api/session/${sessionId}/link-token`);
            const newToken: string = response.data.link_token;
            setToken(newToken);
            onTokenCreated(newToken);
        } catch (err: any) {
            setError(
                axios.isAxiosError(err)
                    ? err.response?.data?.detail || "Failed to create token."
                    : "Unexpected error."
            );
        } finally {
            setIsCreating(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
            onClick={onClose}
        >
            <div
                className="relative mx-4 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-6 space-y-5"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Key className="w-5 h-5 text-cyan-400" />
                        <h2 className="text-base font-semibold text-slate-100">WebSocket URL</h2>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-slate-500 hover:text-slate-300 transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {token ? (
                    <div className="space-y-3">
                        <p className="text-xs text-slate-400">
                            Use this WebSocket URL to connect Puryfi with Puryfier
                        </p>
                        <button
                            onClick={handleCopy}
                            className="group w-full flex items-center justify-between gap-3 bg-slate-950 border border-slate-700 hover:border-cyan-700 rounded-xl px-4 py-3 transition-colors"
                        >
                            <code className="text-sm font-mono text-cyan-300 truncate">{import.meta.env.VITE_PURYFI_WS_URL}/{token}</code>
                            {copied
                                ? <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                                : <Copy className="w-4 h-4 text-slate-500 group-hover:text-cyan-400 shrink-0 transition-colors" />
                            }
                        </button>
                        <p className="text-xs text-slate-500 text-center">Click the box to copy</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        <p className="text-xs text-slate-400">
                            Generate a WebSocket URL to connect your Chaster lock with Puryfi.
                        </p>
                        {error && (
                            <p className="text-xs text-red-400 bg-red-950/40 border border-red-900/40 rounded-lg px-3 py-2">
                                {error}
                            </p>
                        )}
                        <button
                            onClick={handleCreate}
                            disabled={isCreating}
                            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors"
                        >
                            {isCreating
                                ? <><Loader2 className="w-4 h-4 animate-spin" /> Generating…</>
                                : <><Key className="w-4 h-4" /> Generate WebSocket URL</>
                            }
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
