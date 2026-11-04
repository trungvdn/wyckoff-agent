"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition, type FormEvent } from "react";
import { useStatus } from "@/components/layout/StatusContext";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, Eyebrow, cx } from "@/components/ui/Card";
import { ApiError, ask, getAnalysis } from "@/lib/api";
import { readyText } from "@/lib/format";
import type { Explanation, Timeframe } from "@/lib/types";
import { useExplanation } from "./ExplanationContext";

const MAX_QUESTION = 500;

type Msg =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "agent"; text: string; sub?: string; error?: boolean; pending?: boolean };

function sourceText(e: Pick<Explanation, "source" | "model">) {
  return e.source === "llm" || e.source === "cache" ? `Diễn giải bởi ${e.model}` : "Diễn giải theo mẫu (không dùng LLM)";
}

function AgentBubble({ text, sub, error, pending }: { text: string; sub?: string; error?: boolean; pending?: boolean }) {
  return (
    <div aria-busy={pending || undefined} className={cx("flex flex-col gap-1.5 rounded-[10px] border bg-sunken px-4 py-3 leading-relaxed wrap-anywhere", error ? "border-neg-dim" : "border-line")}>
      <span className={cx("text-[13px] font-semibold", error ? "text-neg" : "text-pos")}>Agent</span>
      <p className={cx("m-0", pending && "after:content-['…'] motion-safe:after:animate-blink")}>{text}</p>
      {sub && <p className="m-0 text-xs text-muted">{sub}</p>}
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return <div className="max-w-[80%] self-end rounded-[10px] border border-line-strong bg-raised px-3.5 py-2.5 leading-relaxed wrap-anywhere">{text}</div>;
}

/** Hỏi agent bằng ngôn ngữ tự nhiên + nút Phân tích lại (bỏ cache server, cập nhật dữ liệu, diễn giải lại). */
export function AskAgent({ symbol, tf }: { symbol: string; tf: Timeframe }) {
  const router = useRouter();
  const { setStatus } = useStatus();
  const { state: ex, reload } = useExplanation();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [refreshing, startRefresh] = useTransition();
  const nextId = useRef(0);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [msgs, ex]);

  async function onAsk(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || asking) return;
    setQuestion("");
    setAsking(true);
    const uid = nextId.current++;
    const aid = nextId.current++;
    setMsgs((m) => [...m, { id: uid, role: "user", text: q }, { id: aid, role: "agent", text: "Agent đang trả lời", pending: true }]);
    let reply: Msg;
    try {
      const r = await ask(symbol, tf, q);
      reply = {
        id: aid,
        role: "agent",
        text: r.answer,
        sub: r.source === "template" ? "Trả lời theo mẫu: LLM chưa sẵn sàng hoặc câu trả lời không qua kiểm tra số liệu." : undefined,
      };
    } catch (err) {
      reply = { id: aid, role: "agent", text: `Không trả lời được: ${(err as Error).message}`, error: true };
    }
    setMsgs((m) => m.map((x) => (x.id === aid ? reply : x)));
    setAsking(false);
  }

  function onReanalyze() {
    startRefresh(async () => {
      setStatus({ kind: "loading", text: `Đang phân tích lại ${symbol}…` });
      try {
        const a = await getAnalysis(symbol, tf, { refresh: true }); // server dựng lại và giữ trong cache
        router.refresh(); // trang (server component) đọc kết quả mới
        reload();
        setStatus({ kind: "ok", text: readyText(symbol, a.as_of) });
      } catch (err) {
        setStatus({ kind: "error", text: err instanceof ApiError ? err.message : "Không phân tích lại được" });
      }
    });
  }

  return (
    <Card labelledBy="ask-h">
      <CardHeader>
        <Eyebrow id="ask-h">Hỏi Agent</Eyebrow>
        {ex.status === "ok" && <span className="text-xs text-muted">{sourceText(ex.data)}</span>}
      </CardHeader>

      <div ref={logRef} aria-live="polite" aria-relevant="additions" className="flex max-h-[360px] flex-col gap-2.5 overflow-y-auto">
        {ex.status === "loading" && <AgentBubble text="Agent đang diễn giải" pending />}
        {ex.status === "error" && <AgentBubble text={`Không lấy được diễn giải: ${ex.message}`} error />}
        {ex.status === "ok" && <AgentBubble text={ex.data.summary} sub={ex.data.context_assessment} />}
        {msgs.map((m) => (m.role === "user" ? <UserBubble key={m.id} text={m.text} /> : <AgentBubble key={m.id} {...m} />))}
      </div>

      <form onSubmit={onAsk} autoComplete="off" className="flex flex-wrap gap-2.5 sm:flex-nowrap">
        <label htmlFor="ask-question" className="sr-only">Câu hỏi cho agent</label>
        <input
          id="ask-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={MAX_QUESTION}
          placeholder="Ví dụ: Spring này có đáng tin không?"
          className="h-11 min-w-0 flex-[1_1_100%] rounded-lg border border-line-strong bg-sunken px-3.5 outline-none transition-colors placeholder:text-faint focus:border-pos sm:flex-1"
        />
        <Button type="submit" variant="ghost" disabled={asking} className="flex-1 sm:flex-none">Gửi</Button>
        <Button onClick={onReanalyze} disabled={refreshing} className="flex-1 sm:flex-none">
          {refreshing ? "Đang phân tích…" : "Phân tích lại"}
        </Button>
      </form>
    </Card>
  );
}
