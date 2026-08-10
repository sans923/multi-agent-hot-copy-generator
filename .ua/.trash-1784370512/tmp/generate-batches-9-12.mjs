import fs from "node:fs";
import path from "node:path";

const outDir = path.resolve(".ua/intermediate");

const edge = (source, target, type, weight) => ({
  source,
  target,
  type,
  direction: "forward",
  weight,
});

const node = (id, type, name, filePath, summary, tags, complexity, extra = {}) => ({
  id,
  type,
  name,
  filePath,
  summary,
  tags,
  complexity,
  ...extra,
});

const functionNode = (filePath, name, lineRange, summary, tags, complexity = "simple") =>
  node(`function:${filePath}:${name}`, "function", name, filePath, summary, tags, complexity, { lineRange });

const classNode = (filePath, name, lineRange, summary, tags, complexity = "simple") =>
  node(`class:${filePath}:${name}`, "class", name, filePath, summary, tags, complexity, { lineRange });

const batch9 = {
  nodes: [
    node(
      "document:docs/TOUTIAO_RAG_GUIDE.md",
      "document",
      "TOUTIAO_RAG_GUIDE.md",
      "docs/TOUTIAO_RAG_GUIDE.md",
      "头条长文 RAG 实战指南，说明 LangChain 与 LangGraph 的职责分工、入库和检索步骤、相关文件清单及故障排查。",
      ["documentation", "rag", "langgraph", "onboarding"],
      "moderate"
    ),
    node(
      "document:docs/resume_agent_fullstack.md",
      "document",
      "resume_agent_fullstack.md",
      "docs/resume_agent_fullstack.md",
      "面向 AI 全栈工程师岗位的 Markdown 简历源稿，覆盖技能、经历、项目亮点、教育背景与投递前说明。",
      ["documentation", "resume", "project-overview", "markdown"],
      "moderate"
    ),
    node(
      "config:docs/template_doc.xml",
      "config",
      "template_doc.xml",
      "docs/template_doc.xml",
      "从 Word 简历模板提取的 WordprocessingML 文档主体，保留段落、字体、边框和版式属性供模板分析或复用。",
      ["configuration", "wordprocessingml", "document-template", "formatting"],
      "complex",
      { languageNotes: "文件虽只有一条物理行，但包含完整的 WordprocessingML 文档树。" }
    ),
    node(
      "document:docs/template_lines.txt",
      "document",
      "template_lines.txt",
      "docs/template_lines.txt",
      "按段落索引列出的简历模板纯文本快照，用于确认 python-docx 修改时所依赖的段落位置和内容。",
      ["documentation", "resume-template", "paragraph-index", "debugging"],
      "simple"
    ),
    node(
      "document:docs/template_structure.txt",
      "document",
      "template_structure.txt",
      "docs/template_structure.txt",
      "记录简历模板各段落样式与文本结构的诊断快照，辅助验证列表、普通段落和空段落布局。",
      ["documentation", "resume-template", "document-structure", "debugging"],
      "simple"
    ),
  ],
  edges: [
    edge("document:docs/template_lines.txt", "config:docs/template_doc.xml", "related", 0.5),
    edge("document:docs/template_structure.txt", "config:docs/template_doc.xml", "related", 0.5),
    edge("document:docs/resume_agent_fullstack.md", "document:docs/template_lines.txt", "related", 0.5),
  ],
};

