import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const ua = path.join(root, ".ua");
const batchesDoc = JSON.parse(
  fs.readFileSync(path.join(ua, "intermediate", "batches.json"), "utf8"),
);

const exactFileSummaries = {
  "app/agents/agentic_runners.py": "实现智能体流水线各阶段的执行、步骤结果处理、质量门禁以及中断后的恢复，是复杂任务编排的核心运行层。",
  "app/agents/lead_agent.py": "实现主管智能体，负责选择执行路径、协调专业智能体并汇总多阶段文案生成结果。",
  "app/agents/model_roles.py": "定义智能体模型角色及其解析规则，为不同阶段选择合适的模型配置。",
  "app/agents/orchestrator.py": "提供传统多智能体编排器，串联需求分析、文案生成、审核和持久化流程。",
  "app/agents/pipeline_context.py": "构造并维护流水线上下文，把任务、用户输入、模型配置和中间结果传递给各阶段。",
  "app/agents/pipeline_runners.py": "封装流水线阶段运行函数，负责调用智能体、记录结果并推进任务状态。",
  "app/agents/pipeline_state.py": "定义智能体流水线的状态结构、状态转换和序列化辅助逻辑。",
  "app/lang/graph/agentic_pipeline_graph.py": "构建复杂任务的 LangGraph 状态图，连接分类、规划、执行、反思、验证和人工确认节点。",
  "app/lang/graph/lead_pipeline_graph.py": "构建主管智能体主导的 LangGraph 流程图，组织专业智能体之间的分派和汇总。",
  "app/config.py": "集中声明应用运行配置，并从环境变量加载数据库、鉴权、模型和外部服务参数。",
  "app/scheduler.py": "配置后台定时任务，用于周期性同步热点数据并管理调度器生命周期。",
  "app/utils/llm_client.py": "统一封装大模型客户端创建、请求调用、响应解析和异常处理。",
  "app/utils/model_roles.py": "根据任务阶段解析模型角色并返回对应的大模型配置。",
  "app/main.py": "FastAPI 应用入口，注册路由、中间件、生命周期钩子、异常处理器和健康检查。",
  "app/database.py": "创建 SQLAlchemy 引擎与会话，兼容不同数据库并提供依赖注入和建表入口。",
  "app/core/security.py": "实现密码哈希校验、JWT 访问令牌签发和解码等认证安全能力。",
  "app/core/deps.py": "提供 FastAPI 鉴权依赖，解析当前用户并执行活跃状态与管理员权限检查。",
  "frontend/src/App.tsx": "定义前端顶层路由树，将公开页面、受保护页面和管理员页面组合到统一布局中。",
  "frontend/src/main.tsx": "React 前端入口，挂载应用并注入路由、认证和提示消息等全局上下文。",
  "frontend/src/api/client.ts": "封装浏览器端 HTTP 客户端、令牌存取、统一响应解析和 API 错误模型。",
  "frontend/src/contexts/AuthContext.tsx": "提供全局认证上下文，管理登录用户、令牌恢复、登录注册和退出状态。",
  "frontend/src/contexts/ToastContext.tsx": "提供全局提示消息上下文，管理临时通知的创建、展示与自动消失。",
  "frontend/src/types/api.ts": "集中定义前后端 API 的请求、响应、任务、日志、热点和内容资产类型。",
};

const servicePurposes = {
  audit_service: "记录和查询编排审计轨迹，确保各智能体步骤可追踪",
  embedding_service: "生成向量嵌入并维护内容检索所需的索引数据",
  judge_service: "对候选文案执行结构化质量评判并输出评分结论",
  longform_mvp_service: "执行长文生成 MVP 流程并组织分段产物",
  orchestration_persistence: "持久化编排状态、中间步骤和恢复所需快照",
  orchestration_policy: "根据任务特征和执行结果决定编排策略、跳过条件与人工介入",
  planner_service: "把复杂任务拆解为可执行步骤并生成结构化计划",
  reflect_service: "反思阶段产出改进建议并更新后续执行上下文",
  task_classifier: "识别任务复杂度和类型，为流水线路由提供依据",
  verify_service: "验证阶段检查产物是否满足约束和质量要求",
  hotlist_service: "拉取、清洗、保存和查询多平台热点榜单数据",
};

