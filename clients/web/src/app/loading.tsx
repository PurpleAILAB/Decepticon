export default function GlobalLoading() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-purple-500" />
        <p className="text-sm text-zinc-500">Loading...</p>
      </div>
    </div>
  );
}
