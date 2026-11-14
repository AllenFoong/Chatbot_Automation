// shadcn/ui Avatar（只有字母，没有图片）
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

function Avatar({ className, ...props }: ComponentProps<"span">) {
  return (
    <span
      data-slot="avatar"
      className={cn(
        "relative flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-brand-soft text-xs font-semibold text-brand-text",
        className,
      )}
      {...props}
    />
  );
}

export { Avatar };
