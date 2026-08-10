import fs from "node:fs";
import path from "node:path";

const root = "D:/workspace/demo_project/multi-agent-hot-copy-generator";
const ua = path.join(root, ".ua");
const manifest = JSON.parse(fs.readFileSync(path.join(ua, "intermediate/batches.json"), "utf8"));
const selected = [2, 5, 8, 11];

const complexity = (lines) => lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";
const edge = (source, target, type, weight) => ({ source, target, type, direction: "forward", weight });
const basename = (p) => path.posix.basename(p);
const prefixFor = (file) => {
  if (file.fileCategory === "config") return "config";
  if (file.fileCategory === "docs") return "document";
  if (file.fileCategory === "data") return "table";
  return "file";
};

function fileDescription(p) {
  const exact = {
    "app/api/v1/auth.py": "提供用户注册、密码登录、表单登录、当前用户查询与退出接口，是账户认证的 HTTP 边界。",
    "app/api/v1/content_assets.py": "提供头条参考文章与风格卡的管理接口，将管理员请求转交给内容资产服务。",
    "app/api/v1/hotlist.py": "提供多平台热榜查询、语义搜索、同步触发与统计接口，连接热榜数据、向量检索和后台同步。",
    "app/api/v1/logs.py": "提供任务审计、智能体执行、任务概览和系统日志的分页查询接口，并实施用户与管理员权限隔离。",
    "app/api/v1/tasks.py": "承担文案任务创建、查询、结果读取和人工恢复，并在后台启动或续跑多智能体编排流程。",
    "app/api/v1/users.py": "提供个人资料维护和管理员用户查询接口，统一处理密码更新与权限校验。",
    "app/core/deps.py": "定义 FastAPI 认证依赖，从 JWT 解析当前用户并逐级校验启用状态和管理员权限。",
    "app/core/security.py": "封装密码哈希校验与 JWT 访问令牌的签发、解析，是认证链路的安全基础。",
    "app/database.py": "集中创建 SQLAlchemy 引擎、会话和声明基类，兼容 SQLite 与 MySQL，并提供建表入口。",
    "app/main.py": "创建并配置 FastAPI 应用，注册路由、中间件、异常处理、生命周期任务和健康检查。",
    "app/models/__init__.py": "汇总导入项目的 SQLAlchemy 模型，确保元数据建表时包含全部业务实体。",
    "app/services/hotlist_service.py": "负责从聚合接口抓取和清洗多平台热榜，持久化同步结果并提供近期榜单查询。",
    "app/lang/embeddings.py": "按配置懒加载并缓存多语言文本嵌入模型，为头条 RAG 提供统一向量化能力。",
    "app/lang/graph/ingest_graph.py": "构建头条文章切块与向量入库的 LangGraph 工作流，并提供同步执行入口。",
    "app/lang/graph/query_graph.py": "构建头条参考资料检索与提示词格式化的 LangGraph 查询工作流。",
    "app/lang/graph/state.py": "定义文章入库和 RAG 查询图共享的 TypedDict 状态结构。",
    "app/lang/rag/chunking.py": "把头条长文按配置切分为带来源元数据的 LangChain 文档块。",
    "app/lang/rag/ingest.py": "封装头条文档块的向量入库和按文章删除操作，并记录处理结果。",
    "app/lang/rag/retriever.py": "执行头条参考资料的语义检索，并将命中文档整理成可供文案提示词使用的引用文本。",
    "app/lang/toutiao_fetcher.py": "抓取头条文章页面，解析渲染数据并递归提取标题、正文和文章标识。",
    "app/lang/vectorstore.py": "按配置创建并缓存持久化 Chroma 向量库，绑定项目统一嵌入模型。",
    "app/services/content_asset_service.py": "编排参考文章抓取、入库、重建索引、删除与风格卡提炼，形成可复用内容资产。",
    "scripts/import_toutiao_article.py": "提供命令行入口，将指定头条文章抓取、保存并写入 RAG 向量索引。",
    "scripts/query_toutiao_rag.py": "提供命令行检索入口，输出与查询主题相关的头条参考资料。",
    ".env.example": "列出应用、编排、数据库、鉴权、模型、向量库、热榜和日志所需的环境变量模板。",
    "README.md": "系统总览与上手文档，说明多智能体架构、头条长文模式、内容资产库、部署步骤、目录和 API。",
    "deploy.sh": "面向 Ubuntu ECS 的一键部署脚本，安装依赖、校验机密、配置 Supervisor 与 Nginx，并执行健康检查。",
    "package.json": "定义仓库级便捷脚本，将前端安装、开发和构建命令转发到 frontend 子项目。",
    "requirements.txt": "集中声明后端 Web、数据库、鉴权、LangGraph、RAG、模型调用、调度和生产服务依赖。",
    "scripts/init_mysql.sql": "初始化 copy_generator MySQL 数据库、应用账号及其访问权限。",
    "scripts/migrate_add_toutiao_platform.sql": "扩展 tasks.platform 枚举，使任务可选择今日头条等六个平台。",
    "scripts/migrate_agentic_phase2.sql": "为 tasks 表增加 JSON 编排元数据列，支撑智能体流程状态与人工介入信息。",
    "scripts/migrate_audit_logs.sql": "创建编排审计日志表及任务序列索引，以保存每一步执行、失败和耗时信息。",
    "scripts/migrate_style_pattern.sql": "为头条参考文章补充互动指标，并创建按主题和平台组织的风格卡表。",
  };
  if (exact[p]) return exact[p];
  if (p.includes("/models/")) return `定义 ${basename(p, ".py")} 对应的 SQLAlchemy 持久化模型及其字段关系。`;
  if (p.includes("/schemas/")) return `定义 ${basename(p, ".py")} 相关的 Pydantic 请求与响应结构，约束 API 数据边界。`;
  if (p.includes("/tests/")) return `验证 ${basename(p)} 所覆盖业务链路的正常、异常与权限行为，使用隔离数据库或替身控制外部依赖。`;
  if (p.endsWith("__init__.py")) return "标记 Python 包边界，并汇总该包对外暴露的组件。";
  if (p.startsWith("scripts/")) return `提供 ${basename(p)} 对应的项目维护或初始化命令行流程。`;
  return `实现 ${basename(p)} 所承载的项目功能，并与相邻模块协作完成业务流程。`;
}

