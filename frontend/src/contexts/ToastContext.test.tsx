import { useEffect } from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "./ToastContext";

function ToastTrigger() {
  const toast = useToast();

  useEffect(() => {
    toast.error("加载失败");
  }, [toast]);

  return null;
}

describe("ToastProvider cleanup", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("cancels pending removal timers when the provider unmounts", () => {
    vi.useFakeTimers();
    const view = render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>
    );

    expect(vi.getTimerCount()).toBe(1);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