const batch10 = {
  nodes: [
    node(
      "config:frontend/.env.example",
      "config",
      ".env.example",
      "frontend/.env.example",
      "前端环境变量示例，声明可选的 VITE_API_BASE；开发环境留空时由 Vite 代理访问本地后端。",
      ["configuration", "environment", "vite", "api-base"],
      "simple"
    ),
    node(
      "document:frontend/README.md",
      "document",
      "README.md",
      "frontend/README.md",
      "React + Vite 前端的使用说明，概述鉴权、任务、热榜和管理功能，并给出开发、构建和环境变量配置步骤。",
      ["documentation", "frontend", "react", "getting-started"],
      "simple"
    ),
    node(
      "file:frontend/index.html",
      "file",
      "index.html",
      "frontend/index.html",
      "Vite 单页应用的 HTML 外壳，加载中英文字体、提供 root 挂载节点并启动 src/main.tsx。",
      ["entry-point", "html", "vite", "react"],
      "simple"
    ),
    node(
      "config:frontend/package.json",
      "config",
      "package.json",
      "frontend/package.json",
      "前端包清单与脚本配置，定义 Vite 开发、TypeScript 校验构建和预览命令，以及 React 运行时依赖。",
      ["configuration", "package-manager", "build-system", "react"],
      "simple"
    ),
    node(
      "config:frontend/tsconfig.json",
      "config",
      "tsconfig.json",
      "frontend/tsconfig.json",
      "前端 TypeScript 严格编译配置，启用 bundler 模块解析、React JSX、未使用代码检查和 @/* 路径别名。",
      ["configuration", "typescript", "strict-mode", "build-system"],
      "simple"
    ),
  ],
  edges: [
    edge("document:frontend/README.md", "file:frontend/index.html", "documents", 0.5),
    edge("config:frontend/package.json", "config:frontend/tsconfig.json", "depends_on", 0.6),
    edge("config:frontend/.env.example", "config:frontend/package.json", "configures", 0.6),
  ],
};

const batch11 = {
  nodes: [
    node(
      "schema:scripts/init_mysql.sql",
      "schema",
      "init_mysql.sql",
      "scripts/init_mysql.sql",
      "MySQL 本地初始化脚本，创建 utf8mb4 的 copy_generator 数据库、应用账号并授予数据库权限。",
      ["database", "initialization", "mysql", "security"],
      "simple"
    ),
    node(
      "table:scripts/migrate_add_toutiao_platform.sql:migration",
      "table",
      "migrate_add_toutiao_platform.sql",
      "scripts/migrate_add_toutiao_platform.sql",
      "扩展 tasks.platform 枚举以支持头条、微博、微信、抖音、小红书和知乎等内容平台。",
      ["database", "migration", "mysql", "platform"],
      "simple"
    ),
    node(
      "table:scripts/migrate_add_toutiao_platform.sql:tasks",
      "table",
      "tasks",
      "scripts/migrate_add_toutiao_platform.sql",
      "迁移脚本所修改的任务表，将 platform 列约束为受支持平台枚举并设置默认值。",
      ["database", "table", "task-model", "platform"],
      "simple"
    ),
    node(
      "table:scripts/migrate_agentic_phase2.sql:migration",
      "table",
      "migrate_agentic_phase2.sql",
      "scripts/migrate_agentic_phase2.sql",
      "Agentic 编排第二阶段迁移，为任务记录增加可空 JSON 编排元数据，并说明人工介入状态的枚举扩展方式。",
      ["database", "migration", "agentic", "orchestration"],
      "simple"
    ),
    node(
      "table:scripts/migrate_agentic_phase2.sql:tasks",
      "table",
      "tasks",
      "scripts/migrate_agentic_phase2.sql",
      "迁移脚本所修改的任务表，新增 orchestration_meta JSON 字段以持久化编排上下文。",
      ["database", "table", "task-model", "metadata"],
      "simple"
    ),
    node(
      "table:scripts/migrate_audit_logs.sql:migration",
      "table",
      "migrate_audit_logs.sql",
      "scripts/migrate_audit_logs.sql",
      "创建编排全链路审计日志表的 Phase 3 数据库迁移，包含任务外键、步骤序号、耗时、失败信息和查询索引。",
      ["database", "migration", "audit-log", "orchestration"],
      "simple"
    ),
    node(
      "table:scripts/migrate_audit_logs.sql:orchestration_audit_logs",
      "table",
      "orchestration_audit_logs",
      "scripts/migrate_audit_logs.sql",
      "按任务和执行序列记录 Agent 编排步骤输入输出、状态、失败级别、耗时与错误详情的审计表。",
      ["database", "table", "audit-log", "observability"],
      "simple"
    ),
    node(
      "table:scripts/migrate_style_pattern.sql:migration",
      "table",
      "migrate_style_pattern.sql",
      "scripts/migrate_style_pattern.sql",
      "为头条参考文章增加互动量字段和索引，并创建按主题与平台保存风格模式的 style_cards 表。",
      ["database", "migration", "style-pattern", "analytics"],
      "simple"
    ),
    node(
      "table:scripts/migrate_style_pattern.sql:toutiao_reference",
      "table",
      "toutiao_reference",
      "scripts/migrate_style_pattern.sql",
      "迁移脚本扩展的头条参考文章表，新增点赞、阅读、评论与发布时间字段并建立点赞量索引。",
      ["database", "table", "toutiao", "engagement"],
      "simple"
    ),
    node(
      "table:scripts/migrate_style_pattern.sql:style_cards",
      "table",
      "style_cards",
      "scripts/migrate_style_pattern.sql",
      "存储主题聚类、平台、风格模式 JSON、来源文章、置信度和平均点赞量的风格卡表。",
      ["database", "table", "style-card", "rag"],
      "simple"
    ),
  ],
  edges: [
    edge("table:scripts/migrate_add_toutiao_platform.sql:migration", "table:scripts/migrate_add_toutiao_platform.sql:tasks", "migrates", 0.7),
    edge("table:scripts/migrate_agentic_phase2.sql:migration", "table:scripts/migrate_agentic_phase2.sql:tasks", "migrates", 0.7),
    edge("table:scripts/migrate_audit_logs.sql:migration", "table:scripts/migrate_audit_logs.sql:orchestration_audit_logs", "migrates", 0.7),
    edge("table:scripts/migrate_style_pattern.sql:migration", "table:scripts/migrate_style_pattern.sql:toutiao_reference", "migrates", 0.7),
    edge("table:scripts/migrate_style_pattern.sql:migration", "table:scripts/migrate_style_pattern.sql:style_cards", "migrates", 0.7),
  ],
};

