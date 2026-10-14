import Spinner from "@/components/Spinner";

// Fallback while the route param resolves (needed with cacheComponents).
export default function Loading() {
  return <Spinner />;
}
