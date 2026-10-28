import { Zap } from "lucide-react";

import { cn } from "@/lib/utils";

interface BrandMarkProps {
    className?: string;
}

export default function BrandMark({ className }: BrandMarkProps) {
    return (
        <div
            aria-hidden="true"
            className={cn(
                "relative flex size-11 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-cyan-400 via-blue-500 to-violet-500 text-white shadow-lg shadow-cyan-500/20 ring-1 ring-white/20",
                className,
            )}
        >
            <span className="absolute inset-x-1.5 top-0 h-px bg-white/70 blur-[1px]" />
            <Zap className="size-5 fill-current" strokeWidth={0} />
        </div>
    );
}