const batch12Nodes = [
  node("file:app/__init__.py", "file", "__init__.py", "app/__init__.py", "应用顶层 Python 包标记文件，用于将 app 目录作为可导入包。", ["package", "python", "namespace"], "simple"),
  node("file:app/agents/__init__.py", "file", "__init__.py", "app/agents/__init__.py", "Agents 包公共入口，通过模块级 __getattr__ 惰性暴露编排器和三个 Agent，避免与 skills 包形成循环依赖。", ["entry-point", "agents", "lazy-import", "orchestration"], "simple"),
  node("file:app/api/__init__.py", "file", "__init__.py", "app/api/__init__.py", "API 子包标记文件，为路由和接口模块提供 Python 包命名空间。", ["package", "api", "python"], "simple"),
  node("file:app/core/__init__.py", "file", "__init__.py", "app/core/__init__.py", "核心基础设施子包的空入口文件，用于组织配置、鉴权等共享能力。", ["package", "core", "python"], "simple"),
  node("file:app/lang/__init__.py", "file", "__init__.py", "app/lang/__init__.py", "说明头条长文 RAG 的 LangChain 与 LangGraph 分层、目录职责以及推荐阅读顺序的包文档入口。", ["package", "rag", "langchain", "documentation"], "simple"),
  node("file:app/lang/graph/__init__.py", "file", "__init__.py", "app/lang/graph/__init__.py", "LangGraph 流程编排包说明，列出入库、检索、固定编排、Agentic 和 Lead 等状态图及其调用方。", ["package", "langgraph", "orchestration", "documentation"], "simple"),
  node("file:app/lang/rag/__init__.py", "file", "__init__.py", "app/lang/rag/__init__.py", "LangChain RAG 工具包说明，映射图节点到切块、入库、检索和提示词格式化函数。", ["package", "rag", "langchain", "documentation"], "simple"),
  node("file:app/services/__init__.py", "file", "__init__.py", "app/services/__init__.py", "服务层子包标记文件，为业务服务实现提供统一命名空间。", ["package", "service-layer", "python"], "simple"),
  node("file:app/utils/__init__.py", "file", "__init__.py", "app/utils/__init__.py", "通用工具子包标记文件，用于组织跨模块复用的辅助函数。", ["package", "utility", "python"], "simple"),
  node("file:docs/resume_agent_fullstack.docx", "file", "resume_agent_fullstack.docx", "docs/resume_agent_fullstack.docx", "由 Markdown 简历源稿生成的 Word 投递文档，包含 AI 全栈技能、项目经历和教育背景等排版内容。", ["document-artifact", "resume", "docx", "generated"], "moderate"),
  node("file:frontend/src/styles/index.css", "file", "index.css", "frontend/src/styles/index.css", "前端全局样式表，集中定义应用布局、鉴权表单、任务卡片、热榜、Agent Pipeline、审计时间线及响应式交互视觉。", ["stylesheet", "frontend", "design-system", "responsive"], "complex", { languageNotes: "单文件覆盖整套界面组件状态，包括 pending、processing、awaiting_human、completed 和 failed。" }),
  node("file:frontend/src/vite-env.d.ts", "file", "vite-env.d.ts", "frontend/src/vite-env.d.ts", "Vite 客户端类型声明，补充 ImportMetaEnv 中 VITE_API_BASE 的只读字符串类型。", ["type-definition", "vite", "environment", "typescript"], "simple"),
  node("file:frontend/tsconfig.tsbuildinfo", "file", "tsconfig.tsbuildinfo", "frontend/tsconfig.tsbuildinfo", "TypeScript 增量构建缓存元数据，由编译器生成以加速后续类型检查和构建。", ["build-cache", "typescript", "generated"], "simple"),
  node("file:frontend/vite.config.ts", "file", "vite.config.ts", "frontend/vite.config.ts", "Vite 开发服务器配置，启用 React 插件、固定 5173 端口并将 /api 请求代理到本地 8000 后端。", ["configuration", "vite", "react", "development-server"], "simple"),
  node("file:gunicorn.conf.py", "file", "gunicorn.conf.py", "gunicorn.conf.py", "FastAPI 生产 Gunicorn 配置，使用 Uvicorn worker 并设置进程数、超时、日志、请求回收与生命周期钩子。", ["configuration", "gunicorn", "deployment", "asgi"], "moderate"),
  node("file:nginx.conf", "file", "nginx.conf", "nginx.conf", "生产 Nginx 反向代理配置，提供 HTTP 到 HTTPS 跳转、TLS、限流、压缩、健康检查和 FastAPI 路由转发。", ["configuration", "nginx", "reverse-proxy", "security"], "moderate"),
  node("file:scripts/fill_user_resume_docx.py", "file", "fill_user_resume_docx.py", "scripts/fill_user_resume_docx.py", "基于固定段落索引填充用户 Word 简历模板的脚本，自底向上修改内容、插入项目亮点并在写入前创建备份。", ["script", "docx", "resume", "automation"], "moderate"),
  node("file:scripts/md_resume_to_docx.py", "file", "md_resume_to_docx.py", "scripts/md_resume_to_docx.py", "将 Markdown 简历转换为格式化 Word 文档，支持标题、富文本粗体、列表、引用和表格，并统一设置中文字体。", ["script", "markdown", "docx", "converter"], "moderate"),
  node("file:scripts/study.py", "file", "study.py", "scripts/study.py", "LangGraph 最小学习示例，以 TypedDict 状态执行求和或乘积节点并编译为可调用状态图。", ["example", "langgraph", "state-machine", "learning"], "simple"),
  node("file:tests/__init__.py", "file", "__init__.py", "tests/__init__.py", "测试包标记文件，使测试模块可以使用包级导入。", ["test", "package", "python"], "simple"),
  node("file:tests/conftest.py", "file", "conftest.py", "tests/conftest.py", "Pytest 公共配置，在测试收集和每个测试执行前导入全部 ORM 模型，确保 create_all 能创建新增表。", ["test", "pytest", "fixture", "database"], "simple"),

  functionNode("app/agents/__init__.py", "__getattr__", [15, 28], "按请求名称惰性导入并返回编排器或具体 Agent 类，未知名称抛出 AttributeError。", ["lazy-import", "factory", "agents"]),

  functionNode("gunicorn.conf.py", "on_starting", [67, 68], "Gunicorn 主服务启动钩子，向服务器日志写入启动状态。", ["lifecycle-hook", "logging", "gunicorn"]),
  functionNode("gunicorn.conf.py", "on_exit", [70, 71], "Gunicorn 主服务退出钩子，记录服务器关闭状态。", ["lifecycle-hook", "logging", "gunicorn"]),
  functionNode("gunicorn.conf.py", "worker_init", [73, 74], "Gunicorn worker 初始化钩子，记录新 worker 的进程号。", ["lifecycle-hook", "logging", "worker"]),

  functionNode("scripts/fill_user_resume_docx.py", "insert_paragraph_after", [17, 25], "在指定 Word 段落后插入新段落，并按需设置样式和初始文本。", ["utility", "docx", "paragraph"]),
  functionNode("scripts/fill_user_resume_docx.py", "set_para_text", [28, 32], "清空段落后写入新文本，并可显式设置粗体属性。", ["utility", "docx", "formatting"]),
  functionNode("scripts/fill_user_resume_docx.py", "set_title_line", [35, 40], "重建带制表符分隔的标题与日期行，并控制标题粗体。", ["utility", "docx", "formatting"]),
  functionNode("scripts/fill_user_resume_docx.py", "add_bullets", [43, 47], "在给定段落后依次插入项目符号列表并返回最后一个段落。", ["utility", "docx", "list"]),
  functionNode("scripts/fill_user_resume_docx.py", "add_numbered_items", [50, 54], "在给定段落后插入带序号的列表项并返回尾段落。", ["utility", "docx", "list"]),
  functionNode("scripts/fill_user_resume_docx.py", "main", [57, 135], "备份并加载简历模板，自底向上替换教育、经历、项目和技能内容，最后覆盖或另存 Word 文件。", ["entry-point", "resume", "automation", "file-io"], "moderate"),

  functionNode("scripts/md_resume_to_docx.py", "set_cn_font", [18, 24], "同时设置 Word run 的西文字体与东亚字体，并按需应用字号和粗体。", ["utility", "docx", "font"]),
  functionNode("scripts/md_resume_to_docx.py", "add_rich_paragraph", [27, 39], "解析 Markdown 粗体片段并创建统一中文字体的 Word 段落。", ["parser", "docx", "markdown"]),
  functionNode("scripts/md_resume_to_docx.py", "parse_table", [42, 50], "从 Markdown 表格行解析表头和二维数据行。", ["parser", "markdown", "table"]),
  functionNode("scripts/md_resume_to_docx.py", "add_table", [53, 68], "向 Word 文档写入网格表格，并分别格式化表头与数据单元格字体。", ["renderer", "docx", "table"], "moderate"),
  functionNode("scripts/md_resume_to_docx.py", "convert", [71, 173], "逐行解析 Markdown 标题、分隔线、表格、引用和列表，构建带页面边距与中文排版的 Word 文档。", ["converter", "markdown", "docx", "parser"], "moderate"),
  functionNode("scripts/md_resume_to_docx.py", "main", [176, 180], "读取简历 Markdown 源文件，执行转换并将结果保存为 DOCX。", ["entry-point", "converter", "file-io"]),

  classNode("scripts/study.py", "State", [4, 8], "定义 LangGraph 示例状态的名称、数值列表、运算类型与结果字段。", ["state-model", "typeddict", "langgraph"]),
  functionNode("scripts/study.py", "calculate_and_format", [10, 21], "根据状态选择求和或乘积运算，将字符串结果写回状态；不支持的运算会抛错。", ["graph-node", "calculation", "state-transition"]),

  functionNode("tests/conftest.py", "pytest_configure", [10, 12], "在 Pytest 配置阶段导入 app.models，确保 ORM 模型在建表前注册。", ["pytest-hook", "database", "model-registration"]),
  functionNode("tests/conftest.py", "_register_all_orm_models", [16, 17], "自动使用的测试夹具，在每个测试上下文再次确保 ORM 模型已注册。", ["fixture", "database", "model-registration"]),
];

