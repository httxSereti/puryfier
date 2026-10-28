import SectionSkeleton from "@/components/ui/section-skeleton";
import Skeleton from "@/components/ui/skeleton";

export default function ConfigurationSkeleton() {
    return (
        <div role="status" aria-busy="true" aria-live="polite" className="flex flex-col gap-5">
            <span className="sr-only">Loading configuration…</span>

            <div className="flex items-start gap-3.5 rounded-2xl border border-white/[0.07] bg-[#17151F]/90 p-4 shadow-xl shadow-black/20 backdrop-blur sm:items-center sm:p-5">
                <Skeleton className="size-11 shrink-0 rounded-2xl" />

                <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                        <Skeleton className="h-4 w-36" />
                        <Skeleton className="h-5 w-16 rounded-full" />
                    </div>
                    <Skeleton className="h-3 w-full max-w-md" />
                </div>
            </div>

            <SectionSkeleton rows={2} />
            <SectionSkeleton rows={1} showFields />
        </div>
    );
}
