import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AutomationActivity from "@/components/common/automations/AutomationActivity";
import type { AutomationExecutionSchema } from "@/types/api";

function makeExecution(
    overrides: Partial<AutomationExecutionSchema> = {},
): AutomationExecutionSchema {
    return {
        id: "exec-1",
        session_id: "session-1",
        automation_id: "auto-1",
        automation_name: "Lock on freeze",
        event_id: "event-1",
        event_type: "chaster.lock.frozen",
        status: "success",
        actions: [
            { type: "puryfi.lock", status: "success" },
            { type: "puryfi.enable", status: "success" },
        ],
        error: null,
        started_at: "2026-11-01T12:00:00.000Z",
        finished_at: "2026-11-01T12:00:00.240Z",
        ...overrides,
    };
}

describe("AutomationActivity", () => {
    it("shows the automation, trigger source, duration and action outcomes", () => {
        render(<AutomationActivity executions={[makeExecution()]} />);

        expect(screen.getByText("Lock on freeze")).toBeInTheDocument();
        expect(screen.getByText("Success")).toBeInTheDocument();
        expect(screen.getByText("Chaster")).toBeInTheDocument();
        expect(screen.getByText("Lock frozen")).toBeInTheDocument();
        expect(screen.getByText("240 ms")).toBeInTheDocument();
        expect(screen.getByText("Lock PuryFi")).toBeInTheDocument();
        expect(screen.getByText("Enable PuryFi")).toBeInTheDocument();
    });

    it("surfaces partial failures and the execution error", () => {
        render(
            <AutomationActivity
                executions={[
                    makeExecution({
                        status: "partial",
                        error: "Chaster rejected the action",
                        actions: [
                            { type: "puryfi.unlock", status: "success" },
                            {
                                type: "chaster.add_time",
                                status: "failed",
                                error: "Chaster rejected the action",
                            },
                        ],
                    }),
                ]}
            />,
        );

        expect(screen.getByText("Partial")).toBeInTheDocument();
        expect(
            screen.getByText("Chaster rejected the action"),
        ).toBeInTheDocument();
        expect(
            screen.getByLabelText(
                "Add time: failed — Chaster rejected the action",
            ),
        ).toBeInTheDocument();
    });

    it("renders an empty state when nothing has run", () => {
        render(<AutomationActivity executions={[]} />);

        expect(screen.getByText("No runs yet")).toBeInTheDocument();
    });
});