const batch12Edges = [];
const exportedFunctions = [
  ["app/agents/__init__.py", "__getattr__"],
  ["gunicorn.conf.py", "on_starting"],
  ["gunicorn.conf.py", "on_exit"],
  ["gunicorn.conf.py", "worker_init"],
  ["scripts/fill_user_resume_docx.py", "insert_paragraph_after"],
  ["scripts/fill_user_resume_docx.py", "set_para_text"],
  ["scripts/fill_user_resume_docx.py", "set_title_line"],
  ["scripts/fill_user_resume_docx.py", "add_bullets"],
  ["scripts/fill_user_resume_docx.py", "add_numbered_items"],
  ["scripts/fill_user_resume_docx.py", "main"],
  ["scripts/md_resume_to_docx.py", "set_cn_font"],
  ["scripts/md_resume_to_docx.py", "add_rich_paragraph"],
  ["scripts/md_resume_to_docx.py", "parse_table"],
  ["scripts/md_resume_to_docx.py", "add_table"],
  ["scripts/md_resume_to_docx.py", "convert"],
  ["scripts/md_resume_to_docx.py", "main"],
  ["scripts/study.py", "calculate_and_format"],
  ["tests/conftest.py", "pytest_configure"],
  ["tests/conftest.py", "_register_all_orm_models"],
];
const exportedClasses = [["scripts/study.py", "State"]];

