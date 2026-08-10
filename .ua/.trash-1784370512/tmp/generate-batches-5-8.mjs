import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const uaDir = path.join(root, ".ua");
const batches = JSON.parse(
  fs.readFileSync(path.join(uaDir, "intermediate", "batches.json"), "utf8"),
).batches;

const fileSummaries = {
  "app/lang/embeddings.py": "集中创建并缓存文本向量模型，为向量库写入和语义检索提供统一的 embedding 实例。",
  "app/lang/graph/ingest_graph.py": "定义文章入库的 LangGraph 工作流，将原文切块并写入向量库，同时维护摄取状态和错误信息。",
  "app/lang/graph/query_graph.py": "定义 RAG 查询图，完成候选文档检索、参考资料格式化和统一查询结果组装。",
  "app/lang/graph/state.py": "声明文章摄取与查询流程使用的类型化状态，约束图节点之间传递的数据字段。",
  "app/lang/rag/chunking.py": "把头条文章转换为带来源元数据的文档分块，并按配置创建递归文本切分器。",
  "app/lang/rag/ingest.py": "封装向量库的文档写入与文章分块删除操作，为重新索引和清理内容资产提供底层能力。",
  "app/lang/rag/retriever.py": "执行头条参考资料的向量检索，并把命中文档整理为适合注入提示词的文本。",
  "app/lang/toutiao_fetcher.py": "从头条链接提取文章标识，抓取页面并解析渲染数据或 HTML，输出标准化文章内容。",
  "app/lang/vectorstore.py": "按项目配置创建并缓存 Chroma 向量库，连接 embedding 模型与持久化目录。",
  "app/models/toutiao_reference.py": "定义头条参考文章的数据库模型，保存来源、正文、互动数据及向量索引状态。",
  "app/services/content_asset_service.py": "编排参考文章导入、重建索引、删除和风格卡生成，连接抓取、数据库、RAG 与写作模式服务。",
  "app/services/writing_pattern_service.py": "从多篇文章中去标识化内容、抽取结构模式并合并为可复用写作风格，同时检测文本复用风险。",
  "app/skills/style_skills.py": "提供搜索热门文章、抽取写作模式、读取和保存风格卡的 Agent 技能实现。",
  "scripts/build_style_cards.py": "命令行批量按关键词检索素材、提炼写作模式并生成风格卡。",
  "scripts/import_toutiao_article.py": "命令行导入单篇头条文章，持久化引用记录并触发向量与图式索引。",
  "scripts/query_toutiao_rag.py": "提供轻量命令行入口，用于对头条文章知识库执行 RAG 查询。",
  "tests/test_writing_pattern.py": "覆盖去标识化、结构摘要、重复检测、热门文章排序、风格抽取和大纲生成的测试。",
  "app/lang/graph/copy_pipeline_graph.py": "构建文案生产 LangGraph，将需求分析、写作、审阅、质量收口及失败处理连接为可路由流程。",
  "app/orchestration/__init__.py": "作为编排子系统的公共入口，集中导出引擎协议、工厂和具体引擎实现。",
  "app/orchestration/base.py": "定义编排引擎抽象接口和运行契约，统一启动、恢复、查询状态与直接运行能力。",
  "app/orchestration/factory.py": "维护编排引擎注册表，并依据配置或显式名称创建 Native 或 LangGraph 引擎。",
  "app/orchestration/langgraph_engine.py": "以 LangGraph 文案流程实现统一编排引擎接口，将任务执行委托给图运行器。",
  "app/orchestration/native_engine.py": "以原生 Agent 流程实现统一编排引擎接口，作为不依赖 LangGraph 的执行后端。",
  "tests/test_orchestration.py": "验证引擎工厂、状态初始化、成功与失败流程，以及 Native 和 LangGraph 引擎的委托行为。",
  "docker-compose.yml": "编排后端、前端、MySQL 与相关持久化资源，提供本地或服务器的一体化容器运行环境。",
  "Dockerfile": "使用 builder 与 runtime 两阶段构建 Python 应用镜像，分离依赖安装和最终运行环境。",
  ".env.example": "列出应用、编排、数据库、认证、模型、向量库、热点同步和日志所需的环境变量模板。",
  "README.md": "项目总览文档，介绍多智能体文案系统架构、MVP 能力、技术栈、部署步骤、目录结构与 API。",
  "deploy.sh": "自动检查环境、生成配置并通过 Docker Compose 完成项目部署、状态检查和运维提示。",
  "package.json": "定义仓库级辅助 npm 脚本，用于统一调用后端、前端或部署相关命令。",
  "requirements.txt": "锁定后端运行所需的 Web、数据库、LLM、LangGraph、向量检索和测试依赖。",
};

