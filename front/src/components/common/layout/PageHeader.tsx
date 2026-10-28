import type { ReactNode } from "react";

import BrandMark from "@/components/common/layout/BrandMark";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
    subtitle: string;
    version?: string;
    children?: ReactNode;
    className?: string;
}

export default function PageHeader({ subtitle, version, children, className }: PageHeaderProps) {
    return (
        <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between", className)}>
            <div className="flex min-w-0 items-center gap-3.5">
                <BrandMark />
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <h1 className="text-2xl font-semibold tracking-tight text-white">Puryfier</h1>
                        {version ? (
                            <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] font-medium tracking-wide text-slate-400">
                                v{version}
                            </span>
                        ) : null}
                    </div>
                    <p className="mt-0.5 text-sm leading-relaxed text-slate-400">{subtitle}</p>
                </div>
            </div>

            {children ? (
                <div className="flex shrink-0 flex-wrap items-center gap-2">{children}</div>
            ) : null}
        </header>
    );
}
