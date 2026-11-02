import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SessionAutomationsSummary from "@/components/common/sessions/SessionAutomationsSummary";
import { fetchSessionAutomations } from "@/lib/http/automations";
import type { AutomationListSchema, AutomationSchema } from "@/types/api";

vi.mock("@/lib/http/automations", () => ({
    fetchSessionAutomations: vi.fn(),
}));

const fetchSessionAutomationsMock = vi.mocked(fetchSessionAutomations);

function makeAutomation(overrides: Partial<AutomationSchema> = {}): AutomationSchema {
    return {
        id: "auto-1",
        session_id: "session-1",
        lock_id: "lock-1",
        lock_label: "Lock 1",
        owner_id: "keyholder-1",
        owner_role: "keyholder",
        name: "Lock on freeze",
        status: "active",
        enabled: true,
        priority: 100,
        trigger: {
            event: "chaster.lock.frozen",
            conditions: [],
            min_score: 0,
            count: 1,
            window_seconds: 0,
            count_mode: "images",
        },
        actions: [
            { type: "puryfi.lock", params: {}, on_failure: "stop" },
            { type: "puryfi.enable", params: {}, on_failure: "stop" },
        ],
        limits: { cooldown_seconds: 0, max_per_day: 0 },
        source_automation_id: null,
        disabled_by: null,
        disabled_by_role: null,
        disabled_at: null,
        archived_at: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        is_owner: true,
        can_edit: true,
        can_delete: true,
        can_disable: true,
        ...overrides,
    };
}

function makeList(overrides: Partial<AutomationListSchema> = {}): AutomationListSchema {
    return {
        session_id: "session-1",
        role: "keyholder",
        owner_id: "keyholder-1",
        automation_mode: true,
        wearer_can_manage: false,
        effective_wearer_can_manage: false,
        automations: [makeAutomation()],
        archived_automations: [],
        targets: [],
        executions: [],
        ...overrides,
    };
}

beforeEach(() => {
    fetchSessionAutomationsMock.mockReset();
    fetchSessionAutomationsMock.mockResolvedValue(makeList());
});

describe("SessionAutomationsSummary", () => {
    it("renders active rules with the automation card layout", async () => {
        render(<SessionAutomationsSummary mainToken="main-token" />);

        expect(await screen.findByText("Lock on freeze")).toBeInTheDocument();
        expect(screen.getByText("When")).toBeInTheDocument();
        expect(screen.getByText("Then")).toBeInTheDocument();
        expect(screen.getByText("Lock PuryFi")).toBeInTheDocument();
        expect(screen.getByText("Enable PuryFi")).toBeInTheDocument();
        expect(screen.getByText("Recent activity")).toBeInTheDocument();
        expect(screen.queryByRole("switch")).not.toBeInTheDocument();
        expect(
            screen.queryByRole("button", { name: "Edit" }),
        ).not.toBeInTheDocument();
    });

    it("only lists enabled automations", async () => {
        fetchSessionAutomationsMock.mockResolvedValue(
            makeList({
                automations: [
                    makeAutomation(),
                    makeAutomation({
                        id: "auto-2",
                        name: "Disabled rule",
                        enabled: false,
                    }),
                ],
            }),
        );

        render(<SessionAutomationsSummary mainToken="main-token" />);

        expect(await screen.findByText("Lock on freeze")).toBeInTheDocument();
        expect(screen.queryByText("Disabled rule")).not.toBeInTheDocument();
    });
});
