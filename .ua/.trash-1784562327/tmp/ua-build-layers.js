const fs = require("fs");
const results = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const outputPath = process.argv[3];
const groups = results.directoryGroups;
const allIds = Object.values(groups).flat();

const takeGroup = (...names) => names.flatMap((name) => groups[name] || []);
const takeMatching = (group, predicate) => (groups[group] || []).filter(predicate);

const layers = [
  {
    id: "layer:api",
    name: "API 与应用入口层",
    description: "承载 FastAPI 应用装配、版本化 REST API 路由、认证依赖与请求级安全控制。",
    nodeIds: [
      ...takeGroup("app/api", "app/core"),
      "file:app/main.py",
    ],
  },
  {
    id: "layer:service",
    name: "智能体与业务编排层",
    description: "集中实现 LangGraph/LangChain 流程、智能体协作、文案技能、领域服务以及可切换的编排引擎。",
    nodeIds: takeGroup(
      "app/agents",
      "app/lang",
      "app/services",
      "app/skills",
      "app/orchestration"
    ),
  },
  {
    id: "layer:data",
    name: "数据与持久化层",
    description: "管理 SQLAlchemy 会话与 ORM 模型，并通过 MySQL 初始化和迁移脚本维护业务数据结构。",
    nodeIds: [
      ...takeGroup("app/models"),
      "file:app/database.py",
      ...takeMatching("scripts", (id) => id.startsWith("table:")),
    ],
  },
  {
    id: "layer:types",
    name: "数据契约层",
    description: "定义后端 Pydantic 请求响应模型和前端 TypeScript API 类型，统一跨端数据契约。",
    nodeIds: [
      ...takeGroup("app/schemas", "frontend/src/types"),
      "file:frontend/src/vite-env.d.ts",
    ],
  },
  {
    id: "layer:ui",
    name: "React 界面层",
    description: "提供 React 页面、复用组件、路由外壳与全局样式，并由 Vite 浏览器入口完成挂载。",
    nodeIds: [
      "file:frontend/src/App.tsx",
      "file:frontend/src/main.tsx",
      ...takeGroup("frontend/src/components", "frontend/src/pages", "frontend/src/styles"),
      "file:frontend/index.html",
    ],
  },
  {
    id: "layer:frontend-service",
    name: "前端服务与状态层",
    description: "封装浏览器端 API 客户端、鉴权调用和 React Context 状态，为页面提供远程数据与会话能力。",
    nodeIds: takeGroup("frontend/src/api", "frontend/src/contexts"),
  },
  {
    id: "layer:utility",
    name: "共享工具层",
    description: "提供 LLM 客户端、日志记录和模型角色映射等可复用的后端横切能力。",
    nodeIds: takeGroup("app/utils"),
  },
  {
    id: "layer:test-tooling",
    name: "测试与运维工具层",
    description: "覆盖智能体、认证、编排和内容资产行为测试，并包含数据导入、初始化、查询与文档转换工具。",
    nodeIds: [
      ...takeGroup("tests"),
      ...takeMatching("scripts", (id) => !id.startsWith("table:")),
    ],
  },
  {
    id: "layer:infrastructure",
    name: "基础设施与配置层",
    description: "汇集 Docker、Docker Compose、Gunicorn、Nginx、Vite 及环境配置，支撑前后端构建、启动和部署。",
    nodeIds: [
      ...takeMatching("root", (id) => !id.startsWith("document:")),
      ...takeMatching("frontend", (id) =>
        !["document:frontend/README.md", "file:frontend/index.html"].includes(id)
      ),
      "file:app/config.py",
      "file:app/scheduler.py",
      "file:app/__init__.py",
    ],
  },
  {
    id: "layer:documentation",
    name: "文档与模板层",
    description: "保存项目说明、头条 RAG 指南、全栈履历说明以及配套文档模板和依赖清单。",
    nodeIds: [
      ...takeGroup("docs"),
      ...takeMatching("root", (id) => id.startsWith("document:")),
      "document:frontend/README.md",
    ],
  },
];

const assigned = layers.flatMap((layer) => layer.nodeIds);
const duplicates = assigned.filter((id, index) => assigned.indexOf(id) !== index);
const missing = allIds.filter((id) => !assigned.includes(id));
const invented = assigned.filter((id) => !allIds.includes(id));
if (
  layers.length < 3 ||
  layers.length > 10 ||
  duplicates.length ||
  missing.length ||
  invented.length ||
  assigned.length !== results.fileStats.totalFileNodes
) {
  throw new Error(
    JSON.stringify(
      {
        layerCount: layers.length,
        expected: results.fileStats.totalFileNodes,
        assigned: assigned.length,
        duplicates,
        missing,
        invented,
      },
      null,
      2
    )
  );
}

fs.writeFileSync(outputPath, `${JSON.stringify(layers, null, 2)}\n`);
process.stdout.write(
  JSON.stringify(
    {
      total: assigned.length,
      layers: layers.map((layer) => ({ name: layer.name, count: layer.nodeIds.length })),
    },
    null,
    2
  )
);