function fileTags(file) {
  const p = file.path;
  if (p.includes("/tests/")) return ["测试", "回归验证", "业务流程"];
  if (p.includes("/api/")) return ["api-handler", "接口路由", "权限控制"];
  if (p.includes("/models/")) return ["data-model", "数据库", "持久化"];
  if (p.includes("/schemas/")) return ["validation", "数据契约", "序列化"];
  if (p.includes("/lang/graph/")) return ["langgraph", "工作流", "rag"];
  if (p.includes("/lang/rag/") || p.includes("vectorstore") || p.includes("embeddings")) return ["rag", "向量检索", "内容资产"];
  if (p === "deploy.sh") return ["deployment", "自动化脚本", "运维"];
  if (p === "README.md" || p === "requirements.txt") return ["documentation", "项目说明", "开发指南"];
  if (file.fileCategory === "config") return ["configuration", "运行配置", "项目设置"];
  if (file.fileCategory === "data") return ["database", "migration", "schema-definition"];
  if (p.includes("/core/")) return ["security", "基础设施", "认证"];
  if (p.includes("/services/")) return ["service", "业务逻辑", "编排"];
  return ["entry-point", "应用基础", "模块组织"];
}

function symbolSummary(name, kind, p) {
  const words = name.replace(/^_/, "").split("_").join(" ");
  const special = {
    register: "校验账号唯一性、哈希密码并创建新用户，返回访问令牌。",
    login: "校验邮箱和密码并签发访问令牌，同时记录登录结果。",
    create_task: "持久化用户文案需求和编排参数，并安排后台智能体流水线。",
    resume_task: "校验待人工处理任务的恢复动作，并安排后台续跑。",
    get_current_user: "解码 Bearer Token、查询用户并拒绝无效认证。",
    create_access_token: "按配置生成带过期时间和签发信息的 JWT 访问令牌。",
    decode_access_token: "解析并校验 JWT，失败时返回空结果供认证依赖处理。",
    lifespan: "在应用启动和关闭阶段初始化数据库、调度器及相关资源。",
    log_requests: "记录请求耗时、状态与异常，形成统一 HTTP 访问日志。",
    sync_all_hotlists: "遍历受支持平台抓取热榜并将结果和同步状态写入数据库。",
    fetch_toutiao_article: "请求头条页面并从渲染数据中提取文章标题、正文与元信息。",
    run_ingest: "运行文章切块和向量入库图，返回入库数量或错误状态。",
    run_rag_query: "运行语义检索图，将相关文档与格式化引用汇总返回。",
    import_reference: "抓取并保存参考文章，随后建立向量索引并更新处理状态。",
    build_style_card: "聚合选定参考文章的写作模式并保存主题风格卡。",
    main: `执行 ${basename(p)} 的命令行主流程并输出处理结果。`,
  };
  if (special[name]) return special[name];
  if (kind === "class") return `定义 ${name} 的结构、字段与行为，作为 ${basename(p)} 中可复用的数据类型。`;
  if (name.startsWith("test_")) return `验证“${words.slice(5)}”场景的预期行为与关键断言。`;
  if (name.startsWith("get_") || name.startsWith("list_")) return `查询并整理 ${words} 所需数据，返回符合接口契约的结果。`;
  if (name.startsWith("create_") || name.startsWith("build_")) return `构建 ${words} 对应对象或流程，并返回可供后续使用的结果。`;
  if (name.startsWith("delete_") || name.startsWith("remove_")) return `删除 ${words} 对应资源，并维护相关持久化状态。`;
  if (name.startsWith("sync_") || name.startsWith("reindex_")) return `执行 ${words} 流程并同步更新处理状态。`;
  return `实现 ${words} 对应的核心处理逻辑，是 ${basename(p)} 中的显著可调用单元。`;
}

