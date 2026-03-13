import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import BeforeAfterSlider from "../components/BeforeAfterSlider";

describe("BeforeAfterSlider", () => {
  it("renders before and after images", () => {
    render(
      <BeforeAfterSlider beforeSrc="/before.png" afterSrc="/after.png" />
    );

    const imgs = screen.getAllByRole("img");
    expect(imgs).toHaveLength(2);
    expect(imgs.find((i) => i.alt === "Before")).toBeTruthy();
    expect(imgs.find((i) => i.alt === "After")).toBeTruthy();
  });

  it("shows labels after image loads", () => {
    render(
      <BeforeAfterSlider beforeSrc="/before.png" afterSrc="/after.png" />
    );

    // Labels hidden before load
    expect(screen.queryByText("Before")).not.toBeInTheDocument();

    // Simulate image load
    const afterImg = screen.getByAltText("After");
    fireEvent.load(afterImg);

    expect(screen.getByText("Before")).toBeInTheDocument();
    expect(screen.getByText("After")).toBeInTheDocument();
  });

  it("resets loaded state when sources change", () => {
    const { rerender } = render(
      <BeforeAfterSlider beforeSrc="/a.png" afterSrc="/b.png" />
    );

    // Load images
    fireEvent.load(screen.getByAltText("After"));
    expect(screen.getByText("Before")).toBeInTheDocument();

    // Change sources
    rerender(
      <BeforeAfterSlider beforeSrc="/c.png" afterSrc="/d.png" />
    );

    // Labels should be gone (loaded reset to false)
    expect(screen.queryByText("Before")).not.toBeInTheDocument();
  });

  it("starts slider at 50%", () => {
    render(
      <BeforeAfterSlider beforeSrc="/a.png" afterSrc="/b.png" />
    );

    // The before image should have clip-path at 50%
    const beforeImg = screen.getByAltText("Before");
    expect(beforeImg.style.clipPath).toBe("inset(0 50% 0 0)");
  });
});
