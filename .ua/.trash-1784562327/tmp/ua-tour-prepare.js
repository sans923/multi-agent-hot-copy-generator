const fs = require("fs");

const graph = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const layers = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
fs.writeFileSync(process.argv[4], JSON.stringify({
  nodes: graph.nodes || [],
  edges: graph.edges || [],
  layers
}, null, 2));
