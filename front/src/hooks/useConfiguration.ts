import type { ChasterExtensionConfigurationSchema } from "@/types/api";
import { useApiResource } from "@/hooks/useApiResource";
import { fetchConfiguration } from "@/lib/http/configuration";

export function useConfiguration(partnerConfigurationToken: string | null) {
    return useApiResource<ChasterExtensionConfigurationSchema>(
        partnerConfigurationToken,
        "partnerConfigurationToken",
        fetchConfiguration,
        "Error syncing with the local server.",
    );
}
