export interface ChasterExtensionSessionSchema {
    id: string;
    role: string;

    has_linked_plugin: boolean;
    is_online: boolean;
    link_token: string | null;

    lock_on_freeze: boolean;
    unlock_on_unfreeze: boolean;
    lock_password: string | null;
}