const functionPurpose = {
  get_embeddings: "按配置创建并复用 embedding 客户端。",
  _chunk_node: "把摄取状态中的文章内容转换为文档分块。",
  _index_node: "将文档分块写入向量库并记录索引结果。",
  build_ingest_graph: "组装文章摄取状态图及节点连接。",
  run_ingest: "初始化摄取状态、执行图并返回最终结果。",
  _retrieve_node: "根据查询文本检索相关参考文档。",
  _format_node: "把检索文档整理为结构化引用与提示词文本。",
  build_query_graph: "组装检索与格式化组成的查询状态图。",
  run_rag_query: "执行完整 RAG 查询并返回参考资料。",
  build_text_splitter: "按配置创建文本分块器。",
  article_to_documents: "将文章正文切分为携带来源元数据的文档。",
  delete_article_chunks: "删除指定文章已有的向量分块。",
  ingest_documents: "批量写入文档并记录索引过程。",
  retrieve_toutiao_references: "从向量库检索最相关的头条参考内容。",
  format_references_for_prompt: "将检索结果格式化为可供模型使用的引用上下文。",
  extract_article_id: "从头条 URL 中解析文章标识。",
  _strip_html: "移除 HTML 标记并规整文本。",
  _find_title_content: "从页面结构中定位文章标题和正文。",
  _parse_render_data: "解析页面内嵌的渲染数据。",
  fetch_toutiao_article: "抓取并标准化一篇头条文章及其元数据。",
  get_toutiao_vectorstore: "创建并缓存头条文章专用的 Chroma 向量库。",
  reference_to_dict: "将参考文章模型序列化为字典。",
  style_card_to_dict: "将风格卡模型序列化为字典。",
  import_reference: "导入参考文章并同步数据库与索引。",
  reindex_reference: "为已有参考文章重建向量索引。",
  delete_reference: "删除参考文章资产。",
  build_style_card: "从选定素材提炼并保存风格卡。",
  deidentify_text: "遮蔽文本中的身份和来源特征。",
  build_structure_summary: "按段落归纳文章结构与功能。",
  _guess_paragraph_function: "启发式判断段落在文章中的作用。",
  _extract_json_from_response: "从模型响应中提取并解析 JSON。",
  has_ngram_overlap: "检测文本之间是否存在明显 n-gram 重合。",
  extract_writing_pattern_from_articles: "调用模型从多篇素材提取结构化写作模式。",
  merge_writing_patterns: "合并多份写作模式为统一结果。",
  _article_to_dict: "把文章模型转换为技能可消费的数据结构。",
  build_for_keyword: "围绕关键词批量构建风格卡。",
  main: "解析命令行参数并执行脚本主流程。",
  setup_database: "为测试创建并初始化隔离数据库。",
  db: "向测试提供数据库会话夹具。",
  _get_agents: "取得当前图运行所需的 Agent 集合。",
  _requirement_node: "执行需求分析阶段。",
  _copywriter_node: "执行文案生成阶段。",
  _reviewer_node: "执行审阅阶段。",
  _finalize_node: "完成质量收口并生成最终结果。",
  _mark_failed_node: "将异常流程标记为失败。",
  _route_after_copywriter: "依据写作阶段结果选择后续图分支。",
  build_copy_pipeline_graph: "组装文案生产状态图与条件路由。",
  run_copy_pipeline: "初始化状态并执行完整文案图。",
  register_engine: "向编排引擎注册表登记实现。",
  get_orchestration_engine: "依据配置解析并实例化编排引擎。",
  _create_task: "创建测试所需的任务记录。",
  _mock_stage_returns: "构造各流水线阶段的模拟返回值。",
};

const classPurpose = {
  IngestState: "描述文章摄取图在切块、索引和错误处理之间传递的状态。",
  QueryState: "描述 RAG 查询图在检索、格式化和错误处理之间传递的状态。",
  ToutiaoReference: "表示持久化的头条参考文章及其索引元数据。",
  SearchHotArticlesByTopicSkill: "按主题搜索并排序热门参考文章的 Agent 技能。",
  ExtractWritingPatternSkill: "从选定文章中抽取结构化写作模式的 Agent 技能。",
  GetStyleCardSkill: "读取已保存风格卡的 Agent 技能。",
  SaveStyleCardSkill: "持久化风格卡及其来源关系的 Agent 技能。",
  OrchestrationEngine: "规定所有编排后端必须实现的统一抽象协议。",
  LangGraphOrchestrationEngine: "通过 LangGraph 图执行任务的编排引擎适配器。",
  NativeOrchestrationEngine: "通过原生 Agent 流程执行任务的编排引擎适配器。",
};

