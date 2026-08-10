const fs = require("fs");

try {
  const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const nodes = input.nodes || [];
  const edges = input.edges || [];
  const layers = input.layers || [];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const fanIn = new Map(nodes.map((node) => [node.id, 0]));
  const fanOut = new Map(nodes.map((node) => [node.id, 0]));
  for (const edge of edges) {
    if (fanOut.has(edge.source)) fanOut.set(edge.source, fanOut.get(edge.source) + 1);
    if (fanIn.has(edge.target)) fanIn.set(edge.target, fanIn.get(edge.target) + 1);
  }
  const rank = (map, key) => [...map].map(([id, value]) => ({
    id, [key]: value, name: byId.get(id)?.name || id
  })).sort((a, b) => b[key] - a[key] || a.id.localeCompare(b.id)).slice(0, 20);
  const fanInRanking = rank(fanIn, "fanIn");
  const fanOutRanking = rank(fanOut, "fanOut");
  const topOut = new Set(fanOutRanking.slice(0, Math.max(1, Math.ceil(nodes.length * 0.1))).map((x) => x.id));
  const inValues = [...fanIn.values()].sort((a, b) => a - b);
  const lowInCutoff = inValues[Math.floor(inValues.length * 0.25)] || 0;
  const entryNames = new Set(["index.ts","index.js","main.ts","main.js","app.ts","app.js","server.ts","server.js","mod.rs","main.go","main.py","main.rs","manage.py","app.py","wsgi.py","asgi.py","run.py","__main__.py","Application.java","Main.java","Program.cs","config.ru","index.php","App.swift","Application.kt","main.cpp","main.c"]);
  const entryPointCandidates = nodes.map((node) => {
    let score = 0;
    const path = node.filePath || "";
    if (node.type === "file") {
      if (entryNames.has(node.name)) score += 3;
      if (path.split("/").length <= 2) score += 1;
      if (topOut.has(node.id)) score += 1;
      if ((fanIn.get(node.id) || 0) <= lowInCutoff) score += 1;
    } else if (node.type === "document" && path === "README.md") score += 5;
    else if (node.type === "document" && path.endsWith(".md") && !path.includes("/")) score += 2;
    return {id: node.id, score, name: node.name, summary: node.summary || ""};
  }).filter((x) => x.score > 0).sort((a, b) => b.score - a.score || a.id.localeCompare(b.id)).slice(0, 5);
  const codeStart = entryPointCandidates.find((x) => byId.get(x.id)?.type === "file")?.id;
  const allowed = new Set(["imports", "calls"]);
  const adjacency = new Map(nodes.map((node) => [node.id, []]));
  for (const edge of edges) if (allowed.has(edge.type) && adjacency.has(edge.source) && byId.has(edge.target)) adjacency.get(edge.source).push(edge.target);
  const order = [], depthMap = {}, byDepth = {};
  if (codeStart) {
    const queue = [codeStart];
    depthMap[codeStart] = 0;
    while (queue.length) {
      const id = queue.shift();
      order.push(id);
      const depth = depthMap[id];
      (byDepth[depth] ||= []).push(id);
      for (const next of adjacency.get(id) || []) if (!(next in depthMap)) {
        depthMap[next] = depth + 1;
        queue.push(next);
      }
    }
  }
  const pick = (types) => nodes.filter((node) => types.includes(node.type)).map((node) => ({
    id: node.id, name: node.name, type: node.type, summary: node.summary || ""
  }));
  const pairTypes = new Set(["imports", "calls"]);
  const edgeSet = new Set(edges.filter((e) => pairTypes.has(e.type)).map((e) => `${e.source}\0${e.target}`));
  const clusters = [];
  const seen = new Set();
  for (const edge of edges.filter((e) => pairTypes.has(e.type))) {
    if (!edgeSet.has(`${edge.target}\0${edge.source}`)) continue;
    const key = [edge.source, edge.target].sort().join("\0");
    if (!seen.has(key)) {
      seen.add(key);
      clusters.push({nodes: [edge.source, edge.target], edgeCount: 2});
    }
  }
  const nodeSummaryIndex = Object.fromEntries(nodes.map((node) => [node.id, {
    name: node.name, type: node.type, summary: node.summary || ""
  }]));
  const result = {
    scriptCompleted: true,
    entryPointCandidates,
    fanInRanking,
    fanOutRanking,
    bfsTraversal: {startNode: codeStart || null, order, depthMap, byDepth},
    nonCodeFiles: {
      documentation: pick(["document"]),
      infrastructure: pick(["service", "pipeline", "resource"]),
      data: pick(["table", "schema", "endpoint"]),
      config: pick(["config"])
    },
    clusters: clusters.slice(0, 10),
    layers: {count: layers.length, list: layers.map(({id, name, description}) => ({id, name, description}))},
    nodeSummaryIndex,
    totalNodes: nodes.length,
    totalEdges: edges.length
  };
  fs.writeFileSync(process.argv[3], JSON.stringify(result, null, 2));
} catch (error) {
  console.error(error.stack || error.message);
  process.exit(1);
}
