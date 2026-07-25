import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Footer } from "@/components/layout/footer";

describe("Footer", () => {
  it("renders the product name and version within a contentinfo landmark", () => {
    render(<Footer />);

    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveTextContent("AI Infrastructure Operating System");
    expect(footer).toHaveTextContent("v0.1.0");
  });
});
