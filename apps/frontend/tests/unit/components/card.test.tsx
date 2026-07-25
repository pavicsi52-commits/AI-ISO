import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/cards/card";

describe("Card", () => {
  it("composes header, title, description, and content", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardDescription>Description</CardDescription>
        </CardHeader>
        <CardContent>Body</CardContent>
      </Card>,
    );

    expect(screen.getByText("Title")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.getByText("Body")).toBeInTheDocument();
  });

  it("merges a custom className onto the root element", () => {
    render(<Card className="custom-class" data-testid="card" />);

    expect(screen.getByTestId("card")).toHaveClass("custom-class");
  });
});
