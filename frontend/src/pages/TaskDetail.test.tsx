import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getTask, preparePublication } from "../api/tasks";
import { ApiError } from "../api/client";
import { openExternalApp } from "../utils/externalNavigation";
import { ToastProvider } from "../contexts/ToastContext";
import { TaskDetail } from "./TaskDetail";

vi.mock("../api/tasks", () => ({
  getTask: vi.fn(),
  preparePublication: vi.fn(),
  resumeTask: vi.fn(),
}));
vi.mock("../components/AgentPipeline", () => ({ AgentPipeline: () => null }));
vi.mock("../components/AuditTimeline", () => ({
  AuditTimeline: ({ refreshKey }: { refreshKey: number }) => (
    <div data-testid="audit-refresh">{refreshKey}</div>
  ),
}));
vi.mock("../utils/externalNavigation", () => ({ openExternalApp: vi.fn() }));

const task = {
  id: 7,
  user_id: 1,
  raw_requirement: "生成长文",
  platform: "toutiao",
  status: "completed" as const,
  created_at: "2026-08-13T00:00:00Z",
  updated_at: "2026-08-13T00:00:00Z",
  copies: [{
    id: 41,
    version: 2,
    title: "当前终稿",
    content: "正文",
    hashtags: ["AI"],
    review_score: 90,
    is_final: true,
  }],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/tasks/7"]}>
      <ToastProvider>
        <Routes><Route path="/tasks/:taskId" element={<TaskDetail />} /></Routes>
      </ToastProvider>
    </MemoryRouter>
  );
}

