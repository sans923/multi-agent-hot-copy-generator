const fs = require("node:fs");

const input = JSON.parse(fs.readFileSync(".ua/tmp/ua-arch-input.json", "utf8"));
const structural = JSON.parse(fs.readFileSync(".ua/tmp/ua-arch-results.json", "utf8"));
if (!structural.scriptCompleted) throw new Error("结构分析结果未完成");

const layerDefinitions = [
  {
    id: "layer:frontend",
    name: "前端应用层",
    description: "承载 React 页面、可复用组件、全局上下文、浏览器端 API 客户端和类型定义，形成用户操作多智能体文案系统的完整界面。",
  },
  {
    id: "layer:api",
    name: "API 与契约层",
    description: "提供 FastAPI 路由、鉴权依赖和 Pydantic 数据契约，把前端请求转换为后端业务调用并统一响应。",
  },
  {
    id: "layer:orchestration",
    name: "智能体编排层",
    description: "组织主管与专业智能体、LangGraph 状态图、可插拔技能和多种执行引擎，驱动文案任务的规划、生成、审核与恢复。",
  },
  {
    id: "layer:service",
    name: "领域服务与共享能力层",
    description: "实现热点、内容资产、评审、反思、审计等领域服务，并提供模型客户端、日志和调度等跨模块能力。",
  },
  {
    id: "layer:data",
    name: "数据与持久化层",
    description: "定义 SQLAlchemy 业务模型、数据库会话以及 MySQL 初始化和迁移结构，保存用户、任务、文案、审计与风格数据。",
  },
  {
    id: "layer:infrastructure",
    name: "配置与基础设施层",
    description: "集中管理应用和前端构建配置、容器镜像、Compose 编排、Nginx、Gunicorn、部署脚本及运行入口。",
  },
  {
    id: "layer:documentation",
    name: "文档与模板层",
    description: "汇总项目使用说明、头条 RAG 指南、依赖清单、简历示例和文档生成模板，为使用与交付提供参考。",
  },
  {
    id: "layer:test",
    name: "自动化测试层",
    description: "覆盖认证、API、智能体流水线、编排策略、审计、合规和写作模式等关键行为与回归场景。",
  },
  {
    id: "layer:tooling",
    name: "项目工具与数据运维层",
    description: "提供数据库准备、用户种子、内容导入、RAG 查询、风格卡构建和文档转换等一次性或运维辅助脚本。",
  },
];

function assign(node) {
  const p = node.filePath.replaceAll("\\", "/");
  if (
    p.startsWith("docs/") ||
    p === "README.md" ||
    p === "requirements.txt" ||
    p === "frontend/README.md"
  ) return "layer:documentation";

  if (p.startsWith("tests/")) return "layer:test";

  if (p.startsWith("scripts/")) {
    if (["schema", "table", "endpoint"].includes(node.type) || p.endsWith(".sql")) {
      return "layer:data";
    }
    return "layer:tooling";
  }

  if (p === "quick_view.py") return "layer:tooling";

  if (p.startsWith("frontend/")) {
    if (
      node.type === "config" ||
      p === "frontend/vite.config.ts" ||
      p === "frontend/tsconfig.tsbuildinfo"
    ) return "layer:infrastructure";
    return "layer:frontend";
  }

  if (p.startsWith("app/models/") || p === "app/database.py") return "layer:data";

  if (
    p.startsWith("app/api/") ||
    p.startsWith("app/core/") ||
    p.startsWith("app/schemas/") ||
    p === "app/main.py"
  ) return "layer:api";

  if (
    p.startsWith("app/agents/") ||
    p.startsWith("app/lang/") ||
    p.startsWith("app/orchestration/") ||
    p.startsWith("app/skills/")
  ) return "layer:orchestration";

  if (
    p.startsWith("app/services/") ||
    p.startsWith("app/utils/") ||
    p === "app/scheduler.py" ||
    p === "app/__init__.py"
  ) return "layer:service";

  if (p === "app/config.py" || !p.includes("/")) return "layer:infrastructure";

  throw new Error(`无法分层的节点: ${node.id} (${p})`);
}

const idsInInput = new Set(input.fileNodes.map((node) => node.id));
if (idsInInput.size !== input.fileNodes.length) throw new Error("输入文件级节点 ID 不唯一");

const assignments = new Map(layerDefinitions.map((layer) => [layer.id, []]));
for (const node of input.fileNodes) {
  assignments.get(assign(node)).push(node.id);
}

const layers = layerDefinitions.map((layer) => ({
  ...layer,
  nodeIds: assignments.get(layer.id).sort(),
}));

if (layers.length < 3 || layers.length > 10) throw new Error(`层数无效: ${layers.length}`);
if (layers.some((layer) => layer.nodeIds.length === 0)) throw new Error("存在空层");

const flattened = layers.flatMap((layer) => layer.nodeIds);
const assigned = new Set(flattened);
const duplicates = flattened.filter((id, index) => flattened.indexOf(id) !== index);
const missing = [...idsInInput].filter((id) => !assigned.has(id));
const invented = [...assigned].filter((id) => !idsInInput.has(id));
if (duplicates.length || missing.length || invented.length) {
  throw new Error(
    JSON.stringify(
      { duplicates: [...new Set(duplicates)], missing, invented },
      null,
      2,
    ),
  );
}
if (
  flattened.length !== input.fileNodes.length ||
  flattened.length !== structural.fileStats.totalFileNodes
) {
  throw new Error(
    `覆盖数量不匹配: output=${flattened.length}, input=${input.fileNodes.length}, structural=${structural.fileStats.totalFileNodes}`,
  );
}

fs.writeFileSync(
  ".ua/intermediate/layers.json",
  `${JSON.stringify(layers, null, 2)}\n`,
  "utf8",
);
process.stdout.write(
  `${JSON.stringify(
    {
      valid: true,
      total: flattened.length,
      layers: layers.map((layer) => ({
        id: layer.id,
        name: layer.name,
        count: layer.nodeIds.length,
      })),
    },
    null,
    2,
  )}\n`,
);