function buildBatch(batchIndex) {
  const batch = manifest.batches.find((b) => b.batchIndex === batchIndex);
  const extracted = JSON.parse(fs.readFileSync(path.join(ua, `tmp/ua-file-extract-results-${batchIndex}.json`), "utf8"));
  const resultMap = new Map(extracted.results.map((r) => [r.path, r]));
  const nodes = [];
  const edges = [];

  for (const file of batch.files) {
    const result = resultMap.get(file.path);
    const prefix = prefixFor(file);
    const fileId = `${prefix}:${file.path}`;
    const nonEmpty = result?.nonEmptyLines ?? fs.readFileSync(path.join(root, file.path), "utf8").split(/\r?\n/).filter((x) => x.trim()).length;
    nodes.push({
      id: fileId,
      type: prefix,
      name: basename(file.path),
      filePath: file.path,
      summary: fileDescription(file.path),
      tags: fileTags(file),
      complexity: complexity(nonEmpty),
      ...(file.path === "deploy.sh" ? { languageNotes: "脚本启用快速失败，并通过 Supervisor 托管 Gunicorn、Nginx 反向代理和 HTTP 健康检查完成部署闭环。" } : {}),
    });

    if (file.fileCategory === "code" || file.fileCategory === "script") {
      for (const target of batch.batchImportData[file.path] ?? []) edges.push(edge(fileId, `file:${target}`, "imports", 0.7));
      for (const fn of result?.functions ?? []) {
        const exported = (result.exports ?? []).some((x) => x.name === fn.name);
        if (fn.endLine - fn.startLine + 1 < 10 && !exported) continue;
        const id = `function:${file.path}:${fn.name}`;
        nodes.push({ id, type: "function", name: fn.name, filePath: file.path, lineRange: [fn.startLine, fn.endLine], summary: symbolSummary(fn.name, "function", file.path), tags: file.path.includes("/tests/") ? ["test", "行为验证", "回归"] : ["业务逻辑", "可调用单元", fn.name.startsWith("_") ? "内部函数" : "公开函数"], complexity: complexity(fn.endLine - fn.startLine + 1) });
        edges.push(edge(fileId, id, "contains", 1.0));
        if (exported) edges.push(edge(fileId, id, "exports", 0.8));
      }
      for (const cls of result?.classes ?? []) {
        const exported = (result.exports ?? []).some((x) => x.name === cls.name);
        if ((cls.methods?.length ?? 0) < 2 && cls.endLine - cls.startLine + 1 < 20 && !exported) continue;
        const id = `class:${file.path}:${cls.name}`;
        nodes.push({ id, type: "class", name: cls.name, filePath: file.path, lineRange: [cls.startLine, cls.endLine], summary: symbolSummary(cls.name, "class", file.path), tags: file.path.includes("/models/") ? ["data-model", "数据库", "实体"] : ["数据结构", "类型定义", "validation"], complexity: complexity(cls.endLine - cls.startLine + 1) });
        edges.push(edge(fileId, id, "contains", 1.0));
        if (exported) edges.push(edge(fileId, id, "exports", 0.8));
      }
      if (file.path.includes("/tests/")) {
        for (const target of batch.batchImportData[file.path] ?? []) {
          if (!target.includes("/tests/")) edges.push(edge(`file:${target}`, fileId, "tested_by", 0.5));
        }
      }
    }
  }

  if (batchIndex === 8) {
    edges.push(edge("document:README.md", "file:deploy.sh", "documents", 0.5));
    edges.push(edge("document:README.md", "config:.env.example", "documents", 0.5));
    edges.push(edge("document:README.md", "document:requirements.txt", "documents", 0.5));
    edges.push(edge("config:package.json", "document:README.md", "related", 0.5));
  }
  if (batchIndex === 11) {
    const tables = [
      ["scripts/migrate_audit_logs.sql", "orchestration_audit_logs", "保存任务编排各步骤的输入输出摘要、状态、耗时和错误。"],
      ["scripts/migrate_style_pattern.sql", "style_cards", "保存由高互动参考文章提炼的主题写作模式、来源与置信度。"],
    ];
    for (const [p, name, summary] of tables) {
      const id = `table:${p}:${name}`;
      nodes.push({ id, type: "table", name, filePath: p, summary, tags: ["database", "schema-definition", "业务数据"], complexity: "simple" });
      edges.push(edge(`table:${p}`, id, "migrates", 0.7));
    }
  }

  const uniqueEdges = [...new Map(edges.map((e) => [`${e.source}|${e.target}|${e.type}`, e])).values()];
  return { batch, nodes, edges: uniqueEdges };
}

