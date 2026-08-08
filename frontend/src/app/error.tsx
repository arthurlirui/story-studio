"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 space-y-4">
      <h2 className="text-2xl font-bold text-destructive">出错了</h2>
      <p className="text-sm text-muted-foreground max-w-md text-center">
        {error.message || "页面加载时发生未知错误"}
      </p>
      <Button onClick={reset} variant="outline">
        重试
      </Button>
    </div>
  );
}
