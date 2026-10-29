import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";

import PageShell from "@/components/common/layout/PageShell";

interface ErrorBoundaryProps {
    children: ReactNode;
}

interface ErrorBoundaryState {
    error: Error | null;
}

/**
 * Last-resort UI for unexpected render errors.
 *
 * Chaster embeds this app in an iframe: without a boundary, a render error
 * would leave an empty frame with no way to recover. The fallback keeps the
 * extension frame usable and offers a reload.
 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
    state: ErrorBoundaryState = { error: null };

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error("Unhandled UI error", error, info.componentStack);
    }

    handleReload = () => {
        window.location.reload();
    };

    render() {
        if (!this.state.error) {
            return this.props.children;
        }

        return (
            <PageShell className="max-w-3xl">
                <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
                    <div className="flex size-14 items-center justify-center rounded-2xl border border-red-400/20 bg-red-400/10 text-red-300">
                        <TriangleAlert className="size-6" />
                    </div>

                    <div className="max-w-md">
                        <h1 className="text-base font-semibold text-white">Something went wrong</h1>
                        <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
                            The extension hit an unexpected error. Reload the page to try again.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={this.handleReload}
                        className="inline-flex h-10 items-center gap-2 rounded-xl bg-cyan-500 px-4 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-500/15 transition-colors hover:bg-cyan-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#211E2C]"
                    >
                        <RefreshCw className="size-4" />
                        Reload the page
                    </button>
                </div>
            </PageShell>
        );
    }
}