function stem(filePath) {
  return path.posix.basename(filePath).replace(/\.(py|tsx?|jsx?)$/, "");
}

function humanize(name) {
  return name
    .replace(/^_+/, "")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .trim();
}

function fileSummary(filePath) {
  if (exactFileSummaries[filePath]) return exactFileSummaries[filePath];
  const s = stem(filePath);
  if (filePath.startsWith("tests/")) {
    return `覆盖 ${humanize(s.replace(/^test_/, ""))} 相关行为的自动化测试，验证正常流程、边界条件和关键回归场景。`;
  }
  if (filePath.startsWith("scripts/")) {
    return `提供 ${humanize(s)} 的项目维护脚本，用于初始化、数据准备或外部服务连通性检查。`;
  }
  if (filePath.startsWith("app/api/")) {
    return `实现 ${humanize(s)} 领域的 FastAPI 路由，完成请求校验、权限控制、服务调用和响应组装。`;
  }
  if (filePath.startsWith("app/models/")) {
    return `定义 ${humanize(s)} 的 SQLAlchemy 持久化模型、字段约束及数据库关系。`;
  }
  if (filePath.startsWith("app/schemas/")) {
    return `定义 ${humanize(s)} 领域的 Pydantic 请求与响应结构，用于 API 校验和序列化。`;
  }
  if (filePath.startsWith("app/services/")) {
    return `${servicePurposes[s] ?? `封装 ${humanize(s)} 领域业务逻辑`}，供 API 层和智能体流水线复用。`;
  }
  if (filePath.startsWith("app/skills/")) {
    if (s === "__init__") return "汇总并导出项目内置技能，使编排器能够从统一包入口加载技能实现。";
    if (s === "base") return "定义技能抽象、注册表和执行器，为具体文案技能提供统一调用与审计协议。";
    if (s === "skill_response") return "定义技能执行结果的标准信封和兼容旧格式的归一化逻辑。";
    return `实现 ${humanize(s)} 领域的可注册技能，把专业处理能力暴露给智能体编排器。`;
  }
  if (filePath.startsWith("app/agents/")) {
    return `实现 ${humanize(s)} 相关智能体能力，参与任务分析、生成、审核或流水线协调。`;
  }
  if (filePath.startsWith("app/utils/")) {
    return `提供 ${humanize(s)} 通用辅助能力，供后端多个模块复用。`;
  }
  if (filePath.startsWith("frontend/src/api/")) {
    return `封装 ${humanize(s)} 领域的前端 API 调用，并复用统一 HTTP 客户端处理认证与错误。`;
  }
  if (filePath.startsWith("frontend/src/components/")) {
    return `实现 ${humanize(s)} 可复用 React 组件，承担界面展示、导航或访问控制职责。`;
  }
  if (filePath.startsWith("frontend/src/pages/")) {
    return `实现 ${humanize(s)} 业务页面，协调接口请求、交互状态和结果展示。`;
  }
  if (filePath.endsWith("__init__.py")) {
    return "定义 Python 包公共入口并集中导出该目录下的核心类型与能力。";
  }
  return `实现 ${humanize(s)} 模块的核心职责，并为项目其他组件提供可复用接口。`;
}

