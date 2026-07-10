import { getProjectData, getDeckData } from "@/lib/data";
import SmoothDashboard from "@/components/SmoothDashboard";

export const dynamic = "force-dynamic";

export default function Home() {
  const projectHistories = getProjectData();
  const deckData = getDeckData();

  return (
    <main className="min-h-screen bg-black">
      <SmoothDashboard projectHistories={projectHistories} deckData={deckData} />
    </main>
  );
}
