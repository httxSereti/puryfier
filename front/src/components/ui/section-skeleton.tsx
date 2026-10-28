import Skeleton from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface SectionSkeletonProps {
    rows?: number;
    showFields?: boolean;
    showAction?: boolean;
    className?: string;
}

/**
 * Placeholder that mirrors the header and content rhythm of SectionCard.
 */
export default function SectionSkeleton({
    rows = 2,
    showFields = false,
    showAction = false,
    className,
}: SectionSkeletonProps) {
    return (
        <div
            className={cn(
                "overflow-hidden rounded-2xl border border-white/[0.07] bg-[#17151F]/90 shadow-xl shadow-black/20 backdrop-blur",
                className,
            )}
        >
            <div className="flex items-start gap-3 border-b border-white/[0.05] px-4 py-4 sm:px-5">
                <Skeleton className="size-9 shrink-0 rounded-xl" />

                <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                        <Skeleton className="h-3.5 w-24" />
                        {showAction ? <Skeleton className="h-5 w-16 rounded-full" /> : null}
                    </div>
                    <Skeleton className="h-3 w-56 max-w-full" />
                </div>
            </div>

            <div className="space-y-3 p-3.5 sm:p-4">
                {Array.from({ length: rows }).map((_, index) => (
                    <div
                        key={index}
                        className="flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5 sm:gap-4 sm:p-4"
                    >
                        <Skeleton className="size-10 shrink-0 rounded-xl" />

                        <div className="min-w-0 flex-1 space-y-2">
                            <Skeleton className="h-3.5 w-40 max-w-full" />
                            <Skeleton className="h-3 w-64 max-w-full" />
                        </div>

                        <Skeleton className="h-6 w-11 shrink-0 rounded-full" />
                    </div>
                ))}

                {showFields ? (
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                        <div className="grid gap-4 sm:grid-cols-2">
                            {[0, 1].map((index) => (
                                <div key={index} className="space-y-2">
                                    <Skeleton className="h-3 w-32" />
                                    <Skeleton className="h-11 w-full rounded-xl" />
                                    <Skeleton className="h-3 w-44 max-w-full" />
                                </div>
                            ))}
                        </div>

                        <Skeleton className="mt-4 h-10 w-full rounded-lg" />
                    </div>
                ) : null}
            </div>
        </div>
    );
}
