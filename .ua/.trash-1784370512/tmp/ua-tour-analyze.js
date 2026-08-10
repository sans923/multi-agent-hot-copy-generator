const fs = require("node:fs");
const path = require("node:path");

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

try {
  const [inputPath, outputPath] = process.argv.slice(2);
  if (!inputPath || !outputPath) fail("usage: node ua-tour-analyze.js <input> <output>");
  const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  const nodes = input.nodes ?? [];
  const edges = input.edges ?? [];
  const layers = input.layers ?? [];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const fanIn = new Map(nodes.map((node) => [node.id, 0]));
  const fanOut = new Map(nodes.map((node) => [node.id, 0]));
  const adjacency = new Map(nodes.map((node) => [node.id, []]));

  for (const edge of edges) {
    if (byId.has(edge.source)) fanOut.set(edge.source, (fanOut.get(edge.source) ?? 0) + 1);
    if (byId.has(edge.target)) fanIn.set(edge.target, (fanIn.get(edge.target) ?? 0) + 1);
    if (
      byId.has(edge.source)
      && byId.has(edge.target)
      && (edge.type === "imports" || edge.type === "calls")
      && edge.direction !== "backward"
    ) {
      adjacency.get(edge.source).push(edge.target);
    }
  }

  const rank = (values, label) => [...values.entries()]
    .map(([id, value]) => ({ id, [label]: value, name: byId.get(id)?.name ?? id }))
    .sort((a, b) => b[label] - a[label] || a.id.localeCompare(b.id))
    .slice(0, 20);
  const fanInRanking = rank(fanIn, "fanIn");
  const fanOutRanking = rank(fanOut, "fanOut");
  const sortedFanOut = [...fanOut.values()].sort((a, b) => b - a);
  const topTenThreshold = sortedFanOut[Math.max(0, Math.ceil(sortedFanOut.length * 0.1) - 1)] ?? 0;
  const sortedFanIn = [...fanIn.values()].sort((a, b) => a - b);
  const bottomQuarterThreshold = sortedFanIn[Math.max(0, Math.ceil(sortedFanIn.length * 0.25) - 1)] ?? 0;
  const entryNames = new Set([
    "index.ts", "index.js", "main.ts", "main.js", "app.ts", "app.js",
    "server.ts", "server.js", "mod.rs", "main.go", "main.py", "main.rs",
    "manage.py", "app.py", "wsgi.py", "asgi.py", "run.py", "__main__.py",
    "Application.java", "Main.java", "Program.cs", "config.ru", "index.php",
    "App.swift", "Application.kt", "main.cpp", "main.c",
  ]);
  const entryPointCandidates = nodes.map((node) => {
    const filePath = node.filePath ?? "";
    const name = node.name ?? path.basename(filePath);
    let score = 0;
    if (node.type === "file") {
      if (entryNames.has(name)) score += 3;
      if (filePath.split("/").length <= 2) score += 1;
      if ((fanOut.get(node.id) ?? 0) >= topTenThreshold) score += 1;
      if ((fanIn.get(node.id) ?? 0) <= bottomQuarterThreshold) score += 1;
    } else if (node.type === "document") {
      if (filePath === "README.md") score += 5;
      else if (/^[^/]+\.md$/i.test(filePath)) score += 2;
    }
    return { id: node.id, score, name, summary: node.summary };
  }).filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
    .slice(0, 5);

  const codeCandidates = entryPointCandidates.filter((item) => byId.get(item.id)?.type === "file");
  const preferredMain = byId.has("file:app/main.py") ? "file:app/main.py" : codeCandidates[0]?.id;
  const depthMap = {};
  const order = [];
  if (preferredMain) {
    const queue = [preferredMain];
    depthMap[preferredMain] = 0;
    while (queue.length) {
      const current = queue.shift();
      order.push(current);
      for (const next of adjacency.get(current) ?? []) {
        if (depthMap[next] !== undefined) continue;
        depthMap[next] = depthMap[current] + 1;
        queue.push(next);
      }
    }
  }
  const byDepth = {};
  for (const id of order) {
    const depth = String(depthMap[id]);
    (byDepth[depth] ??= []).push(id);
  }

  const inventory = (types) => nodes.filter((node) => types.includes(node.type))
    .map((node) => ({ id: node.id, name: node.name, type: node.type, summary: node.summary }));
  const nonCodeFiles = {
    documentation: inventory(["document"]),
    infrastructure: inventory(["service", "pipeline", "resource"]),
    data: inventory(["table", "schema", "endpoint"]),
    config: inventory(["config"]),
  };

  const pairCounts = new Map();
  const directed = new Set();
  for (const edge of edges) {
    if (!byId.has(edge.source) || !byId.has(edge.target)) continue;
    if (edge.type !== "imports" && edge.type !== "calls") continue;
    directed.add(`${edge.source}\0${edge.target}`);
  }
  for (const key of directed) {
    const [source, target] = key.split("\0");
    if (!directed.has(`${target}\0${source}`)) continue;
    const pair = [source, target].sort();
    pairCounts.set(pair.join("\0"), (pairCounts.get(pair.join("\0")) ?? 0) + 1);
  }
  const clusters = [...pairCounts.entries()]
    .map(([key, edgeCount]) => ({ nodes: key.split("\0"), edgeCount }))
    .sort((a, b) => b.edgeCount - a.edgeCount || a.nodes[0].localeCompare(b.nodes[0]))
    .slice(0, 10);

  const nodeSummaryIndex = Object.fromEntries(nodes.map((node) => [
    node.id,
    { name: node.name, type: node.type, summary: node.summary },
  ]));
  const result = {
    scriptCompleted: true,
    entryPointCandidates,
    fanInRanking,
    fanOutRanking,
    bfsTraversal: { startNode: preferredMain ?? null, order, depthMap, byDepth },
    nonCodeFiles,
    clusters,
    layers: {
      count: layers.length,
      list: layers.map(({ id, name, description }) => ({ id, name, description })),
    },
    nodeSummaryIndex,
    totalNodes: nodes.length,
    totalEdges: edges.length,
  };
  fs.writeFileSync(outputPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
} catch (error) {
  fail(error.stack || error.message);
}