function fileTags(filePath) {
  if (filePath.startsWith("tests/")) return ["test", "regression", "quality-assurance"];
  if (filePath.startsWith("app/api/")) return ["api-handler", "fastapi", "validation"];
  if (filePath.startsWith("app/models/")) return ["data-model", "sqlalchemy", "database"];
  if (filePath.startsWith("app/schemas/")) return ["validation", "serialization", "type-definition"];
  if (filePath.startsWith("app/services/")) return ["service", "business-logic", "backend"];
  if (filePath.startsWith("app/skills/")) return ["skill", "plugin-system", "agent-tool"];
  if (filePath.startsWith("app/agents/")) return ["agent", "orchestration", "llm"];
  if (filePath.includes("/lang/graph/")) return ["langgraph", "workflow", "state-machine"];
  if (filePath.startsWith("frontend/src/api/")) return ["api-client", "frontend", "http"];
  if (filePath.startsWith("frontend/src/components/")) return ["component", "react", "ui"];
  if (filePath.startsWith("frontend/src/contexts/")) return ["context", "react", "state-management"];
  if (filePath.startsWith("frontend/src/pages/")) return ["page", "react", "ui"];
  if (filePath.startsWith("scripts/")) return ["script", "development", "automation"];
  if (filePath === "app/main.py" || filePath === "frontend/src/main.tsx" || filePath === "run.py") {
    return ["entry-point", "bootstrap", "application"];
  }
  return ["backend", "module", "application"];
}

function entitySummary(kind, name, filePath) {
  const h = humanize(name);
  const low = name.toLowerCase();
  if (low.startsWith("test")) return `验证 ${humanize(name.replace(/^test_?/, ""))} 场景，防止相关行为发生回归。`;
  if (low.includes("login")) return "处理用户登录流程，校验凭据并建立认证会话。";
  if (low.includes("register")) return "处理用户注册流程，校验输入并创建新的用户账户。";
  if (low.includes("classify")) return "分析任务输入并生成分类结果，为后续流水线路由提供依据。";
  if (low.includes("plan")) return "生成或检查结构化执行计划，驱动复杂任务逐步推进。";
  if (low.includes("resume")) return "从持久化状态恢复中断任务，并按用户动作继续执行流水线。";
  if (low.includes("audit")) return "记录或读取编排审计信息，使任务执行过程可追踪。";
  if (low.includes("verify")) return "检查生成结果是否满足约束，并返回结构化验证结论。";
  if (low.includes("reflect")) return "分析当前产物与反馈，形成用于下一轮改进的反思结果。";
  if (low.includes("sync")) return "执行外部热点数据同步，并维护数据库中的最新状态。";
  if (low.startsWith("get") || low.startsWith("list") || low.startsWith("fetch")) {
    return `读取 ${h} 对应的数据，完成必要的筛选、转换和响应组装。`;
  }
  if (low.startsWith("create") || low.startsWith("build")) {
    return `创建 ${h} 对应的业务对象或产物，并处理相关持久化状态。`;
  }
  if (low.startsWith("run") || low.startsWith("execute")) {
    return `执行 ${h} 对应的处理阶段，协调依赖并返回结构化结果。`;
  }
  if (low.startsWith("check") || low.startsWith("validate")) {
    return `检查 ${h} 对应的规则或输入，并返回可供流水线判断的结果。`;
  }
  if (kind === "class") {
    return `封装 ${h} 的状态与行为，是 ${humanize(stem(filePath))} 模块的核心类型。`;
  }
  return `实现 ${h} 处理逻辑，服务于 ${humanize(stem(filePath))} 模块的核心流程。`;
}

function complexity(lines) {
  if (lines > 200) return "complex";
  if (lines >= 50) return "moderate";
  return "simple";
}

function entityTags(kind, name, filePath) {
  const tags = kind === "class" ? ["class", "domain-logic"] : ["function", "business-logic"];
  if (filePath.startsWith("tests/")) tags.push("test");
  else if (filePath.includes("/api/")) tags.push("api-handler");
  else if (filePath.includes("/skills/")) tags.push("agent-tool");
  else if (filePath.includes("/agents/")) tags.push("orchestration");
  else if (filePath.startsWith("frontend/")) tags.push("frontend");
  else tags.push("backend");
  return tags;
}

function isExported(result, name) {
  return (result.exports ?? []).some((item) => item.name === name);
}

