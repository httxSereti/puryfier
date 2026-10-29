import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import NumberInput from "@/components/ui/number-input";

describe("NumberInput", () => {
    it("keeps a draft while typing and only emits valid changes", () => {
        const onChange = vi.fn();
        render(<NumberInput id="threshold" value={10} onChange={onChange} min={1} suffix="images" />);
        const input = screen.getByRole("spinbutton");

        fireEvent.change(input, { target: { value: "" } });

        expect(input).toHaveValue(null);
        expect(onChange).not.toHaveBeenCalled();
        expect(screen.getByText("images")).toBeInTheDocument();
    });

    it("clamps out-of-range values on blur", () => {
        const onChange = vi.fn();
        render(<NumberInput id="threshold" value={10} onChange={onChange} min={1} max={100} />);
        const input = screen.getByRole("spinbutton");

        fireEvent.change(input, { target: { value: "0" } });
        fireEvent.blur(input);

        expect(onChange).toHaveBeenLastCalledWith(1);
        expect(input).toHaveValue(1);
    });

    it("floors decimal values on blur", () => {
        const onChange = vi.fn();
        render(<NumberInput id="threshold" value={10} onChange={onChange} min={1} />);
        const input = screen.getByRole("spinbutton");

        fireEvent.change(input, { target: { value: "4.9" } });
        fireEvent.blur(input);

        expect(onChange).toHaveBeenLastCalledWith(4);
        expect(input).toHaveValue(4);
    });

    it("restores the current value when the draft is empty on blur", () => {
        const onChange = vi.fn();
        render(<NumberInput id="threshold" value={10} onChange={onChange} />);
        const input = screen.getByRole("spinbutton");

        fireEvent.change(input, { target: { value: "" } });
        fireEvent.blur(input);

        expect(onChange).not.toHaveBeenCalled();
        expect(input).toHaveValue(10);
    });
});
