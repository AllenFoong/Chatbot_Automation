// shadcn/ui NativeSelect：浏览器原来的 <select>，样式和 Input 一样（选项多、要能打字找的地方用原生的比较好用，测试也照旧）
import { ChevronDownIcon } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

function NativeSelect({ className, ...props }: ComponentProps<"select">) {
  return (
    <div data-slot="native-select-wrapper" className={cn("relative w-full", className)}>
      <select
        data-slot="native-select"
        className="h-9 w-full min-w-0 cursor-pointer appearance-none rounded-md border border-input bg-card py-1 pr-9 pl-3 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50"
        {...props}
      />
      <ChevronDownIcon
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
      />
    </div>
  );
}

export { NativeSelect };
