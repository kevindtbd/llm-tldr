// Bug 3 fixture: route with @/ alias imports
// Call graph should resolve @/lib/helpers to lib/helpers.ts

import { requireAuth, apiError } from "@/lib/helpers";
import { getDbHealth } from "@/lib/db";

export async function GET() {
  const auth = await requireAuth();
  if (!auth) return apiError(401, "Unauthorized");
  return { ok: true };
}

export async function POST(req: Request) {
  const auth = await requireAuth();
  if (!auth) return apiError(401, "Unauthorized");
  const healthy = getDbHealth();
  return { ok: healthy };
}
