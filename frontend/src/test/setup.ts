import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear(); // 例：收起选单的选择不要带到下一个测试
});

// jsdom 没有 ResizeObserver：Radix 的 Switch 等元件要用（量元件的大小），测试里给一个什么都不做的
if (!("ResizeObserver" in globalThis)) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