function makeFragment(batchIndex) {
  const batch = batchesDoc.batches.find((item) => item.batchIndex === batchIndex);
  const extracted = JSON.parse(
    fs.readFileSync(path.join(ua, "tmp", `ua-file-extract-results-${batchIndex}.json`), "utf8"),
  );
  if (!extracted.scriptCompleted || extracted.results.length !== batch.files.length) {
    throw new Error(`批次 ${batchIndex} 的结构抽取不完整`);
  }

  const nodes = [];
  const edges = [];
  for (const result of extracted.results) {
    nodes.push({
      id: `file:${result.path}`,
      type: "file",
      name: path.posix.basename(result.path),
      filePath: result.path,
      summary: fileSummary(result.path),
      tags: fileTags(result.path),
      complexity: complexity(result.nonEmptyLines),
    });

    for (const fn of result.functions ?? []) {
      const exported = isExported(result, fn.name);
      if (fn.endLine - fn.startLine + 1 < 10 && !exported) continue;
      const id = `function:${result.path}:${fn.name}`;
      nodes.push({
        id,
        type: "function",
        name: fn.name,
        filePath: result.path,
        lineRange: [fn.startLine, fn.endLine],
        summary: entitySummary("function", fn.name, result.path),
        tags: entityTags("function", fn.name, result.path),
        complexity: complexity(fn.endLine - fn.startLine + 1),
      });
      edges.push({
        source: `file:${result.path}`,
        target: id,
        type: "contains",
        direction: "forward",
        weight: 1.0,
      });
      if (exported) {
        edges.push({
          source: `file:${result.path}`,
          target: id,
          type: "exports",
          direction: "forward",
          weight: 0.8,
        });
      }
    }

    for (const cls of result.classes ?? []) {
      if (!cls.name || cls.name === "-") continue;
      const exported = isExported(result, cls.name);
      const methodCount = Array.isArray(cls.methods) ? cls.methods.length : 0;
      if (cls.endLine - cls.startLine + 1 < 20 && methodCount < 2 && !exported) continue;
      const id = `class:${result.path}:${cls.name}`;
      nodes.push({
        id,
        type: "class",
        name: cls.name,
        filePath: result.path,
        lineRange: [cls.startLine, cls.endLine],
        summary: entitySummary("class", cls.name, result.path),
        tags: entityTags("class", cls.name, result.path),
        complexity: complexity(cls.endLine - cls.startLine + 1),
      });
      edges.push({
        source: `file:${result.path}`,
        target: id,
        type: "contains",
        direction: "forward",
        weight: 1.0,
      });
      if (exported) {
        edges.push({
          source: `file:${result.path}`,
          target: id,
          type: "exports",
          direction: "forward",
          weight: 0.8,
        });
      }
    }

    for (const target of batch.batchImportData[result.path] ?? []) {
      edges.push({
        source: `file:${result.path}`,
        target: `file:${target}`,
        type: "imports",
        direction: "forward",
        weight: 0.7,
      });
    }
  }
  return { batch, nodes, edges };
}

function writeParts(batchIndex, fragment) {
  const outDir = path.join(ua, "intermediate");
  for (const name of fs.readdirSync(outDir)) {
    if (new RegExp(`^batch-${batchIndex}(?:-part-\\d+)?\\.json$`).test(name)) {
      fs.rmSync(path.join(outDir, name));
    }
  }

  const sortedFiles = fragment.batch.files.map((item) => item.path).sort();
  const groups = [];
  let current = [];
  let currentNodeCount = 0;
  let currentEdgeCount = 0;
  for (const filePath of sortedFiles) {
    const fileNodes = fragment.nodes.filter((node) => node.filePath === filePath);
    const fileNodeIds = new Set(fileNodes.map((node) => node.id));
    const fileEdges = fragment.edges.filter((edge) => fileNodeIds.has(edge.source));
    if (
      current.length > 0 &&
      (currentNodeCount + fileNodes.length > 60 ||
        currentEdgeCount + fileEdges.length > 120)
    ) {
      groups.push(current);
      current = [];
      currentNodeCount = 0;
      currentEdgeCount = 0;
    }
    current.push(filePath);
    currentNodeCount += fileNodes.length;
    currentEdgeCount += fileEdges.length;
  }
  if (current.length > 0) groups.push(current);

  const partCount = groups.length;
  const written = [];
  for (let part = 0; part < groups.length; part += 1) {
    const paths = new Set(groups[part]);
    const nodes = fragment.nodes.filter((node) => paths.has(node.filePath));
    const ids = new Set(nodes.map((node) => node.id));
    const edges = fragment.edges.filter((edge) => ids.has(edge.source));
    const name =
      partCount === 1
        ? `batch-${batchIndex}.json`
        : `batch-${batchIndex}-part-${part + 1}.json`;
    fs.writeFileSync(
      path.join(outDir, name),
      `${JSON.stringify({ nodes, edges }, null, 2)}\n`,
      "utf8",
    );
    written.push({ name, nodes: nodes.length, edges: edges.length });
  }
  return written;
}

