export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-4 px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Shop Floor Video Agent</h1>
      <p className="text-zinc-600">
        Upload a short factory floor video and an AI agent reports safety events with timestamps.
      </p>
      <p className="text-sm text-zinc-500">Frontend scaffold. Pages are added in Phase 6.</p>
    </main>
  );
}
