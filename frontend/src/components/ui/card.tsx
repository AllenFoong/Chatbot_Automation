// shadcn/ui Card（new-york v4）
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

function Card({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card"
      className={cn("flex flex-col gap-4 rounded-xl border bg-card py-5 text-card-foreground shadow-xs", className)}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "grid auto-rows-min grid-rows-[auto_auto] items-start gap-1 px-5 has-data-[slot=card-action]:grid-cols-[1fr_auto]",
        className,
      )}
      {...props}
    />
  );
}

function CardTitle({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-title" className={cn("leading-snug font-semibold", className)} {...props} />;
}

function CardDescription({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-description" className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

function CardAction({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn("col-start-2 row-span-2 row-start-1 self-start justify-self-end", className)}
      {...props}
    />
  );
}

function CardContent({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("px-5", className)} {...props} />;
}

function CardFooter({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-footer" className={cn("flex items-center px-5", className)} {...props} />;
}

/* 一排几张卡片时对齐（CSS subgrid）：每张卡片的同一块（标题、内容、按钮、最下面一行）和旁边的卡片排在同一行，
   一样高、一样的位置；一张卡片打开整条消息，旁边卡片的按钮也不会动。
   用法：<ul className={CARD_GRID}> → <li className={CARD_ROWS_4}> → <Card className={CARD_ROWS_4}>，Card 里面刚好 4 块（3 块的用 CARD_ROWS_3）。 */
const CARD_GRID = "m-0 grid list-none gap-x-4 gap-y-4 p-0 md:grid-cols-2 xl:grid-cols-3";
const CARD_ROWS_3 = "row-span-3 grid grid-rows-subgrid gap-y-4";
const CARD_ROWS_4 = "row-span-4 grid grid-rows-subgrid gap-y-4";

export { CARD_GRID, CARD_ROWS_3, CARD_ROWS_4, Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle };
