const fs = require("node:fs");
const path = require("node:path");

function fail(error) {
  process.stderr.write(`${error.stack || error}\n`);
  process.exit(1);
}

function segments(filePath) {
  return filePath.replaceAll("\\", "/").split("/").filter(Boolean);
}

function commonDirectoryPrefix(fileNodes) {
  const all = fileNodes.map((node) => segments(node.filePath));
  if (!all.length) return [];
  const prefix = [];
  for (let index = 0; ; index += 1) {
    const value = all[0][index];
    if (!value || all.some((parts) => parts[index] !== value)) break;
    if (all.some((parts) => index === parts.length - 1)) break;
    prefix.push(value);
  }
  return prefix;
}

function groupFor(node, prefix) {
  const rest = segments(node.filePath).slice(prefix.length);
  if (rest.length <= 1) return "root";
  return rest[0];
}

function patternFor(group) {
  const patterns = new Map([
    ["api", "api"], ["routes", "api"], ["controllers", "api"], ["endpoints", "api"],
    ["handlers", "api"], ["routers", "api"], ["serializers", "api"],
    ["services", "service"], ["core", "service"], ["lib", "service"], ["domain", "service"],
    ["logic", "service"], ["internal", "service"], ["signals", "service"], ["jobs", "service"],
    ["models", "data"], ["db", "data"], ["data", "data"], ["persistence", "data"],
    ["repository", "data"], ["entities", "data"], ["migrations", "data"], ["sql", "data"],
    ["database", "data"], ["schema", "data"],
    ["components", "ui"], ["views", "ui"], ["pages", "ui"], ["ui", "ui"],
    ["layouts", "ui"], ["screens", "ui"],
    ["middleware", "middleware"], ["plugins", "middleware"], ["interceptors", "middleware"],
    ["guards", "middleware"],
    ["utils", "utility"], ["helpers", "utility"], ["common", "utility"], ["shared", "utility"],
    ["tools", "utility"], ["pkg", "utility"], ["templatetags", "utility"],
    ["config", "config"], ["constants", "config"], ["env", "config"], ["settings", "config"],
    ["management", "config"], ["commands", "config"],
    ["tests", "test"], ["test", "test"], ["__tests__", "test"], ["spec", "test"],
    ["specs", "test"],
    ["types", "types"], ["interfaces", "types"], ["schemas", "types"], ["contracts", "types"],
    ["dtos", "types"], ["dto", "types"], ["request", "types"], ["response", "types"],
    ["hooks", "hooks"], ["composables", "service"],
    ["store", "state"], ["state", "state"], ["reducers", "state"], ["actions", "state"],
    ["slices", "state"],
    ["assets", "assets"], ["static", "assets"], ["public", "assets"],
    ["docs", "documentation"], ["documentation", "documentation"], ["wiki", "documentation"],
    ["deploy", "infrastructure"], ["deployment", "infrastructure"], ["infra", "infrastructure"],
    ["infrastructure", "infrastructure"], ["k8s", "infrastructure"], ["kubernetes", "infrastructure"],
    ["helm", "infrastructure"], ["charts", "infrastructure"], ["terraform", "infrastructure"],
    ["tf", "infrastructure"], ["docker", "infrastructure"],
    [".github", "ci-cd"], [".gitlab", "ci-cd"], [".circleci", "ci-cd"],
    ["cmd", "entry"], ["bin", "entry"],
  ]);
  return patterns.get(group.toLowerCase()) || "unclassified";
}

