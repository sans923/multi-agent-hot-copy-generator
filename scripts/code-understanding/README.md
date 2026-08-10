# Code understanding tools

The tool source code is shared across projects:

- Understand Anything: `D:\workspace\_tooling\ai\plugins\understand-anything`
- DeepWiki Open: `D:\workspace\_tooling\tools\gui\deepwiki-open`
- GitDiagram: `D:\workspace\_tooling\tools\gui\gitdiagram`

Project-specific Understand Anything skills are installed under `.codex/skills/`.
Restart Codex, then run `$understand` followed by `$understand-dashboard`.

DeepWiki Open and GitDiagram run in isolated Docker containers. Their model
credentials are not read from this application's `.env`.

1. Copy the matching example from
   `D:\workspace\_tooling\config\templates\code-understanding\` to
   `D:\workspace\_tooling\config\code-understanding\`.
2. Add a model API key to the copied file.
3. Start a tool:

```powershell
.\scripts\code-understanding\start.ps1 deepwiki up
.\scripts\code-understanding\start.ps1 gitdiagram up
```

DeepWiki opens at `http://localhost:3001`; GitDiagram opens at
`http://localhost:3002`. Analyze this repository using:

```text
https://github.com/sans923/multi-agent-hot-copy-generator
```

Other actions are `build`, `logs`, `status`, and `down`.

