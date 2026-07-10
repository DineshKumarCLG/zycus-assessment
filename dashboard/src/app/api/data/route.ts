import { NextResponse } from "next/server";
import { getProjectData, getDeckData } from "@/lib/data";

export const dynamic = "force-dynamic";

export async function GET() {
  const projectHistories = getProjectData();
  const deckData = getDeckData();
  return NextResponse.json({ projectHistories, deckData });
}