for (const [filePath, name] of exportedFunctions) {
  const fileId = `file:${filePath}`;
  const symbolId = `function:${filePath}:${name}`;
  batch12Edges.push(edge(fileId, symbolId, "contains", 1.0));
  batch12Edges.push(edge(fileId, symbolId, "exports", 0.8));
}
for (const [filePath, name] of exportedClasses) {
  const fileId = `file:${filePath}`;
  const symbolId = `class:${filePath}:${name}`;
  batch12Edges.push(edge(fileId, symbolId, "contains", 1.0));
  batch12Edges.push(edge(fileId, symbolId, "exports", 0.8));
}

batch12Edges.push(
  edge("file:scripts/fill_user_resume_docx.py", "file:docs/resume_agent_fullstack.docx", "depends_on", 0.6),
  edge("file:scripts/md_resume_to_docx.py", "file:docs/resume_agent_fullstack.docx", "depends_on", 0.6),
  edge("file:frontend/vite.config.ts", "file:frontend/src/vite-env.d.ts", "related", 0.5),
  edge("file:nginx.conf", "file:gunicorn.conf.py", "routes", 0.6),
  edge("file:tests/conftest.py", "file:tests/__init__.py", "related", 0.5)
);

const batches = new Map([
  [9, batch9],
  [10, batch10],
  [11, batch11],
  [12, { nodes: batch12Nodes, edges: batch12Edges }],
]);

