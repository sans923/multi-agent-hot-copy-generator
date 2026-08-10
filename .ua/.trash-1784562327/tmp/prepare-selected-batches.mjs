import fs from "node:fs";
import path from "node:path";

const root = "D:/workspace/demo_project/multi-agent-hot-copy-generator";
const selected = new Set([2, 5, 8, 11]);
const manifest = JSON.parse(fs.readFileSync(path.join(root, ".ua/intermediate/batches.json"), "utf8"));
for (const batch of manifest.batches.filter((item) => selected.has(item.batchIndex))) {
  const input = {
    projectRoot: root,
    batchFiles: batch.files,
    batchImportData: batch.batchImportData,
  };
  fs.writeFileSync(
    path.join(root, `.ua/tmp/ua-file-analyzer-input-${batch.batchIndex}.json`),
    `${JSON.stringify(input, null, 2)}\n`,
  );
}