function filePattern(node) {
  const p = node.filePath.replaceAll("\\", "/");
  const base = path.posix.basename(p);
  if (
    /(^|\/)(test_.*\.py|.*\.(test|spec)\.[^.]+|.*_test\.go|.*Test\.java|.*_spec\.rb|.*Test\.php|.*Tests\.cs)$/.test(p)
  ) return "test";
  if (/\.d\.ts$/.test(base)) return "types";
  if (["index.ts", "index.js", "__init__.py"].includes(base)) return "entry";
  if (base === "manage.py" && !p.includes("/")) return "entry";
  if (["wsgi.py", "asgi.py"].includes(base)) return "config";
  if (["Cargo.toml", "go.mod", "Gemfile", "pom.xml", "build.gradle", "composer.json"].includes(base)) return "config";
  if (/^Dockerfile(?:\..+)?$/.test(base) || /^docker-compose.*\.ya?ml$/.test(base)) return "infrastructure";
  if (/\.tf(vars)?$/.test(base)) return "infrastructure";
  if (p.startsWith(".github/workflows/") || base === ".gitlab-ci.yml" || base === "Jenkinsfile") return "ci-cd";
  if (/\.sql$/.test(base)) return "data";
  if (/\.(graphql|gql|proto)$/.test(base)) return "types";
  if (/\.(md|rst)$/.test(base)) return "documentation";
  if (base === "Makefile") return "infrastructure";
  return null;
}

