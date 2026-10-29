import type { ChasterExtensionSessionSchema } from "@/types/api";
import { useApiResource } from "@/hooks/useApiResource";
import { fetchSession } from "@/lib/http/session";

export function useSession(mainToken: string | null) {
    return useApiResource<ChasterExtensionSessionSchema>(
        mainToken,
        "mainToken",
        fetchSession,
        "Error syncing with the local server.",
    );
}
