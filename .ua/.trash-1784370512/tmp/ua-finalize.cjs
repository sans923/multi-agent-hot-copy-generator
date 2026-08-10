#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

const projectRoot = process.argv[2];
const gitCommitHash = process.argv[3];
const uaDir = path.join(projectRoot, ".ua");
const intermediate = path.join(uaDir, "intermediate");

const readJson = (name) =>
  JSON.parse(fs.readFileSync(path.join(intermediate, name), "utf8"));

const assembled = readJson("assembled-graph.json");
const scan = readJson("scan-result.json");
let layers = readJson("layers.json");
let tour = readJson("tour.json");

if (!Array.isArray(layers)) layers = layers.layers || [];
if (!Array.isArray(tour)) tour = tour.steps || [];

const nodeIds = new Set(assembled.nodes.map((node) => node.id));
const prefixes = [
  "file:",
  "config:",
  "document:",
  "service:",
  "pipeline:",
  "table:",
  "schema:",
  "resource:",
  "endpoint:",
];
const normalizeId = (value) => {
  const id = typeof value === "string" ? value : value?.id;
  if (!id) return null;
  return prefixes.some((prefix) => id.startsWith(prefix)) ? id : `file:${id}`;
};
const slug = (value) =>
  String(value || "layer")
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-")
    .replace(/^-|-$/g, "");

layers = layers
  .map((layer) => ({
    id: layer.id || `layer:${slug(layer.name)}`,
    name: layer.name || "未命名层",
    description: layer.description || "该层聚合职责相近的项目文件。",
    nodeIds: (layer.nodeIds || layer.nodes || [])
      .map(normalizeId)
      .filter((id) => id && nodeIds.has(id)),
  }))
  .filter((layer) => layer.nodeIds.length > 0);

tour = tour
  .map((step, index) => {
    const normalized = {
      order: Number(step.order) || index + 1,
      title: step.title || `步骤 ${index + 1}`,
      description:
        step.description || step.whyItMatters || "查看这些节点以理解本步骤。",
      nodeIds: (step.nodeIds || step.nodesToInspect || [])
        .map(normalizeId)
        .filter((id) => id && nodeIds.has(id)),
    };
    if (typeof step.languageLesson === "string") {
      normalized.languageLesson = step.languageLesson;
    }
    return normalized;
  })
  .sort((a, b) => a.order - b.order)
  .map((step, index) => ({ ...step, order: index + 1 }));

const graph = {
  version: "1.0.0",
  project: {
    name: scan.name || "multi-agent-hot-copy-generator",
    languages: scan.languages || [],
    frameworks: scan.frameworks || [],
    description:
      "多智能体热点爆款文案生成系统，采用 FastAPI、React、LangGraph、RAG 与 SQLAlchemy，完成热点采集、任务编排、内容生成、审核和资产沉淀。",
    analyzedAt: new Date().toISOString(),
    gitCommitHash,
  },
  nodes: assembled.nodes,
  edges: assembled.edges,
  layers,
  tour,
};

fs.writeFileSync(
  path.join(intermediate, "assembled-graph.json"),
  JSON.stringify(graph, null, 2),
);

fs.writeFileSync(
  path.join(intermediate, "fingerprint-input.json"),
  JSON.stringify(
    {
      projectRoot,
      sourceFilePaths: (scan.files || []).map((file) => file.path),
      gitCommitHash,
    },
    null,
    2,
  ),
);
