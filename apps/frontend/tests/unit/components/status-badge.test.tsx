import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/feedback/status-badge";

describe("StatusBadge", () => {
  it.each([
    ["success", "Healthy"],
    ["warning", "Degraded"],
    ["danger", "Unreachable"],
    ["neutral", "Unknown"],
  ] as const)("renders the %s tone with its label", (tone, label) => {
    render(<StatusBadge tone={tone} label={label} />);

    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
