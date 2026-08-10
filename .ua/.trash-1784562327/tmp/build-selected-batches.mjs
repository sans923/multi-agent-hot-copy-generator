import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const ua = path.join(root, ".ua");
const all = JSON.parse(fs.readFileSync(path.join(ua, "intermediate", "batches.json"), "utf8"));
const selected = new Set([1, 4, 7, 10]);

const cnName = (p) => path.basename(p).replace(/\.[^.]+$/, "").replaceAll("_", " ");
const complexity = (n) => n < 50 ? "simple" : n <= 200 ? "moderate" : "complex";
const edge = (source, target, type, weight) => ({ source, target, type, direction: "forward", weight });
const exported = (r, name) => (r.exports || []).some((x) => x.name === name);

function purpose(p, category) {
  const n = cnName(p);
  if (p.includes("test")) return `验证“${n}”相关行为、边界条件与回归场景，保障热点文案流水线的关键能力稳定。`;
  if (p.includes("agentic_runners")) return "实现智能体式任务流水线的分类、规划、逐步执行、反思和质量门禁，并支持检查点恢复与人工介入。";
  if (p.includes("pipeline_runners")) return "编排需求分析、文案生成、审核和主控智能体阶段，统一任务状态推进、失败处理与最终结果落库。";
  if (p.includes("pipeline_state")) return "定义多智能体流水线的状态结构、计划步骤及成功、失败、超时和等待人工等结果构造逻辑。";
  if (p.includes("/skills/")) return `提供“${n}”领域的可调用 Skill，将文案生成、合规、RAG、平台适配或风格处理能力封装为统一执行接口。`;
  if (p.includes("/agents/")) return `实现“${n}”智能体及其协作逻辑，承担热点爆款文案生成流水线中的专门角色。`;
  if (p.includes("/services/")) return `提供“${n}”业务服务，为多智能体热点文案生成流程封装可复用的领域能力。`;
  if (p.includes("/graph/")) return `构建“${n}”LangGraph 状态图，声明智能体节点、条件路由和流水线执行入口。`;
  if (p.includes("/models/")) return `定义“${n}”持久化数据模型，保存热点素材、任务或编排相关业务数据。`;
  if (p.includes("/utils/")) return `提供“${n}”基础工具，统一日志、模型角色或 LLM 客户端等横切能力。`;
  if (p === "Dockerfile") return "采用多阶段构建打包前端与 Python 后端，生成包含运行依赖、健康检查和非 root 用户的生产容器镜像。";
  if (p === "docker-compose.yml") return "编排应用与 MySQL 服务，配置构建、环境变量、数据卷、健康检查和服务启动依赖。";
  if (p.endsWith("README.md")) return "说明前端工程的开发、构建与质量检查方式，并概述 Vite、React 和 TypeScript 项目结构。";
  if (p.endsWith("package.json")) return "声明 React 前端的脚本、运行时依赖和开发工具链版本，控制开发、构建、检查与预览命令。";
  if (p.endsWith("tsconfig.json")) return "配置前端 TypeScript 编译目标、严格检查、模块解析与 JSX 转换策略。";
  if (p.endsWith(".env.example")) return "给出前端环境变量示例，约定访问后端 API 时使用的基础地址。";
  if (p.endsWith("index.html")) return "提供 Vite 前端的 HTML 宿主页，声明挂载节点并加载 React 应用入口。";
  if (category === "config") return `配置“${n}”相关工具或运行参数。`;
  if (category === "docs") return `记录“${n}”相关使用说明与项目约定。`;
  return `实现“${n}”模块，为多智能体热点爆款文案生成系统提供对应能力。`;
}

function fileTags(p, category) {
  if (p.includes("test")) return ["测试", "回归验证", "质量保障"];
  if (category === "infra") return ["基础设施", "容器化", p.includes("compose") ? "服务编排" : "部署"];
  if (category === "config") return ["配置", p.includes("tsconfig") ? "typescript" : "构建系统", "前端"];
  if (category === "docs") return ["文档", "前端", "开发指南"];
  if (category === "markup") return ["前端", "html", "入口页面"];
  if (p.includes("/skills/")) return ["skill", "工具调用", "能力封装"];
  if (p.includes("/agents/")) return ["智能体", "流程编排", "文案生成"];
  if (p.includes("/services/")) return ["业务服务", "领域逻辑", "流程支撑"];
  if (p.includes("/graph/")) return ["langgraph", "状态图", "流程编排"];
  return ["python", "业务逻辑", "热点文案"];
}

function symbolSummary(name, kind, p) {
  const display = name.replaceAll("_", " ");
  if (kind === "class") return `封装“${display}”的状态与行为，作为 ${purpose(p, "code").replace(/。$/, "")}的核心对象。`;
  if (name.startsWith("test_")) return `验证 ${display.slice(5)} 场景的预期行为与回归约束。`;
  if (name === "main") return "解析运行参数并启动该脚本的主流程。";
  if (name.startsWith("build_")) return `构建 ${display.slice(6)} 所需的结构、状态或执行对象。`;
  if (name.startsWith("run_")) return `执行 ${display.slice(4)} 流程并返回标准化结果。`;
  return `实现“${display}”处理逻辑，服务于该模块承担的热点文案生成职责。`;
}

