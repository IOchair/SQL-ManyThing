# SQL-ManyThing

**让你的 AI Agent 拥有整个代码库的搜索记忆。一个文件。零服务器。即时检索。**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9%2B-green.svg)](https://www.python.org/)
[![SQLite: 3.35+](https://img.shields.io/badge/SQLite-3.35%2B-orange.svg)](https://www.sqlite.org/) · [🇬🇧 English](README.md)

```bash
# 索引 89K 个文件
python3 scripts/phase1/manything_build_db.py /path/to/project

# 毫秒级查询
sqlite3 /manything/myproject/source.db \
  "SELECT f.path, rank FROM files_fts, files f
   WHERE files_fts MATCH 'layout prepare'
     AND files_fts.rowid = f.id
   ORDER BY rank LIMIT 10;"
```

---

## 🤖 零配置 Agent 提示词 (如果很急，但最好别)

无需安装。把这三条 prompt 依次喂给**任何一个全新的 AI 编程 Agent**，它会自动复现整个安装流程：

**Prompt 1: 索引代码库**
```text
FTS5 + trigram full-text index the target project; design your own filter rules
```

**Prompt 2: 富化并探索**
```text
Interactively query the DB, discover enrichment table designs, write batch enrichment scripts
```

**Prompt 3: 启用查询记忆**
```text
Auto-ingest SQL queries into the trace database, enabling historical query exploration before running new searches
```

现在你知道了配方。准备好深入了解时再回来。

---

## 快速开始

### 让 Agent 帮你装

SQL-ManyThing 以自包含脚本的形式发布，Phase 1–2 零外部依赖。把这段话复制给你的 Agent：

> **前提：** 需要一个能访问网络并执行 shell 的 Agent（Claude、Cursor、Codex 等）。离线环境请使用下面的手动步骤。

> 阅读 https://github.com/IOchair/SQL-ManyThing/tree/master 的 AGENTS.md 并为当前项目安装 SQL-ManyThing。对项目执行 Phase 1 索引，运行 Phase 2 通用富化，设置 Phase 3 查询追踪，然后调用 `sql-manything` skill 索引目标目录。

无需 pip install，无需配置文件。Agent 会读取 `SKILL.md`，找到脚本并执行。

### 或者自己动手

```bash
git clone https://github.com/IOchair/SQL-ManyThing.git
cd SQL-ManyThing

# 1. 索引 (Phase 1)
python3 scripts/phase1/manything_build_db.py /path/to/project
# → 创建 .srcidx/source.db

# 2. 富化 (Phase 2 — 通用，所有语言)
python3 scripts/phase2/enrich_depth_segments.py /path/to/project --batch 500
python3 scripts/phase2/enrich_file_refs.py       /path/to/project --batch 500
python3 scripts/phase2/flatten_file_deps.py      /path/to/project
python3 scripts/phase2/create_enriched_view.py   /path/to/project

# 3. 追踪包装器 (Phase 3)
python3 scripts/phase3/install.py
echo 'MANYTHING_myproject="/path/to/project"' >> ~/.hermes/manything/aliases.sh
```

Phase 1 默认扩展名：`.h,.cpp,.cs,.py,.ts,.tsx,.js,.jsx,.rs,.java`。用 `--ext .md,.toml` 添加文档/配置文件，或用 `--profile unreal-installed-core` 处理 Unreal Engine 构建树。

### 验证

```bash
sqlite3 /manything/myproject/source.db "SELECT COUNT(*) FROM files;"
sqlite3 /manything/myproject/source.db \
  "SELECT f.path, rank FROM files_fts, files f
   WHERE files_fts MATCH 'layout prepare'
     AND files_fts.rowid = f.id
   ORDER BY rank LIMIT 10;"
```

---

## 特性

**89,203 个文件 · 3 GB · 毫秒级搜索 · 一个 SQLite 文件。**

- 🔍 **FTS5 trigram 全文搜索** — 毫秒内找到整个代码库中的任何符号
- 📦 **单个 SQLite 文件** — 无服务器、无后台进程、无网络。`scp` 到任何地方。
- ✂️ **有界提取** — `block_content_full` 只返回函数体。完整文件永不进入上下文。
- 🧠 **查询记忆** — 每次查询都被记录、可标记、可复用。索引越用越聪明。
- 👁️ **纯 SQL，完全可审计** — 无黑盒检索。每个结果都可追溯到一条 `SELECT`。
- 🌐 **语言无关** — C++、Python、JS、Rust、GLSL、生成代码——只要是文本就能索引。
- 🤖 **Agent 原生** — 稳定的脚本入口、规范化的 SQL 模板、`:trace` 查询复用。

---

## 环境要求

- **Python 3.9+**（Phase 1–2 仅需标准库；无需 pip install）
- **SQLite 3.35+** 且启用 FTS5 trigram 分词器（大多数系统默认包含）
- **Bash**（Linux/macOS/WSL）或 **PowerShell**（Windows）用于 Phase 3 包装器
- Phase 2 富化脚本仅使用 Python 标准库；可选的 `cymbal` 富化需要 `cymbal` CLI 二进制文件

---

## 生成了什么

**每个项目 — `.srcidx/source.db`：**

| 表 | 内容 |
|---|---|
| `files` | 文件元数据 + 完整文本内容 |
| `files_fts` | 基于 `path` + `content` 的 FTS5 trigram 索引 |
| `v_enriched` | 统一视图：深度分段块，含 `block_content_full` |
| `enrich_depth_segments` | 原始深度分段数据 |
| `enrich_file_deps` | 已解析的 import/include 依赖图 |
| `enrich_file_refs` | 原始 `#include` / `import` 字符串及行号 |

可选富化额外添加：`enrich_cymbal`（符号定义）、`enrich_graphify_nodes` / `_edges`（AST/文档图谱）、`file_enrich`（UHT 反射 JSON）。

**全局 (Phase 3)：**

| 路径 | 用途 |
|---|---|
| `~/.hermes/manything/query_log.db` | 查询追踪数据库 |
| `~/.hermes/manything/aliases.sh` | 项目别名注册表 |
| `~/.hermes/manything/pending.jsonl` | 待处理查询日志缓冲 |

---

## 使用示例

以下是规范化的 SQL 模板。每条查询都遵循此模式。

### DISCOVER — 找到候选文件

```sql
SELECT f.path, rank FROM files_fts, files f
WHERE files_fts MATCH 'layout prepare'
  AND files_fts.rowid = f.id
  AND f.path NOT LIKE '%test%'
ORDER BY rank LIMIT 15;
```

### EXTRACT — 探查文件结构

```sql
SELECT depth_level, start_offset,
       length(block_content) AS bytes,
       length(block_content_full) AS full_bytes,
       substr(block_content, 1, 100) AS preview
FROM v_enriched
WHERE file_path = 'src/layout.ts'
  AND depth_level <= 1
ORDER BY depth_level, start_offset;
```

### EXTRACT_BLOCK — 终端提取

```sql
SELECT block_content_full FROM v_enriched
WHERE file_path = 'src/layout.ts'
  AND block_content LIKE '%function layout%'
  AND depth_level = 1
ORDER BY start_offset LIMIT 1;
```

> **按语言的深度层级：** 花括号语言（JS、TS、Go、Rust、Java、C++、C#）— 函数体在 `depth=1`。缩进语言（Python、Ruby、YAML）— 签名在 `depth=1`，函数体在 `depth=2`。

### 实用工具 — 项目一览

```sql
SELECT ext, COUNT(*) AS n FROM files
GROUP BY ext ORDER BY n DESC;
```

更高级的用法（依赖追踪、追踪复用、符号搜索），参见[富化](#富化)和[查询追踪](#查询追踪)。

---

## 富化

Phase 1 给你 FTS5 搜索。Phase 2 添加结构——深度分段块、已解析的依赖关系和原始引用字符串——让你无需读取整个文件即可进行有界提取。

### 通用工作流（所有语言）

```bash
python3 scripts/phase2/enrich_depth_segments.py /path/to/project --batch 500
python3 scripts/phase2/enrich_file_refs.py       /path/to/project --batch 500
python3 scripts/phase2/flatten_file_deps.py      /path/to/project
python3 scripts/phase2/create_enriched_view.py   /path/to/project
```

这会添加 `v_enriched`、`enrich_file_deps`、`enrich_file_refs` 和 `enrich_depth_segments`。`v_enriched` 视图支持按深度层级提取代码块：

```sql
-- 提取 depth=1 处的函数体（花括号语言）
SELECT block_content_full FROM v_enriched
WHERE file_path = 'src/parser.ts'
  AND block_content LIKE '%function parseExpr%'
  AND depth_level = 1
ORDER BY start_offset LIMIT 1;
```

### 额外的富化脚本

| 脚本 | 添加内容 | 适用范围 |
|---|---|---|
| `enrich_cymbal.py` | 符号定义（类、函数、方法） | Python、Go、JS，需 `cymbal` CLI |
| `enrich_graphify.py` | AST/文档图谱节点 + 边 | 仅 Python + Markdown |
| `uht_enrich.py` | Unreal Header Tool 反射元数据 | 含 UHT 输出的 UE 构建 |
| `enrich_java_build.py` | Java import 解析 | Java 项目 |

在 Windows 上，`scripts/phase2/run_phase2_universal_windows.bat` 可一键运行全部 4 个通用步骤。Linux/WSL/macOS 上直接运行 Python 脚本。

完整文档：[Phase 2 富化指南](references/phase2/enrich-covercheck-workflow.md)

---

## 查询追踪

Phase 3 包装器拦截到 `/manything/` 数据库的每一次 `sqlite3` 调用并将其记录。过去的查询变得可检索——Agent 可以搜索之前运行过的查询，复用已验证的模式。

### 安装包装器

```bash
python3 scripts/phase3/install.py
```

这会在 `~/.local/bin/` 放置一个 `sqlite3` 包装器，拦截 `/manything/<project>/source.db` 和 `:trace`。用 `which sqlite3` 验证——它应指向 `~/.local/bin/sqlite3`。确保 `~/.local/bin` 在 `PATH` 中排在 `/usr/bin` 之前。

### 注册项目

```bash
echo 'MANYTHING_myproject="/path/to/project"' >> ~/.hermes/manything/aliases.sh
```

### 通过虚拟路径查询

```bash
sqlite3 /manything/myproject/source.db "SELECT COUNT(*) FROM files;"
```

### 搜索历史查询

```bash
# :trace 是由 Phase 3 包装器拦截的虚拟路径
sqlite3 :trace "
SELECT id, project, tag, substr(sql_text, 1, 120) FROM query_trace
WHERE project = 'myproject'
ORDER BY id DESC LIMIT 10;"
```

### 标记有用的查询模式

```sql
INSERT INTO query_notes (log_id, note, tag, created_at)
VALUES (42, '项目总览入口查询', 'useful_pattern', strftime('%s','now'));
```

被标记的查询会随时间累积——未来的会话可以通过 `SELECT * FROM query_trace WHERE tag IS NOT NULL` 发现已验证的模式，无需重复探索。

完整架构：[Phase 3 设计原理](references/phase3/phase3-design-rationale.md)

---

## 工作原理

SQL-ManyThing 不是把整个文件丢给 LLM，而是将代码搜索视为 A\* 探索：找到正确的文件，只提取证据，从最少的信息中给出答案。

### 搜索循环

```
主流 RAG：              SQL-ManyThing：
──────────────          ─────────────────
嵌入整个文件      →    FTS5 排序候选
检索分块          →    substr() 提取证据
堆满上下文        →    从证据中回答
碰运气            →    用 SQL 验证
```

底层是信息状态空间树上的 A\* 搜索（`g(n)` = 已消耗成本，`h(n)` = 估计剩余成本，`operator` = 一条 SQL 查询，`goal` = 证据充分的答案）。四条规范化模板——DISCOVER → EXTRACT → EXTRACT_BLOCK——将这个循环编码为可复用的 SQL 模式。

**先缩小范围。再提取。从证据中回答。**

### 设计原则

- **SQLite 优先。** 用 SQL 查询一切。一个文件，完全可检查。
- **一次构建，永久复用。** 索引成本只付一次；查询免费。
- **追踪行为，而非仅追踪答案。** 每次会话都为下一次留下可导航的面包屑。
- **永不读取整个文件。** 有界的 `substr()` 在不膨胀上下文的前提下给出证据。
- **配置文件策略优于 `.gitignore` 假设。** 显式控制索引内容。
- **默认与项目无关。** 特定领域的经验放在 `references/`，不在核心。

### 为什么用脚本而非统一 CLI

每个脚本都是一个稳定的入口点：`python3 scripts/phase1/manything_build_db.py ...` 让 token 位置在多次会话间保持可预测——这对于 Agent 驱动的工作流至关重要，因为命令字符串需要从查询追踪中原样复现。详见 [Phase 3 设计原理](references/phase3/phase3-design-rationale.md)。

---

## 性能

完整的 Unreal Engine 5.8 安装——本地索引、本地查询：

```
89,203 个文件被索引
~3.0 GB 单个 SQLite 数据库
全文搜索：亚秒级
UHT 反射符号：4,455 个类 · 3,247 个结构体 · 1,590 个枚举 · 8,902 个函数
```

这是压力测试。这个框架适用于任何有文件的项目：JS/TS 库、Python 工具、Java 项目、monorepo、生成代码、构建产物——指向哪里就能索引哪里。

> **WSL 注意：** 在 Windows 宿主的仓库上 DrvFS 查询可能慢 30 倍。将数据库复制到 `~/.hermes/manything/` 以获得亚秒级性能。参见 [DrvFS 性能](references/drvfs-performance.md)。

---

## 对比

|  | grep | LSP | Cloud RAG | **SQL-ManyThing** |
|---|---|---|---|---|
| **离线** | ✅ | ✅ | ❌ 云依赖 | **✅** |
| **亚秒级搜索** | ❌ O(n) | ✅ 精准 | ✅ + 延迟 | **✅ FTS5** |
| **有界提取** | ❌ 完整行 | ❌ | ❌ 分块 | **✅ substr()** |
| **查询记忆** | ❌ | ❌ | ❌ | **✅ 追踪日志** |
| **可审计结果** | ✅ | ❌ | ❌ | **✅ 纯 SQL** |
| **自托管索引** | N/A | ✅ 自动 | ❌ | **✅ 本地 SQLite** |

---

## Unreal Engine

UE 是本项目的主要压力测试目标。工作流与通用 Phase 1 + Phase 2 相同——UE 只是规模大，因此提供了批处理文件在 Windows 侧运行（避免 WSL 的 DrvFS 写入开销）。

### Phase 1 — 使用 UE 配置索引

```bash
# 或在 Windows 上使用 templates/run_phase1_unreal_windows.bat
python3 scripts/phase1/manything_build_db.py /path/to/Engine \
  --gitignore /path/to/Engine/.gitignore \
  --profile unreal-installed-core
```

`unreal-installed-core` 配置文件过滤扩展名（`.h,.cpp,.cs,.usf,.ush,.hlsl,.py,.ini,.uplugin`）并跳过高噪音路径（`Source/ThirdParty/`、`Content/`、`Platforms/`、`ScriptModules/`）。结果：约 89K 文件，约 3 GB。

### Phase 2 — 通用富化（已在 89K 文件上通过压力测试）

```bash
# 或在 Windows 上使用 scripts/phase2/run_phase2_universal_windows.bat
python3 scripts/phase2/enrich_depth_segments.py /path/to/Engine --batch 500
python3 scripts/phase2/enrich_file_refs.py       /path/to/Engine --batch 500
python3 scripts/phase2/flatten_file_deps.py      /path/to/Engine
python3 scripts/phase2/create_enriched_view.py   /path/to/Engine
```

UE shader 文件（`.usf`、`.ush`、`.hlsl`）是 C 风格的花括号语言，可与通用深度段解析器配合使用。完整运行产生 5.2M 个分段，数据库增长 +394 MB。

### Phase 2 — UHT 富化（可选）

仅适用于有 UHT 生成头文件的安装构建：

```bash
python3 scripts/phase2/uht_enrich.py \
  --db /path/to/Engine/.srcidx/source.db \
  --uht-dir /path/to/Engine/Intermediate/Build/Win64/UnrealEditor/Inc \
  --source-prefix Engine/ --batch 500
```

UE 相关文档：

- [安装构建索引](references/unreal/installed-build-indexing.md) — 索引策略和过滤配置
- [UE58 完整运行](references/unreal/ue58-full-phase123-run.md) — Phase 1–3 端到端结果及耗时
- [UHT 生成文件](references/phase2/ue-uht-generated-files.md) — 反射元数据结构

---

## Windows / WSL 注意事项

- **Phase 1 索引：** 尽可能使用 Windows Python 运行——WSL 的 DrvFS 写入较慢。WSL 可以正常查询生成的数据库。
- **查询性能：** 将 `.srcidx/source.db` 复制到原生 ext4 文件系统以获得亚秒级查询。参见 [DrvFS 性能](references/drvfs-performance.md)。
- **包装器：** `scripts/phase3/install.py` 跨平台工作（Windows `.cmd` 包装器，Linux/WSL shell 包装器）。
- **模板：** `templates/run_phase1_unreal_windows.bat` — Windows 上 UE 索引的快速启动批处理文件。

---

## 参考资料

参考文档按阶段和领域组织：

| 领域 | 核心文档 |
|---|---|
| **Phase 1** | ⭐ [Phase 1 安装](references/phase1/phase1-setup.md) · [Gitignore 枚举](references/phase1/gitignore-enumeration.md) |
| **Phase 2** | ⭐ [富化覆盖工作流](references/phase2/enrich-covercheck-workflow.md) · [Cymbal](references/phase2/enrich-cymbal.md) · [Graphify](references/phase2/enrich-graphify.md) · [Java](references/phase2/enrich-java-build.md) · [UHT](references/phase2/ue-uht-generated-files.md) |
| **Phase 3** | ⭐ [设计原理](references/phase3/phase3-design-rationale.md) · [导入器解析](references/phase3/importer-parsing.md) |
| **Unreal** | [安装构建索引](references/unreal/installed-build-indexing.md) · [UE58 完整运行](references/unreal/ue58-full-phase123-run.md) · [索引配置](references/unreal/unreal-installed-indexing-profiles.md) |
| **平台** | [WSL/Windows 冒烟测试](references/platforms/wsl-windows-phase123-smoke.md) |
| **设计** | [SQL Is Many Things](references/design/sql-is-many-things.md) · [数据库维护](references/db-maintenance.md) |
| **元信息** | [Agent 查询循环经验](references/agent-query-loop-lessons.md) · [公开示例](references/public-examples.md) · [第三方归属](references/third-party-attribution.md) |

完整目录：[references/INDEX.md](references/INDEX.md)

---

## 许可证

MIT
