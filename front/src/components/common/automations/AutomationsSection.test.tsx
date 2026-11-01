import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AutomationsSection from "@/components/common/automations/AutomationsSection";
import {
    createAutomation,
    createSessionAutomation,
    deleteAutomation,
    deleteSessionAutomation,
    fetchAutomationCatalog,
    fetchAutomations,
    fetchSessionAutomationCatalog,
    fetchSessionAutomations,
    updateAutomation,
    updateSessionAutomation,
} from "@/lib/http/automations";
import type {
    AutomationCatalogSchema,
    AutomationListSchema,
    AutomationSchema,
} from "@/types/api";

vi.mock("@/lib/http/automations", () => ({
    createAutomation: vi.fn(),
    createSessionAutomation: vi.fn(),
    deleteAutomation: vi.fn(),
    deleteSessionAutomation: vi.fn(),
    duplicateAutomation: vi.fn(),
    duplicateSessionAutomation: vi.fn(),
    fetchAutomationCatalog: vi.fn(),
    fetchAutomations: vi.fn(),
    fetchSessionAutomationCatalog: vi.fn(),
    fetchSessionAutomations: vi.fn(),
    updateAutomation: vi.fn(),
    updateSessionAutomation: vi.fn(),
}));

const fetchAutomationsMock = vi.mocked(fetchAutomations);
const fetchCatalogMock = vi.mocked(fetchAutomationCatalog);
const createAutomationMock = vi.mocked(createAutomation);
const updateAutomationMock = vi.mocked(updateAutomation);
const deleteAutomationMock = vi.mocked(deleteAutomation);
const fetchSessionAutomationsMock = vi.mocked(fetchSessionAutomations);
const fetchSessionCatalogMock = vi.mocked(fetchSessionAutomationCatalog);
const updateSessionAutomationMock = vi.mocked(updateSessionAutomation);
const createSessionAutomationMock = vi.mocked(createSessionAutomation);
const deleteSessionAutomationMock = vi.mocked(deleteSessionAutomation);

