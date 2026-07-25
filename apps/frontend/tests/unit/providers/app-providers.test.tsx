import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppProviders } from "@/providers/app-providers";

describe("AppProviders", () => {
  it("renders children without crashing", () => {
    render(
      <AppProviders>
        <p>content</p>
      </AppProviders>,
    );

    expect(screen.getByText("content")).toBeInTheDocument();
  });
});
