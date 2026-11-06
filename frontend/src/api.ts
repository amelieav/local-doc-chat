/** Calls the backend through the dev proxy (`/api` -> backend). Throws Error with the server's message. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = body?.detail;
    throw new Error(
      typeof detail === "string" ? detail : `Request failed (${String(response.status)})`,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