function validateBatch(batchIndex, fragment, written) {
  const parsed = written.map(({ name }) => ({
    name,
    data: JSON.parse(
      fs.readFileSync(path.join(ua, "intermediate", name), "utf8"),
    ),
  }));
  const allNodes = parsed.flatMap(({ data }) => data.nodes);
  const allEdges = parsed.flatMap(({ data }) => data.edges);
  const allIds = new Set(allNodes.map((node) => node.id));
  if (allIds.size !== allNodes.length) throw new Error(`批次 ${batchIndex} 存在重复节点 ID`);
  if (allNodes.filter((node) => node.type === "file").length !== fragment.batch.files.length) {
    throw new Error(`批次 ${batchIndex} 文件节点数量不匹配`);
  }
  for (const node of allNodes) {
    for (const field of ["id", "type", "name", "summary", "tags", "complexity"]) {
      if (node[field] === undefined || node[field] === "" || node[field] === null) {
        throw new Error(`批次 ${batchIndex} 节点 ${node.id} 缺少 ${field}`);
      }
    }
    if (!Array.isArray(node.tags) || node.tags.length < 3) {
      throw new Error(`批次 ${batchIndex} 节点 ${node.id} 的标签无效`);
    }
  }
  for (const { name, data } of parsed) {
    if (data.nodes.length > 60 || data.edges.length > 120) {
      throw new Error(`${name} 超出单分片大小限制`);
    }
    const localIds = new Set(data.nodes.map((node) => node.id));
    for (const edge of data.edges) {
      if (!localIds.has(edge.source)) throw new Error(`${name} 的边源不存在: ${edge.source}`);
      if (!allIds.has(edge.target) && edge.type !== "imports") {
        throw new Error(`${name} 的非导入边目标不存在: ${edge.target}`);
      }
      if (
        edge.type === "imports" &&
        !(fragment.batch.batchImportData[edge.source.slice(5)] ?? []).some(
          (target) => `file:${target}` === edge.target,
        )
      ) {
        throw new Error(`${name} 的导入边不在 batchImportData 中: ${edge.source} -> ${edge.target}`);
      }
    }
  }
  for (const file of fragment.batch.files) {
    const actual = allEdges.filter(
      (edge) => edge.type === "imports" && edge.source === `file:${file.path}`,
    ).length;
    const expected = (fragment.batch.batchImportData[file.path] ?? []).length;
    if (actual !== expected) {
      throw new Error(`批次 ${batchIndex} 的 ${file.path} 导入边 ${actual}/${expected}`);
    }
  }
  return { valid: true, parts: parsed.length };
}

const report = [];
for (const batchIndex of [1, 2, 3, 4]) {
  const fragment = makeFragment(batchIndex);
  const written = writeParts(batchIndex, fragment);
  report.push({
    batchIndex,
    nodes: fragment.nodes.length,
    edges: fragment.edges.length,
    imports: fragment.edges.filter((edge) => edge.type === "imports").length,
    expectedImports: Object.values(fragment.batch.batchImportData)
      .flat()
      .length,
    files: fragment.batch.files.length,
    written,
    validation: validateBatch(batchIndex, fragment, written),
  });
}
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
