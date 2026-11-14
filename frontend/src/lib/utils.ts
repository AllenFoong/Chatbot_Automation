// shadcn/ui 的 cn()：合并 class，后面的 Tailwind class 盖过前面的（例 "px-2" + "px-4" = "px-4"）
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
