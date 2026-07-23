import type { ChasterExtensionConfigSchema } from "@/types/chaster";

export interface ChasterExtensionSessionSchema {
    id: string;
    role: string;

    has_linked_plugin: boolean;
    is_online: boolean;
    link_token: string | null;

    config: ChasterExtensionConfigSchema | null;
    lock_password: string | null;
}