const validTypes = new Set(["file", "function", "class", "config", "document", "service", "table", "endpoint", "pipeline", "schema", "resource"]);
const validComplexity = new Set(["simple", "moderate", "complex"]);
const validEdgeTypes = new Set(["contains", "imports", "calls", "inherits", "implements", "exports", "depends_on", "tested_by", "configures", "documents", "deploys", "migrates", "triggers", "defines_schema", "serves", "provisions", "routes", "related"]);

for (const [index, graph] of batches) {
  const ids = new Set();
  for (const n of graph.nodes) {
    if (!n.id || !validTypes.has(n.type) || !n.name || !n.summary || !Array.isArray(n.tags) || n.tags.length < 3 || !validComplexity.has(n.complexity)) {
      throw new Error(`batch ${index}: invalid node ${JSON.stringify(n)}`);
    }
    if (ids.has(n.id)) throw new Error(`batch ${index}: duplicate node ${n.id}`);
    ids.add(n.id);
  }
  for (const e of graph.edges) {
    if (!ids.has(e.source) || !ids.has(e.target)) throw new Error(`batch ${index}: dangling local edge ${e.source} -> ${e.target}`);
    if (e.source === e.target) throw new Error(`batch ${index}: self edge ${e.source}`);
    if (!validEdgeTypes.has(e.type) || e.direction !== "forward") throw new Error(`batch ${index}: invalid edge`);
  }
  const outputPath = path.join(outDir, `batch-${index}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify(graph, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ batch: index, nodes: graph.nodes.length, edges: graph.edges.length, outputPath }));
}
