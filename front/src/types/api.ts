import type { components } from "@/types/api.generated";

export type { components, operations, paths } from "@/types/api.generated";

/**
 * Backend DTOs generated from the FastAPI OpenAPI document.
 *
 * Regenerate them with `pnpm generate:api` after changing a request or
 * response model; never edit `api.generated.ts` by hand.
 */
export type CensorPicsConfigSchema = components["schemas"]["CensorPicsConfigSchema"];
export type ChasterExtensionConfigSchema = components["schemas"]["ChasterExtensionConfigSchema"];
export type ChasterExtensionConfigurationSchema =
    components["schemas"]["ChasterExtensionConfigurationSchema"];
export type ChasterExtensionSessionSchema = components["schemas"]["ChasterExtensionSessionSchema"];

/**
 * Payload pushed by the backend's realtime status channel.
 *
 * WebSocket frames are not part of the HTTP OpenAPI document, so this frame
 * stays hand-written. It mirrors the status payload sent by `api/realtime.py`.
 */
export interface PuryfiRealtimeStatus {
    is_online: boolean;
    has_linked_plugin: boolean;
    puryfi_version: string | null;
}
