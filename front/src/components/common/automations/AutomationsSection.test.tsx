import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AutomationsSection from "@/components/common/automations/AutomationsSection";
import {
    createAutomation,
    deleteAutomation,
    fetchAutomationCatalog,
    fetchAutomations,
    updateAutomation,
} from "@/lib/http/automations";
import type {
    AutomationCatalogSchema,
    AutomationListSchema,
    AutomationSchema,
} from "@/types/api";

vi.mock("@/lib/http/automations", () => ({
    createAutomation: vi.fn(),
    deleteAutomation: vi.fn(),
    duplicateAutomation: vi.fn(),
    fetchAutomationCatalog: vi.fn(),
    fetchAutomations: vi.fn(),
    testAutomation: vi.fn(),
    updateAutomation: vi.fn(),
}));

const fetchAutomationsMock = vi.mocked(fetchAutomations);
const fetchCatalogMock = vi.mocked(fetchAutomationCatalog);
const createAutomationMock = vi.mocked(createAutomation);
const updateAutomationMock = vi.mocked(updateAutomation);
const deleteAutomationMock = vi.mocked(deleteAutomation);

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

const catalog: AutomationCatalogSchema = {
    events: [],
    actions: [],
    labels: [
        { value: "Eye", label: "Eyes", censorable: false },
        { value: "Tummy", label: "Belly", censorable: false },
    ],
};

beforeEach(() => {
    fetchAutomationsMock.mockReset();
    fetchCatalogMock.mockReset();
    createAutomationMock.mockReset();
    updateAutomationMock.mockReset();
    deleteAutomationMock.mockReset();
    fetchAutomationsMock.mockResolvedValue(makeList());
    fetchCatalogMock.mockResolvedValue(catalog);
    createAutomationMock.mockResolvedValue(makeAutomation({ id: "auto-2" }));
    updateAutomationMock.mockResolvedValue(makeAutomation({ enabled: false }));
    deleteAutomationMock.mockResolvedValue(undefined);
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("AutomationsSection", () => {
    it("lists automations and toggles one", async () => {
        const user = userEvent.setup();
        render(<AutomationsSection configurationToken="config-token" />);

        expect(await screen.findByText("Lock on freeze")).toBeInTheDocument();
        expect(screen.getByText("Active")).toBeInTheDocument();

        await user.click(
            screen.getByRole("switch", { name: "Disable Lock on freeze" }),
        );

        await waitFor(() =>
            expect(updateAutomationMock).toHaveBeenCalledWith(
                "config-token",
                "auto-1",
                { enabled: false },
            ),
        );
    });

    it("creates an automation from the editor", async () => {
        const user = userEvent.setup();
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("Lock on freeze");
        await user.click(screen.getByRole("button", { name: "New automation" }));

        const nameInput = screen.getByPlaceholderText("e.g. Eyes and Belly");
        await user.type(nameInput, "My rule");
        await user.click(screen.getByRole("button", { name: "Save automation" }));

        await waitFor(() => {
            expect(createAutomationMock).toHaveBeenCalledWith(
                "config-token",
                expect.objectContaining({
                    name: "My rule",
                    trigger: expect.objectContaining({
                        event: "chaster.lock.frozen",
                    }),
                    actions: expect.arrayContaining([
                        expect.objectContaining({ type: "puryfi.lock" }),
                    ]),
                }),
            );
        });
    });

    it("defaults media cooldowns to five seconds", async () => {
        const user = userEvent.setup();
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("Lock on freeze");
        await user.click(screen.getByRole("button", { name: "New automation" }));
        await user.selectOptions(
            screen.getByRole("combobox"),
            "puryfi.media.scan",
        );

        const cooldown = document.querySelector<HTMLInputElement>(
            "#automation-cooldown",
        );
        expect(cooldown).not.toBeNull();
        expect(cooldown?.value).toBe("5");
        expect(cooldown?.min).toBe("5");
    });

    it("confirms deletion in a dialog", async () => {
        const user = userEvent.setup();
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("Lock on freeze");
        await user.click(screen.getByRole("button", { name: "Delete" }));

        const dialog = screen.getByRole("dialog", { name: "Delete automation" });
        expect(within(dialog).getByText(/Delete “Lock on freeze”/)).toBeInTheDocument();

        await user.click(within(dialog).getByRole("button", { name: "Delete" }));

        await waitFor(() =>
            expect(deleteAutomationMock).toHaveBeenCalledWith(
                "config-token",
                "auto-1",
            ),
        );
    });

    it("shows the empty state with templates", async () => {
        fetchAutomationsMock.mockResolvedValue(makeList({ automations: [] }));
        render(<AutomationsSection configurationToken="config-token" />);

        expect(await screen.findByText("No automations yet")).toBeInTheDocument();
        expect(
            screen.getAllByRole("button", { name: /Eyes and Belly/ }).length,
        ).toBeGreaterThan(0);
    });
});
