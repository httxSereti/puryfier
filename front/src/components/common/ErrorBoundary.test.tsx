import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ErrorBoundary from "@/components/common/ErrorBoundary";

function Bomb(): never {
    throw new Error("render exploded");
}

afterEach(() => {
    vi.restoreAllMocks();
});

describe("ErrorBoundary", () => {
    it("renders its children while nothing fails", () => {
        render(
            <ErrorBoundary>
                <p>Healthy UI</p>
            </ErrorBoundary>,
        );

        expect(screen.getByText("Healthy UI")).toBeInTheDocument();
    });

    it("shows the recovery screen after a render error", () => {
        vi.spyOn(console, "error").mockImplementation(() => {});

        render(
            <ErrorBoundary>
                <Bomb />
            </ErrorBoundary>,
        );

        expect(screen.getByText("Something went wrong")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Reload the page" })).toBeInTheDocument();
    });
});
