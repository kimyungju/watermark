import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadZone from "../components/UploadZone";

function createFile(name, size = 100, type = "application/pdf") {
  const blob = new File([new ArrayBuffer(size)], name, { type });
  return blob;
}

describe("UploadZone", () => {
  it("renders upload prompt", () => {
    render(<UploadZone onUpload={vi.fn()} disabled={false} />);
    expect(
      screen.getByText("Drop files here or click to browse")
    ).toBeInTheDocument();
  });

  it("calls onUpload with valid files via file input", async () => {
    const onUpload = vi.fn();
    const user = userEvent.setup();
    render(<UploadZone onUpload={onUpload} disabled={false} />);

    const input = document.querySelector('input[type="file"]');
    const file = createFile("test.pdf");
    await user.upload(input, file);

    expect(onUpload).toHaveBeenCalledWith([file]);
  });

  it("rejects unsupported file type and shows error", async () => {
    const onUpload = vi.fn();
    render(<UploadZone onUpload={onUpload} disabled={false} />);

    const input = document.querySelector('input[type="file"]');
    const file = createFile("virus.exe");
    // Use fireEvent to bypass the accept attribute filtering in userEvent
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByText("virus.exe: unsupported file type")).toBeInTheDocument();
    expect(onUpload).not.toHaveBeenCalled();
  });

  it("rejects files over 10 MB", async () => {
    const onUpload = vi.fn();
    const user = userEvent.setup();
    render(<UploadZone onUpload={onUpload} disabled={false} />);

    const input = document.querySelector('input[type="file"]');
    const bigFile = createFile("big.pdf", 11 * 1024 * 1024);
    await user.upload(input, bigFile);

    expect(screen.getByText("big.pdf: exceeds 10 MB limit")).toBeInTheDocument();
    expect(onUpload).not.toHaveBeenCalled();
  });

  it("accepts valid image types", async () => {
    const onUpload = vi.fn();
    const user = userEvent.setup();
    render(<UploadZone onUpload={onUpload} disabled={false} />);

    const input = document.querySelector('input[type="file"]');
    const files = [
      createFile("a.png", 100, "image/png"),
      createFile("b.jpg", 100, "image/jpeg"),
      createFile("c.jpeg", 100, "image/jpeg"),
    ];
    await user.upload(input, files);

    expect(onUpload).toHaveBeenCalledWith(files);
  });

  it("caps at 5 files and shows error for excess", async () => {
    const onUpload = vi.fn();
    const user = userEvent.setup();
    render(<UploadZone onUpload={onUpload} disabled={false} />);

    const input = document.querySelector('input[type="file"]');
    const files = Array.from({ length: 7 }, (_, i) =>
      createFile(`f${i}.pdf`)
    );
    await user.upload(input, files);

    expect(screen.getByText(/Too many files/)).toBeInTheDocument();
    // Still uploads first 5
    expect(onUpload).toHaveBeenCalledWith(files.slice(0, 5));
  });

  it("applies disabled styling when disabled", () => {
    render(<UploadZone onUpload={vi.fn()} disabled={true} />);
    const dropZone = screen
      .getByText("Drop files here or click to browse")
      .closest("div[class*='cursor-pointer']");
    expect(dropZone.className).toContain("pointer-events-none");
  });
});
