import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CensoredMediaOptions from "@/components/common/configuration/CensoredMediaOptions";
import { defaultConfig } from "@/test/fixtures";

describe("CensoredMediaOptions", () => {
    it("toggles the feature and emits the updated config", async () => {
        const onChange = vi.fn();
        const user = userEvent.setup();
        render(<CensoredMediaOptions config={defaultConfig} onChange={onChange} />);

        await user.click(
            screen.getByRole("switch", { name: "Add time when media is censored" }),
        );

        expect(onChange).toHaveBeenCalledWith({
            ...defaultConfig,
            censorPicsConfig: {
                ...defaultConfig.censorPicsConfig,
                enabled: false,
            },
        });
    });

    it("updates the threshold and duration through the number inputs", async () => {
        const onChange = vi.fn();
        const user = userEvent.setup();
        render(<CensoredMediaOptions config={defaultConfig} onChange={onChange} />);

        const threshold = screen.getByLabelText("Censored media threshold");
        await user.clear(threshold);
        await user.type(threshold, "25");
        await user.tab();

        expect(onChange).toHaveBeenLastCalledWith({
            ...defaultConfig,
            censorPicsConfig: {
                ...defaultConfig.censorPicsConfig,
                limit_count: 25,
            },
        });
    });

    it("renders human-readable values in read-only mode", () => {
        render(<CensoredMediaOptions config={defaultConfig} readOnly />);

        expect(screen.getByRole("switch", { name: "Add time when media is censored" })).toBeDisabled();
        expect(screen.getByText("Threshold")).toBeInTheDocument();
        expect(screen.getByText("10 images")).toBeInTheDocument();
        expect(screen.getByText("Time added")).toBeInTheDocument();
        expect(screen.getByText("10m")).toBeInTheDocument();
    });

    it("hides the fine-grained options when the feature is disabled", () => {
        render(
            <CensoredMediaOptions
                config={{
                    ...defaultConfig,
                    censorPicsConfig: { ...defaultConfig.censorPicsConfig, enabled: false },
                }}
                onChange={vi.fn()}
            />,
        );

        expect(screen.queryByLabelText("Censored media threshold")).not.toBeInTheDocument();
        expect(
            screen.getByText("Enable this option to set a censored media threshold and time penalty."),
        ).toBeInTheDocument();
    });
});