function writeParts(batchIndex, graph) {
  for (const old of fs.readdirSync(path.join(ua, "intermediate")).filter((n) => new RegExp(`^batch-${batchIndex}(?:-part-\\d+)?\\.json$`).test(n))) {
    fs.rmSync(path.join(ua, "intermediate", old));
  }
  let parts = Math.ceil(Math.max(graph.nodes.length / 60, graph.edges.length / 120));
  if (parts <= 1) {
    fs.writeFileSync(path.join(ua, `intermediate/batch-${batchIndex}.json`), `${JSON.stringify({ nodes: graph.nodes, edges: graph.edges }, null, 2)}\n`);
    return;
  }
  const files = [...graph.batch.files].sort((a, b) => a.path.localeCompare(b.path)).map((f) => f.path);
  while (parts < files.length) {
    const trialSize = Math.ceil(files.length / parts);
    let valid = true;
    for (let i = 0; i < parts; i++) {
      const set = new Set(files.slice(i * trialSize, (i + 1) * trialSize));
      const trialNodes = graph.nodes.filter((n) => set.has(n.filePath));
      const ids = new Set(trialNodes.map((n) => n.id));
      const trialEdges = graph.edges.filter((e) => ids.has(e.source));
      if (trialNodes.length > 60 || trialEdges.length > 120) valid = false;
    }
    if (valid) break;
    parts++;
  }
  const groupSize = Math.ceil(files.length / parts);
  for (let i = 0; i < parts; i++) {
    const set = new Set(files.slice(i * groupSize, (i + 1) * groupSize));
    const partNodes = graph.nodes.filter((n) => set.has(n.filePath));
    const ids = new Set(partNodes.map((n) => n.id));
    const partEdges = graph.edges.filter((e) => ids.has(e.source));
    fs.writeFileSync(path.join(ua, `intermediate/batch-${batchIndex}-part-${i + 1}.json`), `${JSON.stringify({ nodes: partNodes, edges: partEdges }, null, 2)}\n`);
  }
}

for (const i of selected) writeParts(i, buildBatch(i));