try {
  const [inputPath, outputPath] = process.argv.slice(2);
  if (!inputPath || !outputPath) throw new Error("usage: node ua-arch-analyze.js input.json output.json");
  const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  const { fileNodes, importEdges, allEdges } = input;
  const nodeById = new Map(fileNodes.map((node) => [node.id, node]));
  const prefix = commonDirectoryPrefix(fileNodes);
  const groupById = new Map(fileNodes.map((node) => [node.id, groupFor(node, prefix)]));

  const directoryGroups = {};
  const nodeTypeGroups = {};
  const filePatternMatches = {};
  for (const node of fileNodes) {
    const group = groupById.get(node.id);
    (directoryGroups[group] ||= []).push(node.id);
    (nodeTypeGroups[node.type] ||= []).push(node.id);
    const matched = filePattern(node);
    if (matched) filePatternMatches[node.id] = matched;
  }
  const patternMatches = Object.fromEntries(
    Object.keys(directoryGroups).map((group) => [group, patternFor(group)]),
  );

  const fileFanIn = Object.fromEntries(fileNodes.map((node) => [node.id, 0]));
  const fileFanOut = Object.fromEntries(fileNodes.map((node) => [node.id, 0]));
  const adjacency = Object.fromEntries(fileNodes.map((node) => [node.id, []]));
  const interMap = new Map();
  for (const edge of importEdges) {
    if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) continue;
    fileFanOut[edge.source] += 1;
    fileFanIn[edge.target] += 1;
    adjacency[edge.source].push(edge.target);
    const from = groupById.get(edge.source);
    const to = groupById.get(edge.target);
    const key = `${from}\u0000${to}`;
    interMap.set(key, (interMap.get(key) || 0) + 1);
  }
  const interGroupImports = [...interMap.entries()]
    .map(([key, count]) => {
      const [from, to] = key.split("\u0000");
      return { from, to, count };
    })
    .sort((a, b) => b.count - a.count || a.from.localeCompare(b.from));

  const intraGroupDensity = {};
  for (const group of Object.keys(directoryGroups)) {
    let internalEdges = 0;
    let totalEdges = 0;
    for (const edge of importEdges) {
      const from = groupById.get(edge.source);
      const to = groupById.get(edge.target);
      if (from === group || to === group) totalEdges += 1;
      if (from === group && to === group) internalEdges += 1;
    }
    intraGroupDensity[group] = {
      internalEdges,
      totalEdges,
      density: totalEdges ? Number((internalEdges / totalEdges).toFixed(4)) : 0,
    };
  }

  const crossMap = new Map();
  const nonCodeConnections = [];
  for (const edge of allEdges) {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) continue;
    if (source.type !== target.type || edge.type !== "imports") {
      const key = `${source.type}\u0000${target.type}\u0000${edge.type}`;
      crossMap.set(key, (crossMap.get(key) || 0) + 1);
    }
    if (source.type !== "file" || target.type !== "file") {
      nonCodeConnections.push({
        source: edge.source,
        target: edge.target,
        edgeType: edge.type,
      });
    }
  }
  const crossCategoryEdges = [...crossMap.entries()].map(([key, count]) => {
    const [fromType, toType, edgeType] = key.split("\u0000");
    return { fromType, toType, edgeType, count };
  });

  const dependencyDirection = [];
  const groups = Object.keys(directoryGroups);
  for (let a = 0; a < groups.length; a += 1) {
    for (let b = a + 1; b < groups.length; b += 1) {
      const left = interMap.get(`${groups[a]}\u0000${groups[b]}`) || 0;
      const right = interMap.get(`${groups[b]}\u0000${groups[a]}`) || 0;
      if (left > right) dependencyDirection.push({ dependent: groups[a], dependsOn: groups[b], count: left, reverseCount: right });
      if (right > left) dependencyDirection.push({ dependent: groups[b], dependsOn: groups[a], count: right, reverseCount: left });
    }
  }

  const paths = fileNodes.map((node) => node.filePath.replaceAll("\\", "/"));
  const infraFiles = fileNodes
    .filter((node) => ["infrastructure", "ci-cd"].includes(filePattern(node)))
    .map((node) => node.filePath);
  const deploymentTopology = {
    hasDockerfile: paths.some((p) => /^Dockerfile(?:\..+)?$/.test(path.posix.basename(p))),
    hasCompose: paths.some((p) => /^docker-compose.*\.ya?ml$/.test(path.posix.basename(p))),
    hasK8s: paths.some((p) => /(^|\/)(k8s|kubernetes|helm|charts)\//.test(p)),
    hasTerraform: paths.some((p) => /\.tf(vars)?$/.test(p)),
    hasCI: paths.some((p) => p.startsWith(".github/workflows/") || /(^|\/)(\.gitlab-ci\.yml|Jenkinsfile)$/.test(p)),
    infraFiles,
  };
  const dataPipeline = {
    schemaFiles: fileNodes.filter((node) => ["schema", "table", "endpoint"].includes(node.type) || /\.(sql|graphql|gql|proto|prisma)$/.test(node.filePath)).map((node) => node.filePath),
    migrationFiles: paths.filter((p) => /(^|\/)(migrations?|alembic)\//.test(p)),
    dataModelFiles: paths.filter((p) => /(^|\/)(models?|entities|repository|persistence)\//.test(p)),
    apiHandlerFiles: paths.filter((p) => /(^|\/)(api|routes|routers|controllers|endpoints|handlers)\//.test(p)),
  };

  const docGroups = new Set(
    fileNodes
      .filter((node) => node.type === "document" || /\.(md|rst)$/.test(node.filePath))
      .map((node) => groupById.get(node.id)),
  );
  const docCoverage = {
    groupsWithDocs: docGroups.size,
    totalGroups: groups.length,
    coverageRatio: groups.length ? Number((docGroups.size / groups.length).toFixed(4)) : 0,
    undocumentedGroups: groups.filter((group) => !docGroups.has(group)),
  };

  const subdirectoryHints = {};
  for (const node of fileNodes) {
    const parts = segments(node.filePath);
    const key = parts.length >= 2 ? parts.slice(0, 2).join("/") : "root";
    (subdirectoryHints[key] ||= []).push(node.id);
  }

  const output = {
    scriptCompleted: true,
    commonPathPrefix: prefix.join("/"),
    directoryGroups,
    subdirectoryHints,
    nodeTypeGroups,
    adjacency,
    crossCategoryEdges,
    nonCodeConnections,
    interGroupImports,
    intraGroupDensity,
    patternMatches,
    filePatternMatches,
    deploymentTopology,
    dataPipeline,
    docCoverage,
    dependencyDirection,
    fileStats: {
      totalFileNodes: fileNodes.length,
      filesPerGroup: Object.fromEntries(Object.entries(directoryGroups).map(([group, ids]) => [group, ids.length])),
      nodeTypeCounts: Object.fromEntries(Object.entries(nodeTypeGroups).map(([type, ids]) => [type, ids.length])),
    },
    fileFanIn,
    fileFanOut,
  };
  fs.writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
  process.exit(0);
} catch (error) {
  fail(error);
}
