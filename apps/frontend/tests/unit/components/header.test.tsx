import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Header } from "@/components/layout/header";

describe("Header", () => {
  it("renders the AI-IOS brand and theme toggle within a banner landmark", () => {
    render(<Header />);

    const banner = screen.getByRole("banner");
    expect(banner).toHaveTextContent("AI-IOS");
    expect(screen.getByRole("button", { name: "Toggle theme" })).toBeInTheDocument();
  });
});