describe("TaskDetail assisted publishing", () => {
  const clipboardWrite = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getTask).mockResolvedValue({ success: true, message: "ok", data: task });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboardWrite.mockResolvedValue(undefined) },
    });
  });

  afterEach(() => cleanup());

  it("binds the visible final copy to the Toutiao package request", async () => {
    const popup = { location: { href: "" }, opener: window, close: vi.fn() };
    vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    vi.mocked(preparePublication).mockResolvedValue({
      success: true,
      message: "ok",
      data: {
        platform: "toutiao", mode: "assisted_export", ready: true,
        requires_user_confirmation: true, copy_id: 41, title: "当前终稿",
        content: "正文", hashtags: ["AI"], package_text: "当前终稿\n\n正文\n\n#AI",
        creator_url: "https://mp.toutiao.com/profile_v4/graphic/publish",
        launch_url: null, media_url: null, media_type: null, blockers: [], instructions: [],
      },
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "复制并打开头条" }));

    await waitFor(() => expect(preparePublication).toHaveBeenCalledWith(7, {
      platform: "toutiao", copy_id: 41,
    }));
    expect(clipboardWrite).toHaveBeenCalledWith("当前终稿\n\n正文\n\n#AI");
    expect(popup.opener).toBeNull();
    expect(popup.location.href).toContain("mp.toutiao.com");
  });

  it("renders server blockers and closes the reserved popup", async () => {
    const popup = { location: { href: "" }, opener: window, close: vi.fn() };
    vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    vi.mocked(preparePublication).mockResolvedValue({
      success: true,
      message: "blocked",
      data: {
        platform: "toutiao", mode: "assisted_export", ready: false,
        requires_user_confirmation: true, copy_id: 41, title: "当前终稿",
        content: "正文", hashtags: [], package_text: "正文", creator_url: null,
        launch_url: null, media_url: null, media_type: null,
        blockers: ["发布能力暂不可用"], instructions: [],
      },
    });

    renderPage();
    const previousRefresh = Number((await screen.findByTestId("audit-refresh")).textContent);
    fireEvent.click(await screen.findByRole("button", { name: "复制并打开头条" }));

    expect(await screen.findByText("发布能力暂不可用")).toBeInTheDocument();
    expect(popup.close).toHaveBeenCalled();
    await waitFor(() =>
      expect(Number(screen.getByTestId("audit-refresh").textContent)).toBeGreaterThan(previousRefresh)
    );
  });

  it("blocks a Douyin request until a media URL is provided", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "拉起抖音发布器" }));

    expect(await screen.findByText("请先填写一个公网 HTTPS 图片或视频地址")).toBeInTheDocument();
    expect(preparePublication).not.toHaveBeenCalled();
  });

  it("offers a safe manual link when the popup is blocked", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    vi.mocked(preparePublication).mockResolvedValue({
      success: true,
      message: "ok",
      data: {
        platform: "toutiao", mode: "assisted_export", ready: true,
        requires_user_confirmation: true, copy_id: 41, title: "当前终稿",
        content: "正文", hashtags: [], package_text: "正文",
        creator_url: "https://mp.toutiao.com/profile_v4/graphic/publish",
        launch_url: null, media_url: null, media_type: null, blockers: [], instructions: [],
      },
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "复制并打开头条" }));

    const link = await screen.findByRole("link", { name: "手动打开头条创作页" });
    expect(link).toHaveAttribute("href", "https://mp.toutiao.com/profile_v4/graphic/publish");
    expect(screen.getByText("浏览器拦截了新窗口，请点击下方安全链接打开头条创作页")).toBeInTheDocument();
  });

  it("reports preparation API errors without claiming success", async () => {
    const popup = { location: { href: "" }, opener: window, close: vi.fn() };
    vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    vi.mocked(preparePublication).mockRejectedValue(new ApiError("终稿已失效", 409));

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "复制并打开头条" }));

    expect(await screen.findByText("终稿已失效")).toBeInTheDocument();
    expect(popup.close).toHaveBeenCalled();
    expect(clipboardWrite).not.toHaveBeenCalled();
  });

  it("prepares and launches a ready Douyin submission for the visible final copy", async () => {
    vi.mocked(preparePublication).mockResolvedValue({
      success: true,
      message: "ok",
      data: {
        platform: "douyin", mode: "user_confirmed_post", ready: true,
        requires_user_confirmation: true, copy_id: 41, title: "当前终稿",
        content: "正文", hashtags: ["AI"], package_text: "正文\n\n#AI",
        creator_url: null, launch_url: "snssdk1128://openplatform/share?signature=test",
        media_url: "https://cdn.example.com/cover.jpg", media_type: "image",
        blockers: [], instructions: [],
      },
    });

    renderPage();
    fireEvent.change(await screen.findByLabelText("公网 HTTPS 素材地址"), {
      target: { value: "https://cdn.example.com/cover.jpg" },
    });
    fireEvent.click(screen.getByRole("button", { name: "拉起抖音发布器" }));

    await waitFor(() => expect(preparePublication).toHaveBeenCalledWith(7, {
      platform: "douyin", copy_id: 41,
      media_url: "https://cdn.example.com/cover.jpg", media_type: "image",
    }));
    expect(clipboardWrite).toHaveBeenCalledWith("正文\n\n#AI");
    expect(openExternalApp).toHaveBeenCalledWith("snssdk1128://openplatform/share?signature=test");
  });

  it("clears a stale Toutiao fallback before showing Douyin blockers", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    vi.mocked(preparePublication)
      .mockResolvedValueOnce({
        success: true, message: "ok",
        data: {
          platform: "toutiao", mode: "assisted_export", ready: true,
          requires_user_confirmation: true, copy_id: 41, title: "当前终稿",
          content: "正文", hashtags: [], package_text: "正文",
          creator_url: "https://mp.toutiao.com/profile_v4/graphic/publish",
          launch_url: null, media_url: null, media_type: null, blockers: [], instructions: [],
        },
      })
      .mockResolvedValueOnce({
        success: true, message: "blocked",
        data: {
          platform: "douyin", mode: "user_confirmed_post", ready: false,
          requires_user_confirmation: true, copy_id: 41, title: "当前终稿",
          content: "正文", hashtags: [], package_text: "正文", creator_url: null,
          launch_url: null, media_url: "https://cdn.example.com/cover.jpg",
          media_type: "image", blockers: ["抖音能力未开通"], instructions: [],
        },
      });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "复制并打开头条" }));
    expect(await screen.findByRole("link", { name: "手动打开头条创作页" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("公网 HTTPS 素材地址"), {
      target: { value: "https://cdn.example.com/cover.jpg" },
    });
    fireEvent.click(screen.getByRole("button", { name: "拉起抖音发布器" }));

    expect(await screen.findByText("抖音能力未开通")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "手动打开头条创作页" })).not.toBeInTheDocument();
  });
});
