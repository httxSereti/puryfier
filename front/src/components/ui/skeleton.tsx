import { cn } from "@/lib/utils";

interface SkeletonProps {
    className?: string;
}

export default function Skeleton({ className }: SkeletonProps) {
    return (
        <div
            aria-hidden="true"
            className={cn("animate-pulse rounded-lg bg-white/[0.06] motion-reduce:animate-none", className)}
        />
    );
}
