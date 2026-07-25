import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "@/components/ui/button";

describe("Button", () => {
  it("renders its children", () => {
    render(<Button>Save</Button>);

    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("calls onClick when clicked", async () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Save</Button>);

    screen.getByRole("button").click();

    expect(handleClick).toHaveBeenCalledOnce();
  });

  it("disables the button and marks it busy while loading", () => {
    render(<Button loading>Save</Button>);

    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("respects an explicit disabled prop", () => {
    render(<Button disabled>Save</Button>);

    expect(screen.getByRole("button")).toBeDisabled();
  });
});
