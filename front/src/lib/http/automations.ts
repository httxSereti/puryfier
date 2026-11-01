import type {
    AutomationCatalogSchema,
    AutomationCreateSchema,
    AutomationLimitsSchema,
    AutomationListSchema,
    AutomationSchema,
    AutomationTestResultSchema,
} from "@/types/api";

import { apiClient } from "./client";

function configurationPath(token: string): string {
    return `/api/configuration/${encodeURIComponent(token)}/automations`;
}

export async function fetchAutomations(
    configurationToken: string,
    signal?: AbortSignal,
): Promise<AutomationListSchema> {
    const { data } = await apiClient.get<AutomationListSchema>(
        configurationPath(configurationToken),
        { signal },
    );
    return data;
}

export async function fetchSessionAutomations(
    mainToken: string,
    signal?: AbortSignal,
): Promise<AutomationListSchema> {
    const { data } = await apiClient.get<AutomationListSchema>(
        `/api/session/${encodeURIComponent(mainToken)}/automations`,
        { signal },
    );
    return data;
}

export async function fetchAutomationCatalog(
    configurationToken: string,
    signal?: AbortSignal,
): Promise<AutomationCatalogSchema> {
    const { data } = await apiClient.get<AutomationCatalogSchema>(
        `${configurationPath(configurationToken)}/catalog`,
        { signal },
    );
    return data;
}

export async function createAutomation(
    configurationToken: string,
    payload: AutomationCreateSchema,
): Promise<AutomationSchema> {
    const { data } = await apiClient.post<AutomationSchema>(
        configurationPath(configurationToken),
        payload,
    );
    return data;
}

export type AutomationUpdateInput = Partial<
    Omit<AutomationCreateSchema, "limits">
> & {
    limits?: AutomationLimitsSchema;
};

export async function updateAutomation(
    configurationToken: string,
    automationId: string,
    payload: AutomationUpdateInput,
): Promise<AutomationSchema> {
    const { data } = await apiClient.patch<AutomationSchema>(
        `${configurationPath(configurationToken)}/${encodeURIComponent(automationId)}`,
        payload,
    );
    return data;
}

export async function deleteAutomation(
    configurationToken: string,
    automationId: string,
): Promise<void> {
    await apiClient.delete(
        `${configurationPath(configurationToken)}/${encodeURIComponent(automationId)}`,
    );
}

export async function duplicateAutomation(
    configurationToken: string,
    automationId: string,
    targetSessionId: string,
    name?: string,
): Promise<AutomationSchema> {
    const { data } = await apiClient.post<AutomationSchema>(
        `${configurationPath(configurationToken)}/${encodeURIComponent(automationId)}/duplicate`,
        { target_session_id: targetSessionId, name },
    );
    return data;
}

export async function testAutomation(
    configurationToken: string,
    automationId: string,
    event?: Record<string, unknown> | null,
): Promise<AutomationTestResultSchema> {
    const { data } = await apiClient.post<AutomationTestResultSchema>(
        `${configurationPath(configurationToken)}/${encodeURIComponent(automationId)}/test`,
        { event: event ?? null },
    );
    return data;
}

export async function migrateLegacyAutomations(
    configurationToken: string,
): Promise<AutomationSchema[]> {
    const { data } = await apiClient.post<AutomationSchema[]>(
        `${configurationPath(configurationToken)}/migrate`,
    );
    return data;
}
