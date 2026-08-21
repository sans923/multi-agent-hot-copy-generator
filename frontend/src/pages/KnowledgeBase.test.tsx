import { cleanup, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { listKnowledgeSources } from "../api/knowledge";
import { getMemoryInsights } from "../api/memory";
import { ToastProvider } from "../contexts/ToastContext";
import { KnowledgeBase } from "./KnowledgeBase";

vi.mock("../api/knowledge", () => ({
  createKnowledgeSource: vi.fn(),
  listKnowledgeSources: vi.fn(),
  searchKnowledge: vi.fn(),
}));

vi.mock("../api/memory", () => ({ getMemoryInsights: vi.fn() }));

describe("KnowledgeBase loading", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listKnowledgeSources).mockResolvedValue({
      success: true,
      message: "ok",
      data: [],
    });
    vi.mocked(getMemoryInsights).mockRejectedValue(
      new ApiError("Not Found", 404)
    );
  });

  afterEach(() => cleanup());

  it("does not repeat the load request when an error toast is rendered", async () => {
    render(
      <ToastProvider>
        <KnowledgeBase />
      </ToastProvider>
    );

    expect(await screen.findByText("Not Found")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(getMemoryInsights).toHaveBeenCalledTimes(1);
  });

  it("stops after the expected StrictMode mount calls", async () => {
    render(
      <StrictMode>
        <ToastProvider>
          <KnowledgeBase />
        </ToastProvider>
      </StrictMode>
    );

    expect(await screen.findAllByText("Not Found")).toHaveLength(2);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(getMemoryInsights).toHaveBeenCalledTimes(2);
  });
});
