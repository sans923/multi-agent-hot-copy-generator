const fs = require("fs");
const path = require("path");

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) fail("Usage: node ua-arch-analyze.js <input> <output>");

try {
  const graph = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  const fileNodes = (graph.fileNodes || graph.nodes || []).filter(
    (node) => node.filePath && !["function", "class", "method"].includes(node.type)
  );
  const fileIds = new Set(fileNodes.map((node) => node.id));
  const allEdges = (graph.allEdges || graph.edges || []).filter(
    (edge) => fileIds.has(edge.source) && fileIds.has(edge.target)
  );
  const importEdges = (graph.importEdges || allEdges).filter((edge) =>
    ["imports", "depends_on"].includes(edge.type)
  );
  const byId = new Map(fileNodes.map((node) => [node.id, node]));

  function groupOf(node) {
    const parts = node.filePath.replaceAll("\\", "/").split("/");
    if (parts.length === 1) return "root";
    if (parts[0] === "app" && parts.length > 2) return `app/${parts[1]}`;
    if (parts[0] === "frontend" && parts[1] === "src" && parts.length > 3)
      return `frontend/src/${parts[2]}`;
    if (parts[0] === "frontend" && parts[1] === "src") return "frontend/src";
    return parts[0];
  }

  const directoryGroups = {};
  const nodeTypeGroups = {};
  for (const node of fileNodes) {
    const group = groupOf(node);
    (directoryGroups[group] ||= []).push(node.id);
    (nodeTypeGroups[node.type] ||= []).push(node.id);
  }

  const fanIn = Object.fromEntries(fileNodes.map((node) => [node.id, 0]));
  const fanOut = Object.fromEntries(fileNodes.map((node) => [node.id, 0]));
  const pairCounts = new Map();
  const internal = {};
  const involved = {};
  for (const edge of importEdges) {
    fanOut[edge.source]++;
    fanIn[edge.target]++;
    const from = groupOf(byId.get(edge.source));
    const to = groupOf(byId.get(edge.target));
    const key = `${from}\0${to}`;
    pairCounts.set(key, (pairCounts.get(key) || 0) + 1);
    involved[from] = (involved[from] || 0) + 1;
    if (to !== from) involved[to] = (involved[to] || 0) + 1;
    else internal[from] = (internal[from] || 0) + 1;
  }

  const patterns = [
    [/api|routers?|controllers?|endpoints?/, "api"],
    [/services?|agents?|orchestration|skills?|lang/, "service"],
    [/models?|database|sql|migrations?/, "data"],
    [/components?|pages?|views?|styles?/, "ui"],
    [/utils?|helpers?|common|shared/, "utility"],
    [/schemas?|types?/, "types"],
    [/contexts?|store|state/, "state"],
    [/tests?|specs?/, "test"],
    [/docs?|documentation/, "documentation"],
    [/deploy|docker|infra/, "infrastructure"],
  ];
  const patternMatches = {};
  for (const group of Object.keys(directoryGroups)) {
    patternMatches[group] =
      patterns.find(([regex]) => regex.test(group.toLowerCase()))?.[1] || "unclassified";
  }

  const cross = new Map();
  for (const edge of allEdges) {
    const fromType = byId.get(edge.source).type;
    const toType = byId.get(edge.target).type;
    if (fromType === toType) continue;
    const key = `${fromType}\0${toType}\0${edge.type}`;
    cross.set(key, (cross.get(key) || 0) + 1);
  }

  const paths = fileNodes.map((node) => node.filePath.replaceAll("\\", "/"));
  const infraFiles = paths.filter((p) =>
    /(^|\/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|.*\.tf(?:vars)?|Jenkinsfile|deploy\.sh|nginx\.conf|gunicorn\.conf\.py)$|^\.github\/workflows\//i.test(p)
  );
  const schemaFiles = paths.filter((p) => /\.(sql|graphql|gql|proto|prisma)$/i.test(p));
  const migrationFiles = paths.filter((p) => /migrat/i.test(p) && /\.sql$/i.test(p));
  const dataModelFiles = paths.filter((p) => /(^|\/)models?\//i.test(p));
  const apiHandlerFiles = paths.filter((p) => /(^|\/)(api|routes?|controllers?)\//i.test(p));

  const interGroupImports = [...pairCounts.entries()]
    .filter(([key]) => key.split("\0")[0] !== key.split("\0")[1])
    .map(([key, count]) => {
      const [from, to] = key.split("\0");
      return { from, to, count };
    })
    .sort((a, b) => b.count - a.count);
  const dependencyDirection = [];
  const seenPairs = new Set();
  for (const item of interGroupImports) {
    const pair = [item.from, item.to].sort().join("\0");
    if (seenPairs.has(pair)) continue;
    seenPairs.add(pair);
    const reverse = pairCounts.get(`${item.to}\0${item.from}`) || 0;
    dependencyDirection.push(
      item.count >= reverse
        ? { dependent: item.from, dependsOn: item.to }
        : { dependent: item.to, dependsOn: item.from }
    );
  }

  const result = {
    scriptCompleted: true,
    directoryGroups,
    nodeTypeGroups,
    crossCategoryEdges: [...cross.entries()].map(([key, count]) => {
      const [fromType, toType, edgeType] = key.split("\0");
      return { fromType, toType, edgeType, count };
    }),
    interGroupImports,
    intraGroupDensity: Object.fromEntries(
      Object.keys(directoryGroups).map((group) => [
        group,
        {
          internalEdges: internal[group] || 0,
          totalEdges: involved[group] || 0,
          density: involved[group] ? (internal[group] || 0) / involved[group] : 0,
        },
      ])
    ),
    patternMatches,
    deploymentTopology: {
      hasDockerfile: paths.some((p) => /(^|\/)Dockerfile/i.test(p)),
      hasCompose: paths.some((p) => /(^|\/)docker-compose.*\.ya?ml$/i.test(p)),
      hasK8s: paths.some((p) => /(^|\/)(k8s|kubernetes|helm|charts)\//i.test(p)),
      hasTerraform: paths.some((p) => /\.tf(?:vars)?$/i.test(p)),
      hasCI: paths.some((p) => /^\.github\/workflows\/|\.gitlab-ci\.ya?ml$|Jenkinsfile$/i.test(p)),
      infraFiles,
    },
    dataPipeline: { schemaFiles, migrationFiles, dataModelFiles, apiHandlerFiles },
    docCoverage: {
      groupsWithDocs: Object.entries(directoryGroups).filter(([, ids]) =>
        ids.some((id) => /\.(md|rst)$/i.test(byId.get(id).filePath))
      ).length,
      totalGroups: Object.keys(directoryGroups).length,
      coverageRatio:
        Object.entries(directoryGroups).filter(([, ids]) =>
          ids.some((id) => /\.(md|rst)$/i.test(byId.get(id).filePath))
        ).length / Object.keys(directoryGroups).length,
      undocumentedGroups: Object.entries(directoryGroups)
        .filter(([, ids]) => !ids.some((id) => /\.(md|rst)$/i.test(byId.get(id).filePath)))
        .map(([group]) => group),
    },
    dependencyDirection,
    fileStats: {
      totalFileNodes: fileNodes.length,
      filesPerGroup: Object.fromEntries(
        Object.entries(directoryGroups).map(([group, ids]) => [group, ids.length])
      ),
      nodeTypeCounts: Object.fromEntries(
        Object.entries(nodeTypeGroups).map(([type, ids]) => [type, ids.length])
      ),
    },
    fileFanIn: fanIn,
    fileFanOut: fanOut,
  };
  fs.writeFileSync(outputPath, `${JSON.stringify(result, null, 2)}\n`);
} catch (error) {
  fail(error.stack || error.message);
}