function makeTrigger(event: string): AutomationSchema["trigger"] {
    return {
        event,
        conditions: [],
        min_score: 0,
        count: 1,
        window_seconds: 0,
        count_mode: "images",
    };
}

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
    fetchSessionAutomationsMock.mockReset();
    fetchSessionCatalogMock.mockReset();
    updateSessionAutomationMock.mockReset();
    createSessionAutomationMock.mockReset();
    deleteSessionAutomationMock.mockReset();
    fetchAutomationsMock.mockResolvedValue(makeList());
    fetchCatalogMock.mockResolvedValue(catalog);
    createAutomationMock.mockResolvedValue(makeAutomation({ id: "auto-2" }));
    updateAutomationMock.mockResolvedValue(makeAutomation({ enabled: false }));
    deleteAutomationMock.mockResolvedValue(undefined);
    fetchSessionAutomationsMock.mockResolvedValue(makeList());
    fetchSessionCatalogMock.mockResolvedValue(catalog);
    updateSessionAutomationMock.mockResolvedValue(makeAutomation({ enabled: false }));
    createSessionAutomationMock.mockResolvedValue(makeAutomation({ id: "auto-2" }));
    deleteSessionAutomationMock.mockResolvedValue(undefined);
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("AutomationsSection", () => {
    it("lists automations and toggles one", async () => {
        const user = userEvent.setup();
        render(<AutomationsSection configurationToken="config-token" />);

        expect(await screen.findByText("Lock on freeze")).toBeInTheDocument();
        const card = screen.getByText("Lock on freeze").closest("article");
        expect(card).not.toBeNull();
        expect(within(card as HTMLElement).getByText("Active")).toBeInTheDocument();

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

    it("uses the session endpoints when rendered on the session page", async () => {
        const user = userEvent.setup();
        render(<AutomationsSection mainToken="main-token" />);

        expect(await screen.findByText("Lock on freeze")).toBeInTheDocument();
        expect(fetchSessionAutomationsMock).toHaveBeenCalledWith("main-token");
        expect(fetchSessionCatalogMock).toHaveBeenCalledWith("main-token");

        await user.click(
            screen.getByRole("switch", { name: "Disable Lock on freeze" }),
        );

        await waitFor(() =>
            expect(updateSessionAutomationMock).toHaveBeenCalledWith(
                "main-token",
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

    it("saves the new Chaster lock actions", async () => {
        const user = userEvent.setup();
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("Lock on freeze");
        await user.click(screen.getByRole("button", { name: "New automation" }));
        await user.type(
            screen.getByPlaceholderText("e.g. Eyes and Belly"),
            "Lock controls",
        );

        await user.click(
            screen.getByRole("checkbox", { name: "Freeze the Chaster lock" }),
        );
        await user.click(
            screen.getByRole("checkbox", { name: "Put the wearer in pillory" }),
        );
        await user.type(
            screen.getByPlaceholderText("Reason (optional)"),
            "Censored media",
        );
        await user.click(
            screen.getByRole("checkbox", {
                name: "Show or hide the remaining time",
            }),
        );

        await user.selectOptions(
            screen.getByRole("combobox", { name: "Remaining time visibility" }),
            "hide",
        );

        await user.click(
            screen.getByRole("button", { name: "Save automation" }),
        );

        await waitFor(() => {
            expect(createAutomationMock).toHaveBeenCalledWith(
                "config-token",
                expect.objectContaining({
                    name: "Lock controls",
                    actions: expect.arrayContaining([
                        expect.objectContaining({
                            type: "chaster.freeze",
                            params: {},
                        }),
                        expect.objectContaining({
                            type: "chaster.pillory",
                            params: {
                                duration: 300,
                                reason: "Censored media",
                            },
                        }),
                        expect.objectContaining({
                            type: "chaster.set_timer_visibility",
                            params: { display_remaining_time: false },
                        }),
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
            screen.getByRole("combobox", { name: "Trigger event" }),
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

    it("opens the template catalog from the empty state", async () => {
        const user = userEvent.setup();
        fetchAutomationsMock.mockResolvedValue(makeList({ automations: [] }));
        render(<AutomationsSection configurationToken="config-token" />);

        expect(await screen.findByText("No automations yet")).toBeInTheDocument();
        await user.click(
            screen.getByRole("button", { name: "Browse templates" }),
        );

        expect(
            screen.getByRole("tab", { name: "Templates" }),
        ).toHaveAttribute("aria-selected", "true");
        expect(screen.getByText("Synchronization")).toBeInTheDocument();
        expect(
            screen.getAllByRole("button", { name: /Eyes and Belly/ }).length,
        ).toBeGreaterThan(0);
    });

    it("keeps guard template conditions when saving", async () => {
        const user = userEvent.setup();
        fetchAutomationsMock.mockResolvedValue(makeList({ automations: [] }));
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("No automations yet");
        await user.click(
            screen.getByRole("button", { name: "Browse templates" }),
        );
        await user.click(
            screen.getByRole("button", {
                name: /Warn when PuryFi disconnects/,
            }),
        );
        await user.click(
            screen.getByRole("button", { name: "Save automation" }),
        );

        await waitFor(() => {
            expect(createAutomationMock).toHaveBeenCalledWith(
                "config-token",
                expect.objectContaining({
                    name: "Warn when PuryFi disconnects",
                    trigger: expect.objectContaining({
                        event: "puryfi.connection.disconnected",
                        conditions: [
                            {
                                field: "chaster_frozen",
                                op: "eq",
                                value: true,
                            },
                        ],
                    }),
                }),
            );
        });
    });

    it("separates my automations from templates", async () => {
        const user = userEvent.setup();
        render(<AutomationsSection configurationToken="config-token" />);

        expect(await screen.findByText("Lock on freeze")).toBeInTheDocument();
        expect(
            screen.queryByRole("button", { name: /Lock PuryFi on join/ }),
        ).not.toBeInTheDocument();

        await user.click(screen.getByRole("tab", { name: "Templates" }));

        expect(screen.queryByText("Lock on freeze")).not.toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: /Lock PuryFi on join/ }),
        ).toBeInTheDocument();
    });

    it("searches automations by name and trigger text", async () => {
        const user = userEvent.setup();
        fetchAutomationsMock.mockResolvedValue(
            makeList({
                automations: [
                    makeAutomation({ id: "auto-1", name: "Lock on freeze" }),
                    makeAutomation({
                        id: "auto-2",
                        name: "Pillory media",
                        trigger: makeTrigger("puryfi.media.scan"),
                        actions: [
                            {
                                type: "chaster.pillory",
                                params: { duration: 300 },
                                on_failure: "stop",
                            },
                        ],
                    }),
                ],
            }),
        );
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("Lock on freeze");
        const search = screen.getByRole("textbox", {
            name: "Search automations",
        });

        await user.type(search, "pillory");
        expect(screen.getByText("Pillory media")).toBeInTheDocument();
        expect(screen.queryByText("Lock on freeze")).not.toBeInTheDocument();

        await user.clear(search);
        await user.type(search, "frozen");
        expect(screen.getByText("Lock on freeze")).toBeInTheDocument();
        expect(screen.queryByText("Pillory media")).not.toBeInTheDocument();
    });

    it("filters automations by status, owner and trigger source", async () => {
        const user = userEvent.setup();
        fetchAutomationsMock.mockResolvedValue(
            makeList({
                automations: [
                    makeAutomation({
                        id: "auto-1",
                        name: "Enabled keyholder",
                        enabled: true,
                        is_owner: true,
                        owner_role: "keyholder",
                        trigger: makeTrigger("chaster.lock.frozen"),
                    }),
                    makeAutomation({
                        id: "auto-2",
                        name: "Disabled wearer",
                        enabled: false,
                        is_owner: false,
                        owner_role: "wearer",
                        trigger: makeTrigger("puryfi.media.scan"),
                    }),
                ],
            }),
        );
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("Enabled keyholder");
        const status = screen.getByRole("combobox", {
            name: "Filter by status",
        });
        const owner = screen.getByRole("combobox", { name: "Filter by owner" });
        const source = screen.getByRole("combobox", {
            name: "Filter by trigger",
        });

        await user.selectOptions(status, "disabled");
        expect(screen.getByText("Disabled wearer")).toBeInTheDocument();
        expect(screen.queryByText("Enabled keyholder")).not.toBeInTheDocument();

        await user.selectOptions(status, "all");
        await user.selectOptions(owner, "wearer");
        expect(screen.getByText("Disabled wearer")).toBeInTheDocument();
        expect(screen.queryByText("Enabled keyholder")).not.toBeInTheDocument();

        await user.selectOptions(owner, "all");
        await user.selectOptions(source, "puryfi");
        expect(screen.getByText("Disabled wearer")).toBeInTheDocument();
        expect(screen.queryByText("Enabled keyholder")).not.toBeInTheDocument();
    });

    it("sorts automations by name and last update", async () => {
        const user = userEvent.setup();
        fetchAutomationsMock.mockResolvedValue(
            makeList({
                automations: [
                    makeAutomation({
                        id: "auto-1",
                        name: "Zulu rule",
                        updated_at: "2026-02-01T00:00:00Z",
                    }),
                    makeAutomation({
                        id: "auto-2",
                        name: "Alpha rule",
                        updated_at: "2026-01-01T00:00:00Z",
                    }),
                ],
            }),
        );
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("Zulu rule");
        const sort = screen.getByRole("combobox", {
            name: "Sort automations",
        });
        const headings = () =>
            screen
                .getAllByRole("heading", { level: 3 })
                .map((heading) => heading.textContent);

        expect(headings()).toEqual(["Zulu rule", "Alpha rule"]);

        await user.selectOptions(sort, "name");
        expect(headings()).toEqual(["Alpha rule", "Zulu rule"]);

        await user.selectOptions(sort, "updated");
        expect(headings()).toEqual(["Zulu rule", "Alpha rule"]);
    });

    it("searches and filters templates by tag", async () => {
        const user = userEvent.setup();
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("Lock on freeze");
        await user.click(screen.getByRole("tab", { name: "Templates" }));

        expect(screen.getByText("Media & punishments")).toBeInTheDocument();

        const search = screen.getByRole("textbox", { name: "Search templates" });
        await user.type(search, "pillory");
        expect(
            screen.getByRole("button", { name: /Pillory for censored media/ }),
        ).toBeInTheDocument();
        expect(
            screen.queryByRole("button", { name: /Lock PuryFi on join/ }),
        ).not.toBeInTheDocument();

        await user.clear(search);
        await user.click(screen.getByRole("button", { name: "PuryFi" }));

        expect(
            screen.getByRole("button", { name: /Lock PuryFi on join/ }),
        ).toBeInTheDocument();
        expect(
            screen.queryByRole("button", {
                name: /Hide the remaining time when frozen/,
            }),
        ).not.toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Chaster" }));
        expect(
            screen.getByRole("button", { name: /Lock PuryFi on join/ }),
        ).toBeInTheDocument();
        expect(
            screen.queryByRole("button", {
                name: /Hide the remaining time when frozen/,
            }),
        ).not.toBeInTheDocument();
    });

    it("resets automation filters when nothing matches", async () => {
        const user = userEvent.setup();
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("Lock on freeze");
        await user.type(
            screen.getByRole("textbox", { name: "Search automations" }),
            "zzz",
        );

        expect(
            screen.getByText("No automations match your filters"),
        ).toBeInTheDocument();
        const [reset] = screen.getAllByRole("button", { name: "Reset filters" });
        await user.click(reset);

        expect(screen.getByText("Lock on freeze")).toBeInTheDocument();
    });

    it("returns to my automations after saving a template", async () => {
        const user = userEvent.setup();
        fetchAutomationsMock.mockResolvedValue(makeList({ automations: [] }));
        render(<AutomationsSection configurationToken="config-token" />);

        await screen.findByText("No automations yet");
        await user.click(
            screen.getByRole("button", { name: "Browse templates" }),
        );
        await user.click(
            screen.getByRole("button", { name: /Lock PuryFi on join/ }),
        );
        await user.click(
            screen.getByRole("button", { name: "Save automation" }),
        );

        await waitFor(() =>
            expect(
                screen.getByRole("tab", { name: "My automations" }),
            ).toHaveAttribute("aria-selected", "true"),
        );
    });
});