function fileType(file) {
  if (file.fileCategory === "config") return "config";
  if (file.fileCategory === "docs") return "document";
  if (file.fileCategory === "infra") return "service";
  return "file";
}

function fileId(file) {
  return `${fileType(file)}:${file.path}`;
}

function complexity(nonEmptyLines = 0) {
  if (nonEmptyLines > 200) return "complex";
  if (nonEmptyLines >= 50) return "moderate";
  return "simple";
}

function fileTags(file) {
  const p = file.path.toLowerCase();
  if (p.startsWith("tests/")) return ["test", "pytest", "regression"];
  if (p === "dockerfile") return ["containerization", "infrastructure", "deployment"];
  if (p === "docker-compose.yml") return ["orchestration", "infrastructure", "containerization"];
  if (p === "readme.md") return ["documentation", "entry-point", "architecture"];
  if (p === "requirements.txt") return ["documentation", "dependencies", "python"];
  if (p === ".env.example") return ["configuration", "environment", "security"];
  if (p === "package.json") return ["configuration", "build-system", "scripts"];
  if (p.endsWith(".sh")) return ["deployment", "automation", "shell"];
  if (p.startsWith("scripts/")) return ["entry-point", "automation", "cli"];
  if (p.includes("/models/")) return ["data-model", "database", "sqlalchemy"];
  if (p.includes("/skills/")) return ["agent-skill", "service", "tool"];
  if (p.includes("/orchestration/")) return ["orchestration", "factory", "service"];
  if (p.includes("/graph/")) return ["langgraph", "workflow", "state-machine"];
  if (p.includes("/rag/") || p.includes("vectorstore") || p.includes("embeddings")) {
    return ["rag", "vector-search", "service"];
  }
  return ["service", "business-logic", "python"];
}

function symbolSummary(kind, name) {
  if (kind === "class") {
    return classPurpose[name] ?? `封装 ${name} 对应的领域行为与状态。`;
  }
  if (name.startsWith("test_")) {
    return `验证 ${name.slice(5).replaceAll("_", " ")} 场景的行为与回归约束。`;
  }
  return functionPurpose[name] ?? `实现 ${name.replaceAll("_", " ")} 对应的处理步骤。`;
}

function symbolTags(kind, name, filePath) {
  if (filePath.startsWith("tests/")) return ["test", "pytest", "regression"];
  if (kind === "class") {
    if (name.endsWith("Skill")) return ["agent-skill", "service", "tool"];
    if (name.endsWith("Engine")) return ["orchestration", "adapter", "service"];
    if (name.endsWith("State")) return ["state", "type-definition", "workflow"];
    return ["data-model", "domain", "class"];
  }
  if (name === "main") return ["entry-point", "cli", "automation"];
  if (name.startsWith("build_")) return ["factory", "workflow", "builder"];
  if (name.startsWith("_")) return ["internal", "workflow", "helper"];
  return ["service", "business-logic", "function"];
}

function nodeForFile(file, result) {
  return {
    id: fileId(file),
    type: fileType(file),
    name: path.basename(file.path),
    filePath: file.path,
    summary: fileSummaries[file.path],
    tags: fileTags(file),
    complexity: complexity(result.nonEmptyLines),
  };
}

