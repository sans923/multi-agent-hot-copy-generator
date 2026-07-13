import type { TaskStatus } from "../types/api";



const STAGES = [

  { key: "requirement", label: "需求理解", desc: "解析意图 · 匹配热点" },

  { key: "copywriter", label: "文案创作", desc: "大纲 · 初稿 · 标签" },

  { key: "reviewer", label: "审核优化", desc: "评分 · 润色 · 终稿" },

] as const;



function stageIndex(status: TaskStatus): number {

  if (status === "pending") return 0;

  if (status === "processing") return 1;

  if (status === "awaiting_human") return 2;

  if (status === "completed") return 3;

  if (status === "failed") return -1;

  return 0;

}



export function AgentPipeline({ status }: { status: TaskStatus }) {

  const active = stageIndex(status);

  const failed = status === "failed";

  const awaiting = status === "awaiting_human";



  return (

    <div className="agent-pipeline">

      {STAGES.map((stage, i) => {

        const done = !failed && !awaiting && active > i;

        const current =

          (!failed && !awaiting && active === i) ||

          (awaiting && i === 2);

        const failHere = failed && i === Math.min(active, 2);

        const pauseHere = awaiting && i === 2;



        return (

          <div

            key={stage.key}

            className={`pipeline-step ${done ? "done" : ""} ${current ? "active" : ""} ${failHere ? "failed" : ""} ${pauseHere ? "paused" : ""}`}

          >

            <div className="pipeline-dot">

              {done ? "✓" : pauseHere ? "!" : i + 1}

            </div>

            <div className="pipeline-body">

              <strong>{stage.label}</strong>

              <span>

                {pauseHere ? "需人工确认 · 验证未通过" : stage.desc}

              </span>

            </div>

            {i < STAGES.length - 1 && <div className="pipeline-line" />}

          </div>

        );

      })}

    </div>

  );

}

