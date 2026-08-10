const fs = require("fs");
const path = require("path");

const root = process.cwd();
const batches = JSON.parse(fs.readFileSync(".ua/intermediate/batches.json", "utf8")).batches;
const selected = new Set([3, 6, 9, 12]);

const fileSummary = {
  "frontend/src/App.tsx": "定义前端路由总入口，组合认证、管理员权限、全局布局与各业务页面。",
  "frontend/src/api/auth.ts": "封装登录、注册、当前用户查询与退出登录等认证接口。",
  "frontend/src/api/client.ts": "提供统一 HTTP 请求客户端、令牌持久化和结构化 API 错误处理。",
  "frontend/src/api/contentAssets.ts": "封装参考素材导入、重建索引及风格卡片管理接口。",
  "frontend/src/api/hotlist.ts": "封装热点榜单查询、搜索、同步和统计接口。",
  "frontend/src/api/logs.ts": "封装任务审计轨迹与智能体运行日志查询接口。",
  "frontend/src/api/tasks.ts": "封装文案任务创建、列表、详情、结果和恢复执行接口。",
  "frontend/src/api/users.ts": "封装个人资料读取更新及管理员用户列表接口。",
  "frontend/src/components/AdminRoute.tsx": "实现管理员路由守卫，阻止非管理员访问后台页面。",
  "frontend/src/components/AgentPipeline.tsx": "可视化多智能体流水线阶段及当前执行进度。",
  "frontend/src/components/AuditTimeline.tsx": "展示任务审计事件和智能体日志组成的时间线。",
  "frontend/src/components/Layout.tsx": "提供带导航、用户信息与内容出口的应用外壳。",
  "frontend/src/components/ProtectedRoute.tsx": "实现登录态路由守卫，并处理认证加载和跳转。",
  "frontend/src/contexts/AuthContext.tsx": "集中管理当前用户、令牌、登录注册和退出状态。",
  "frontend/src/contexts/ToastContext.tsx": "提供全局轻提示队列及便捷调用钩子。",
  "frontend/src/main.tsx": "挂载 React 应用并加载全局样式，是浏览器端启动入口。",
  "frontend/src/pages/AdminUsers.tsx": "管理员用户管理页面，加载并展示平台用户信息。",
  "frontend/src/pages/ContentAssets.tsx": "管理 RAG 参考素材和风格卡片，支持导入、重建与删除。",
  "frontend/src/pages/CreateTask.tsx": "汇集热点、素材与生成参数，创建多智能体文案任务。",
  "frontend/src/pages/Dashboard.tsx": "展示任务概览、状态统计和最近任务列表。",
  "frontend/src/pages/Hotlist.tsx": "提供热点浏览、搜索、同步和选题入口。",
  "frontend/src/pages/Login.tsx": "处理用户登录表单、错误反馈和登录后跳转。",
  "frontend/src/pages/Profile.tsx": "展示并编辑当前用户资料及偏好设置。",
  "frontend/src/pages/Register.tsx": "处理新用户注册、校验、错误提示和自动登录。",
  "frontend/src/pages/TaskDetail.tsx": "任务详情主页面，整合生成结果、流水线、审计记录及恢复操作。",
  "frontend/src/types/api.ts": "集中定义前后端 API 数据模型、任务状态和展示标签。",
  "app/orchestration/__init__.py": "作为编排包公共入口，汇总引擎接口、工厂和具体实现。",
  "app/orchestration/base.py": "定义编排引擎抽象契约及统一的任务执行输入输出。",
  "app/orchestration/factory.py": "维护编排引擎注册表，并按配置选择和实例化执行引擎。",
  "app/orchestration/langgraph_engine.py": "以 LangGraph 流程图实现编排引擎，执行文案生成图。",
  "app/orchestration/native_engine.py": "提供原生编排适配器，将任务委托给既有流水线执行器。",
  "tests/test_orchestration.py": "覆盖编排工厂、状态初始化、成功与失败路径及两类引擎委托行为。",
  "docs/TOUTIAO_RAG_GUIDE.md": "说明今日头条内容采集、清洗、索引和 RAG 检索的配置与使用流程。",
  "docs/resume_agent_fullstack.md": "面向 AI 全栈工程师岗位整理项目经历、技术栈和简历表述素材。",
  "docs/template_doc.xml": "保存简历 Word 模板的 OOXML 文档主体、段落样式与版式结构。",
  "docs/template_lines.txt": "按段落序号记录简历模板的可见文本，供模板定位与内容替换。",
  "docs/template_structure.txt": "记录简历模板段落样式和文本结构，便于分析 Word 文档布局。",
  "frontend/src/styles/index.css": "定义前端深色主题、响应式布局、页面组件和状态视觉样式。",
  "frontend/tsconfig.tsbuildinfo": "保存 TypeScript 增量编译缓存元数据，不承载运行时业务逻辑。",
  "frontend/src/vite-env.d.ts": "声明 Vite 客户端环境类型，使 TypeScript 识别构建时注入能力。",
  "frontend/vite.config.ts": "配置 React 的 Vite 开发与构建流程及后端 API 代理。",
  "gunicorn.conf.py": "配置 Gunicorn 进程、超时、日志和生命周期钩子以承载后端服务。",
  "nginx.conf": "配置 Nginx 静态资源服务、HTTPS、限流和 FastAPI 反向代理。",
  "scripts/fill_user_resume_docx.py": "按固定模板定位段落并填充用户简历内容、项目条目和列表。",
  "scripts/md_resume_to_docx.py": "解析 Markdown 简历并生成带中文字体、列表和表格样式的 DOCX。",
  "scripts/study.py": "提供一个小型状态模型和数值格式化示例，用于实验性学习。",
  "tests/conftest.py": "配置 pytest 环境并确保 ORM 模型在测试启动前完成注册。"
};