function makeFragment(batch, extraction) {
  const nodes = [], edges = [];
  const analyzedPaths = new Set(extraction.results.map((r) => r.path));
  for (const r of extraction.results) {
    const p = r.path;
    const category = r.fileCategory;
    let type = "file";
    if (category === "config") type = "config";
    else if (category === "docs") type = "document";
    else if (category === "infra") type = "service";
    const fid = `${type}:${p}`;
    const fn = {
      id: fid, type, name: path.basename(p), filePath: p,
      summary: purpose(p, category), tags: fileTags(p, category),
      complexity: complexity(r.nonEmptyLines ?? r.totalLines ?? 0)
    };
    if (p.endsWith(".py")) fn.languageNotes = "采用 Python 类型标注与模块化服务边界组织同步或异步业务流程。";
    nodes.push(fn);

    for (const target of batch.batchImportData[p] || []) edges.push(edge(fid, `file:${target}`, "imports", 0.7));

    for (const f of r.functions || []) {
      if ((f.endLine - f.startLine + 1) < 10 && !exported(r, f.name)) continue;
      const id = `function:${p}:${f.name}`;
      nodes.push({
        id, type: "function", name: f.name, filePath: p,
        lineRange: [f.startLine, f.endLine], summary: symbolSummary(f.name, "function", p),
        tags: p.includes("test") ? ["测试用例", "回归验证", "pytest"] : ["函数", "业务逻辑", "流程处理"],
        complexity: complexity(f.endLine - f.startLine + 1)
      });
      edges.push(edge(fid, id, "contains", 1.0));
      if (exported(r, f.name)) edges.push(edge(fid, id, "exports", 0.8));
    }
    for (const c of r.classes || []) {
      if ((c.endLine - c.startLine + 1) < 20 && (c.methods || []).length < 2 && !exported(r, c.name)) continue;
      const id = `class:${p}:${c.name}`;
      nodes.push({
        id, type: "class", name: c.name, filePath: p,
        lineRange: [c.startLine, c.endLine], summary: symbolSummary(c.name, "class", p),
        tags: ["类", p.includes("/agents/") ? "智能体" : p.includes("/skills/") ? "skill" : "领域对象", "行为封装"],
        complexity: complexity(c.endLine - c.startLine + 1)
      });
      edges.push(edge(fid, id, "contains", 1.0));
      if (exported(r, c.name)) edges.push(edge(fid, id, "exports", 0.8));
    }
    for (const s of r.services || []) {
      const name = s.name || s.stage || s.kind;
      if (!name) continue;
      const id = `service:${p}:${name}`;
      nodes.push({ id, type: "service", name, filePath: p, summary: `定义并运行“${name}”容器服务或构建阶段。`, tags: ["基础设施", "容器服务", "服务编排"], complexity: "simple" });
      edges.push(edge(fid, id, "contains", 1.0));
    }
  }
  for (const f of batch.files.filter((x) => !analyzedPaths.has(x.path))) {
    const type = f.fileCategory === "config" ? "config" : f.fileCategory === "docs" ? "document" : f.fileCategory === "infra" ? "service" : "file";
    nodes.push({
      id: `${type}:${f.path}`, type, name: path.basename(f.path), filePath: f.path,
      summary: purpose(f.path, f.fileCategory), tags: fileTags(f.path, f.fileCategory),
      complexity: complexity(f.sizeLines)
    });
    for (const target of batch.batchImportData[f.path] || []) edges.push(edge(`${type}:${f.path}`, `file:${target}`, "imports", 0.7));
  }
  if (batch.batchIndex === 7) {
    edges.push(edge("service:docker-compose.yml", "service:Dockerfile", "depends_on", 0.6));
    edges.push(edge("service:Dockerfile", "file:app/main.py", "deploys", 0.7));
  }
  if (batch.batchIndex === 10) {
    edges.push(edge("config:frontend/tsconfig.json", "file:frontend/src/main.tsx", "configures", 0.6));
    edges.push(edge("config:frontend/package.json", "file:frontend/src/main.tsx", "configures", 0.6));
    edges.push(edge("document:frontend/README.md", "file:frontend/src/main.tsx", "documents", 0.5));
    edges.push(edge("file:frontend/index.html", "file:frontend/src/main.tsx", "depends_on", 0.6));
  }
  return { nodes, edges };
}

for (const batch of all.batches.filter((b) => selected.has(b.batchIndex))) {
  const extraction = JSON.parse(fs.readFileSync(path.join(ua, "tmp", `ua-file-extract-results-${batch.batchIndex}.json`), "utf8"));
  const graph = makeFragment(batch, extraction);
  const parts = Math.ceil(Math.max(graph.nodes.length / 60, graph.edges.length / 120, 1));
  const old = fs.readdirSync(path.join(ua, "intermediate")).filter((n) => new RegExp(`^batch-${batch.batchIndex}(?:-part-\\d+)?\\.json$`).test(n));
  for (const n of old) fs.unlinkSync(path.join(ua, "intermediate", n));
  if (parts === 1) {
    fs.writeFileSync(path.join(ua, "intermediate", `batch-${batch.batchIndex}.json`), JSON.stringify(graph, null, 2));
  } else {
    const files = [...batch.files].map((x) => x.path).sort();
    const groupSize = Math.ceil(files.length / parts);
    for (let k = 0; k < parts; k++) {
      const group = new Set(files.slice(k * groupSize, (k + 1) * groupSize));
      const partNodes = graph.nodes.filter((n) => group.has(n.filePath));
      const ids = new Set(partNodes.map((n) => n.id));
      const partEdges = graph.edges.filter((e) => ids.has(e.source));
      fs.writeFileSync(path.join(ua, "intermediate", `batch-${batch.batchIndex}-part-${k + 1}.json`), JSON.stringify({ nodes: partNodes, edges: partEdges }, null, 2));
    }
  }
  process.stdout.write(`batch ${batch.batchIndex}: ${parts} part(s), ${graph.nodes.length} nodes, ${graph.edges.length} edges\n`);
}
