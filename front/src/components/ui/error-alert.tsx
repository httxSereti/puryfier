import { RefreshCw, TriangleAlert } from "lucide-react";

interface ErrorAlertProps {
    title?: string;
    message: string;
    onRetry?: () => void;
}

export default function ErrorAlert({ title = "Something went wrong", message, onRetry }: ErrorAlertProps) {
    return (
        <div
            role="alert"
            className="flex items-start gap-3 rounded-2xl border border-red-400/20 bg-red-400/[0.07] p-4 shadow-lg shadow-black/10"
        >
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-red-400/20 bg-red-400/10 text-red-300">
                <TriangleAlert className="size-4" />
            </div>

            <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-red-200">{title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-red-200/70">{message}</p>
            </div>

            {onRetry ? (
                <button
                    type="button"
                    onClick={onRetry}
                    className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-red-400/20 bg-red-400/10 px-2.5 text-xs font-medium text-red-200 transition-colors hover:bg-red-400/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60"
                >
                    <RefreshCw className="size-3.5" />
                    Retry
                </button>
            ) : null}
        </div>
    );
}