function complexity(lines) {
  return lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";
}
function fileType(f) {
  if (f.fileCategory === "docs") return "document";
  if (f.fileCategory === "config") return "config";
  return "file";
}
function prefix(type) {
  return type === "document" ? "document" : type === "config" ? "config" : "file";
}
function fileTags(f) {
  const p = f.path;
  if (f.fileCategory === "docs") return ["文档", "使用指南", "项目资料"];
  if (f.fileCategory === "config") return ["配置", "文档模板", "office"];
  if (p.includes("/api/")) return ["api-client", "接口封装", "数据访问"];
  if (p.includes("/pages/")) return ["react", "页面组件", "前端交互"];
  if (p.includes("/components/")) return ["react", "可复用组件", "前端展示"];
  if (p.includes("/contexts/")) return ["react-context", "状态管理", "自定义钩子"];
  if (p.includes("orchestration")) return p.startsWith("tests/") ? ["测试", "编排引擎", "集成验证"] : ["编排引擎", "策略模式", "任务执行"];
  if (p.endsWith(".css")) return ["样式系统", "主题", "响应式布局"];
  if (p.includes("vite")) return ["配置", "vite", "构建系统"];
  if (p === "nginx.conf") return ["基础设施", "反向代理", "安全"];
  if (p === "gunicorn.conf.py") return ["配置", "gunicorn", "进程管理"];
  if (p.startsWith("scripts/")) return ["脚本", "文档生成", "自动化"];
  if (p.startsWith("tests/")) return ["测试", "测试配置", "pytest"];
  if (p.endsWith("__init__.py")) return ["包入口", "模块导出", "python"];
  if (p.includes("/types/") || p.endsWith(".d.ts")) return ["类型定义", "typescript", "接口模型"];
  return ["应用代码", "模块", "项目基础"];
}
function functionSummary(name, p) {
  if (name.startsWith("test_")) return `验证“${name}”对应的编排行为及预期结果。`;
  if (name === "request") return "统一组装请求头、解析响应并将失败响应转换为结构化错误。";
  if (name === "AuthProvider") return "加载当前用户并向组件树提供认证操作和会话状态。";
  if (name === "ToastProvider") return "管理轻提示生命周期并向组件树暴露通知方法。";
  if (name === "convert") return "解析 Markdown 各类块并将其转换为带样式的 Word 文档。";
  if (name === "main") return `组织并执行 ${path.basename(p)} 的命令行处理流程。`;
  if (/^[A-Z]/.test(name)) return `实现 ${name} 页面或组件的状态管理、数据加载与界面渲染。`;
  if (name.startsWith("get_") || name.startsWith("list") || name.startsWith("fetch")) return `执行 ${name} 对应的数据查询并返回类型化结果。`;
  return `实现 ${name} 对应的核心处理流程，并封装为可复用单元。`;
}
function makeOutput(batch) {
  const extract = JSON.parse(fs.readFileSync(`.ua/tmp/ua-file-extract-results-${batch.batchIndex}.json`, "utf8"));
  const byPath = new Map(extract.results.map(r => [r.path, r]));
  const nodes = [], edges = [];
  for (const f of batch.files) {
    const r = byPath.get(f.path);
    const type = fileType(f);
    const id = `${prefix(type)}:${f.path}`;
    const nonEmpty = r?.nonEmptyLines ?? f.sizeLines;
    nodes.push({
      id, type, name: path.basename(f.path), filePath: f.path,
      summary: fileSummary[f.path] || `承载 ${f.path} 对应的项目内容与结构。`,
      tags: fileTags(f), complexity: complexity(nonEmpty)
    });
    if (f.fileCategory !== "code" || !r) continue;
    const exported = new Set((r.exports || []).map(x => x.name));
    for (const item of [...(r.functions || []), ...(r.classes || [])]) {
      const isClass = (r.classes || []).includes(item);
      const span = item.endLine - item.startLine + 1;
      if (!(exported.has(item.name) || span >= 10 || (isClass && ((item.methods || []).length >= 2 || span >= 20)))) continue;
      const nt = isClass ? "class" : "function";
      const nid = `${nt}:${f.path}:${item.name}`;
      nodes.push({
        id: nid, type: nt, name: item.name, filePath: f.path,
        lineRange: [item.startLine, item.endLine],
        summary: functionSummary(item.name, f.path),
        tags: isClass ? ["类", "核心抽象", "可扩展"] : ["函数", "业务逻辑", exported.has(item.name) ? "公开接口" : "内部流程"],
        complexity: complexity(span)
      });
      edges.push({source:id,target:nid,type:"contains",direction:"forward",weight:1.0});
      if (exported.has(item.name)) edges.push({source:id,target:nid,type:"exports",direction:"forward",weight:0.8});
    }
  }
  for (const f of batch.files) {
    if (f.fileCategory !== "code") continue;
    for (const target of batch.batchImportData[f.path] || []) {
      edges.push({source:`file:${f.path}`,target:`file:${target}`,type:"imports",direction:"forward",weight:0.7});
    }
  }
  if (batch.batchIndex === 12) {
    edges.push({source:"file:frontend/src/styles/index.css",target:"file:frontend/src/main.tsx",type:"related",direction:"forward",weight:0.5});
  }
  return {nodes, edges};
}
function writeParts(index, out, files) {
  const parts = Math.ceil(Math.max(out.nodes.length / 60, out.edges.length / 120));
  if (parts <= 1) {
    fs.writeFileSync(`.ua/intermediate/batch-${index}.json`, JSON.stringify(out, null, 2));
    return 1;
  }
  const sorted = [...files].sort((a,b)=>a.path.localeCompare(b.path));
  const chunkSize = Math.ceil(sorted.length / parts);
  for (let k=0;k<parts;k++) {
    const paths = new Set(sorted.slice(k*chunkSize,(k+1)*chunkSize).map(f=>f.path));
    const partNodes = out.nodes.filter(n=>paths.has(n.filePath));
    const ids = new Set(partNodes.map(n=>n.id));
    const partEdges = out.edges.filter(e=>ids.has(e.source));
    fs.writeFileSync(`.ua/intermediate/batch-${index}-part-${k+1}.json`, JSON.stringify({nodes:partNodes,edges:partEdges}, null, 2));
  }
  return parts;
}
for (const batch of batches.filter(b=>selected.has(b.batchIndex))) {
  const out = makeOutput(batch);
  const parts = writeParts(batch.batchIndex, out, batch.files);
  console.log(JSON.stringify({batch:batch.batchIndex,parts,nodes:out.nodes.length,edges:out.edges.length}));
}
