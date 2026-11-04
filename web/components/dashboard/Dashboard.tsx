import { SetStatus } from "@/components/layout/StatusContext";
import { readyText } from "@/lib/format";
import type { Analysis } from "@/lib/types";
import { AskAgent } from "./AskAgent";
import { Banner } from "./Banner";
import { EventsCard } from "./EventsCard";
import { ExplanationProvider } from "./ExplanationContext";
import { PriceChart } from "./PriceChart";
import { ScenarioCard } from "./ScenarioCard";
import { StagePhaseCard } from "./StagePhaseCard";

/** Bố cục dashboard: biểu đồ ≈2/3 | cột phải; hàng dưới Kịch bản | Hỏi Agent. Một cột khi ≤ 1080px. */
export function Dashboard({ data }: { data: Analysis }) {
  return (
    <ExplanationProvider symbol={data.symbol} tf={data.timeframe}>
      <SetStatus kind="ok" text={readyText(data.symbol, data.as_of)} />
      <Banner notices={data.notices} warnings={data.warnings} />
      <main className="grid grid-cols-1 gap-4 sm:gap-5 wide:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <PriceChart data={data} />
        <div className="flex min-w-0 flex-col gap-4 sm:gap-5">
          <StagePhaseCard stage={data.stage} phase={data.phase} confidence={data.confidence} />
          <EventsCard events={data.events} />
        </div>
      </main>
      <div className="grid grid-cols-1 gap-4 sm:gap-5 wide:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <ScenarioCard levels={data.levels} target={data.target} targetDown={data.target_down} />
        <AskAgent symbol={data.symbol} tf={data.timeframe} />
      </div>
    </ExplanationProvider>
  );
}
