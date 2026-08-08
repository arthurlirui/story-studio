export default function Loading() {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="flex items-center gap-2 text-muted-foreground">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <span className="text-sm">加载中...</span>
      </div>
    </div>
  );
}
