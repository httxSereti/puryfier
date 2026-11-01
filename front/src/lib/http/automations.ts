import type {
    AutomationCatalogSchema,
    AutomationCreateSchema,
    AutomationLimitsSchema,
    AutomationListSchema,
    AutomationSchema,
} from "@/types/api";

import { apiClient } from "./client";

function configurationPath(token: string): string {
    return `/api/configuration/${encodeURIComponent(token)}/automations`;
}

function sessionPath(token: string): string {
    return `/api/session/${encodeURIComponent(token)}/automations`;
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
        sessionPath(mainToken),
        { signal },
    );
    return data;
}

export async function fetchSessionAutomationCatalog(
    mainToken: string,
    signal?: AbortSignal,
): Promise<AutomationCatalogSchema> {
    const { data } = await apiClient.get<AutomationCatalogSchema>(
        `${sessionPath(mainToken)}/catalog`,
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

export async function createSessionAutomation(
    mainToken: string,
    payload: AutomationCreateSchema,
): Promise<AutomationSchema> {
    const { data } = await apiClient.post<AutomationSchema>(
        sessionPath(mainToken),
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

export async function updateSessionAutomation(
    mainToken: string,
    automationId: string,
    payload: AutomationUpdateInput,
): Promise<AutomationSchema> {
    const { data } = await apiClient.patch<AutomationSchema>(
        `${sessionPath(mainToken)}/${encodeURIComponent(automationId)}`,
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

export async function deleteSessionAutomation(
    mainToken: string,
    automationId: string,
): Promise<void> {
    await apiClient.delete(
        `${sessionPath(mainToken)}/${encodeURIComponent(automationId)}`,
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

export async function duplicateSessionAutomation(
    mainToken: string,
    automationId: string,
    targetSessionId: string,
    name?: string,
): Promise<AutomationSchema> {
    const { data } = await apiClient.post<AutomationSchema>(
        `${sessionPath(mainToken)}/${encodeURIComponent(automationId)}/duplicate`,
        { target_session_id: targetSessionId, name },
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
