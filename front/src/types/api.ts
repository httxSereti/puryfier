export interface ChasterExtensionSessionSchema {
    id: string;
    role: string;

    has_linked_plugin: boolean;
    is_online: boolean;
    link_token: string | null;

    config: {
        lock_on_freeze: boolean;
        unlock_on_unfreeze: boolean;
        censorPicsConfig: {
            enabled: boolean;
            limit_count: number;
            added_duration: number;
        };

    };
    lock_password: string | null;
}
