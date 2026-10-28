import SectionSkeleton from "@/components/ui/section-skeleton";
import Skeleton from "@/components/ui/skeleton";

export default function SessionSkeleton() {
    return (
        <div role="status" aria-busy="true" aria-live="polite" className="flex flex-col gap-5">
            <span className="sr-only">Loading extension…</span>

            <div className="rounded-2xl border border-white/[0.07] bg-[#17151F]/90 p-5 shadow-xl shadow-black/20 backdrop-blur">
                <div className="flex items-start gap-3">
                    <Skeleton className="size-11 shrink-0 rounded-2xl" />

                    <div className="min-w-0 flex-1 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                            <Skeleton className="h-4 w-32" />
                            <Skeleton className="h-5 w-16 rounded-full" />
                        </div>
                        <Skeleton className="h-3 w-full max-w-sm" />
                    </div>
                </div>

                <Skeleton className="mt-4 h-10 w-full rounded-xl" />
            </div>

            <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2 px-1">
                    <Skeleton className="size-3.5 shrink-0 rounded" />
                    <Skeleton className="h-3 w-72 max-w-full" />
                </div>

                <div className="grid gap-5 lg:grid-cols-2">
                    <SectionSkeleton rows={2} showAction />
                    <SectionSkeleton rows={1} showFields showAction />
                </div>
            </div>
        </div>
    );
}