function addCodeSymbols(nodes, edges, file, result) {
  const exports = new Set((result.exports ?? []).map((item) => item.name));
  for (const fn of result.functions ?? []) {
    if (!fn.name) continue;
    const lines = fn.endLine - fn.startLine + 1;
    if (lines < 10 && !exports.has(fn.name)) continue;
    const id = `function:${file.path}:${fn.name}`;
    nodes.push({
      id,
      type: "function",
      name: fn.name,
      filePath: file.path,
      lineRange: [fn.startLine, fn.endLine],
      summary: symbolSummary("function", fn.name),
      tags: symbolTags("function", fn.name, file.path),
      complexity: complexity(lines),
    });
    edges.push({ source: fileId(file), target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(fn.name)) {
      edges.push({ source: fileId(file), target: id, type: "exports", direction: "forward", weight: 0.8 });
    }
  }
  for (const cls of result.classes ?? []) {
    if (!cls.name) continue;
    const lines = cls.endLine - cls.startLine + 1;
    if ((cls.methods ?? []).length < 2 && lines < 20 && !exports.has(cls.name)) continue;
    const id = `class:${file.path}:${cls.name}`;
    nodes.push({
      id,
      type: "class",
      name: cls.name,
      filePath: file.path,
      lineRange: [cls.startLine, cls.endLine],
      summary: symbolSummary("class", cls.name),
      tags: symbolTags("class", cls.name, file.path),
      complexity: complexity(lines),
    });
    edges.push({ source: fileId(file), target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(cls.name)) {
      edges.push({ source: fileId(file), target: id, type: "exports", direction: "forward", weight: 0.8 });
    }
  }
}

function splitAndWrite(batchIndex, files, nodes, edges) {
  const parts = Math.ceil(Math.max(nodes.length / 60, edges.length / 120, 1));
  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path));
  const chunkSize = Math.ceil(sorted.length / parts);
  for (let k = 0; k < parts; k += 1) {
    const paths = new Set(sorted.slice(k * chunkSize, (k + 1) * chunkSize).map((f) => f.path));
    const partNodes = nodes.filter((n) => paths.has(n.filePath));
    const ids = new Set(partNodes.map((n) => n.id));
    const partEdges = edges.filter((e) => ids.has(e.source));
    const suffix = parts === 1 ? "" : `-part-${k + 1}`;
    fs.writeFileSync(
      path.join(uaDir, "intermediate", `batch-${batchIndex}${suffix}.json`),
      `${JSON.stringify({ nodes: partNodes, edges: partEdges }, null, 2)}\n`,
      "utf8",
    );
  }
  return parts;
}

const report = [];
for (const batchIndex of [5, 6, 7, 8]) {
  const batch = batches.find((item) => item.batchIndex === batchIndex);
  const extraction = JSON.parse(
    fs.readFileSync(path.join(uaDir, "tmp", `ua-file-extract-results-${batchIndex}.json`), "utf8"),
  );
  const byPath = new Map(extraction.results.map((item) => [item.path, item]));
  const nodes = [];
  const edges = [];

  for (const file of batch.files) {
    const result = byPath.get(file.path);
    if (!result) throw new Error(`批次 ${batchIndex} 缺少结构结果: ${file.path}`);
    nodes.push(nodeForFile(file, result));
    if (file.fileCategory === "code" || file.fileCategory === "script") {
      addCodeSymbols(nodes, edges, file, result);
    }
    for (const target of batch.batchImportData[file.path] ?? []) {
      edges.push({
        source: fileId(file),
        target: `file:${target}`,
        type: "imports",
        direction: "forward",
        weight: 0.7,
      });
    }
    if (file.path === "Dockerfile") {
      for (const service of result.services ?? []) {
        const id = `service:${file.path}:${service.name}`;
        nodes.push({
          id,
          type: "service",
          name: service.name,
          filePath: file.path,
          summary: service.name === "builder"
            ? "安装并编译 Python 依赖，为最终镜像准备可复制的运行环境。"
            : "承载精简后的应用运行环境并启动后端服务。",
          tags: ["containerization", "build-stage", "deployment"],
          complexity: "simple",
        });
        edges.push({ source: fileId(file), target: id, type: "contains", direction: "forward", weight: 1.0 });
      }
    }
    if (file.path === "docker-compose.yml") {
      edges.push({ source: fileId(file), target: "service:Dockerfile", type: "depends_on", direction: "forward", weight: 0.6 });
    }
    if (file.path === "package.json") {
      edges.push({ source: fileId(file), target: "file:deploy.sh", type: "configures", direction: "forward", weight: 0.6 });
    }
  }

  const expectedImports = Object.values(batch.batchImportData)
    .reduce((sum, targets) => sum + targets.length, 0);
  const actualImports = edges.filter((edge) => edge.type === "imports").length;
  if (actualImports !== expectedImports) {
    throw new Error(`批次 ${batchIndex} 导入边不匹配: ${actualImports}/${expectedImports}`);
  }
  const parts = splitAndWrite(batchIndex, batch.files, nodes, edges);
  report.push({ batchIndex, parts, nodes: nodes.length, edges: edges.length, imports: actualImports });
}

console.log(JSON.stringify(report));
