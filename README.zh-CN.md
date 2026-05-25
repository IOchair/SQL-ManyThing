# SQL-ManyThing

**把任意源码树变成本地 SQLite 数据库。89,000 个文件，秒级全文检索。单文件。无服务器。无网络。**

SQL-ManyThing 为整个代码库构建 FTS5 trigram 索引，可选附加符号/图谱富化，并记录每一条查询——让 Agent 每次会话都比上次更聪明。

---

## 震撼测试

完整的 Unreal Engine 5.8 安装目录——本地索引，本地查询：

```
索引文件数：89,203
数据库大小：~3.0 GB，单个 SQLite 文件
全文检索速度：秒级
UHT 反射符号：4,455 个类 · 3,247 个结构体 · 1,590 个枚举 · 8,902 个函数
```

这是压力测试。框架本身适用于一切有文件的东西：JS/TS 库、Python 工具、Java 项目、Monorepo、生成代码、构建产物——指哪打哪。

---

## 为什么造这个

大多数 AI Agent 代码搜索至今还是 grep + cat：线性扫描、整文件读取、反复加载、token 预算爆炸。其他方案各有代价：

| | grep | LSP | Cloud RAG | **SQL-ManyThing** |
|---|---|---|---|---|
| **离线可用** | ✅ | ✅ | ❌ 需要网络 | **✅** |
| **查询速度** | O(n) 扫描 | O(1) 跳转 | 毫秒级 + 网络延迟 | **毫秒级本地 FTS5** |
| **Token 消耗** | 整文件读取 | 精确但范围窄 | 检索 + 上下文拼接 | **有界 `substr()`** |
| **可审计性** | ✅ | ❌ 黑盒 | ❌ 黑盒 | **✅ 纯 SQL 可追溯** |
| **语言无关** | ✅ | ❌ 绑定语言 | ✅ | **✅ 任意文件** |
| **自建索引** | ❌ | ✅ 自动 | ❌ 外部服务 | **✅ 本地 SQLite** |

任何索引都比 grep 强。SQLite FTS5 是在规模化场景下能跑起来的最简单那个。

---

## 核心思路

把代码搜索建模为 A* 搜索：

```
状态空间 = 文件 + 行 + 符号 + 图谱节点 + 查询历史
g(n)     = 已消耗的查询次数 / 工具调用次数 / token 数
h(n)     = 由排名、符号精度、图谱覆盖度、历史复用估算的剩余代价
操作符   = 一条 SQL 查询 或 一次有界源码提取
目标     = 用最少源码文本给出有证据支撑的答案
```

**先收窄，再提取，凭证据回答。**

这与主流 RAG 几乎相反：RAG 检索分块后填充上下文；这里是 FTS5 定位目标，`substr()` 提取证据，完整文件从不进入上下文窗口。

---

## 快速上手

### 第一阶段 — 构建 FTS5 索引

```bash
# 任意项目
python3 scripts/phase1/manything_build_db.py /path/to/project \
  --git --ext .ts,.tsx,.js,.jsx,.json,.md

# 普通目录 + .gitignore
python3 scripts/phase1/manything_build_db.py /path/to/project \
  --gitignore /path/to/project/.gitignore

# Unreal Engine 已安装构建
python3 scripts/phase1/manything_build_db.py /path/to/Engine \
  --gitignore /path/to/Engine/.gitignore \
  --profile unreal-installed-core
```

输出：`<project>/.srcidx/source.db`

### 第二阶段 — 富化（可选）

```bash
# 符号富化
python3 scripts/phase2/enrich_cymbal.py /path/to/project

# 图谱/文档富化
python3 scripts/phase2/enrich_graphify.py /path/to/project

# Unreal UHT 反射元数据
python3 scripts/phase2/uht_enrich.py \
  --db /path/to/Engine/.srcidx/source.db \
  --uht-dir /path/to/Engine/Intermediate/Build/Win64/UnrealEditor/Inc \
  --source-prefix Engine/ --batch 500
```

### 第三阶段 — 查询追踪

```bash
# 初始化追踪数据库
python3 scripts/phase3/manything_query_log.py init

# 安装 sqlite3 包装器
mkdir -p ~/.local/bin
cp scripts/phase3/sqlite3_wrapper.sh ~/.local/bin/sqlite3
cp scripts/phase3/SQL-ManyThing-query-log ~/.local/bin/SQL-ManyThing-query-log
chmod +x ~/.local/bin/sqlite3 ~/.local/bin/SQL-ManyThing-query-log
```

确保 `~/.local/bin` 在 `PATH` 中优先于 `/usr/bin`。

```bash
# 注册项目别名
echo 'MANYTHING_myproject="/path/to/project"' >> ~/.hermes/manything/aliases.sh

# 通过虚拟路径查询
sqlite3 /manything/myproject/source.db "SELECT COUNT(*) FROM files"

# 查看查询历史
SQL-ManyThing-query-log import
sqlite3 :trace "SELECT id, project, tag, substr(sql_text,1,120) FROM query_trace ORDER BY id DESC LIMIT 10"
```

---

## 构建产物

**每个项目：**
```
<project>/.srcidx/source.db
```

**数据库结构：**
```
files                   — 文件元数据 + 完整文本
files_fts               — 路径 + 内容的 FTS5 trigram 索引
file_enrich             — 每个文件的符号/领域富化 JSON
enrich_graphify_nodes   — AST/文档节点
enrich_graphify_edges   — 图谱/文档边
```

**全局（第三阶段）：**
```
~/.hermes/manything/query_log.db    — 查询追踪数据库
~/.hermes/manything/aliases.sh      — 项目别名
~/.hermes/manything/pending.jsonl   — 待写入查询日志缓冲
```

---

## 查询示例

**按内容找文件：**
```sql
SELECT path, rank FROM files_fts
WHERE files_fts MATCH 'layout prepare'
ORDER BY rank LIMIT 20;
```

**一眼看清项目结构：**
```sql
SELECT ext, COUNT(*) FROM files
GROUP BY ext ORDER BY COUNT(*) DESC;
```

**有界源码提取**（永远不读整个文件）：
```sql
SELECT instr(content, 'export function layout') FROM files WHERE path='src/layout.ts';
SELECT substr(content, 1200, 1600) FROM files WHERE path='src/layout.ts';
```

**跨富化表搜索符号：**
```sql
SELECT f.path,
       json_extract(s.value, '$.name') AS name,
       json_extract(s.value, '$.kind') AS kind
FROM file_enrich e
JOIN files f ON f.id = e.file_id,
     json_each(e.symbols) AS s
WHERE json_extract(s.value, '$.name') LIKE '%layout%'
LIMIT 50;
```

**把历史查询当 Agent 记忆复用：**
```sql
WITH intent(term) AS (
  VALUES ('files'), ('symbols'), ('graph'), ('README'), ('package'), ('src')
)
SELECT id, project, tag, note, substr(sql_text, 1, 180)
FROM query_trace
WHERE project = 'myproject'
  AND (tag IS NOT NULL OR EXISTS (
    SELECT 1 FROM intent WHERE lower(sql_text) LIKE '%' || lower(term) || '%'
  ))
ORDER BY tag IS NULL, id DESC LIMIT 12;
```

**给有价值的查询打标签：**
```sql
INSERT INTO query_notes (log_id, note, tag, created_at)
VALUES (42, '项目入口概览查询', 'useful_pattern', strftime('%s','now'));
```

---

## 复现路线（三步提示词）

按顺序执行这三个提示词，即可复现整个项目：

1. **FTS5 + trigram 全文索引**目标项目；过滤规则自行设计
2. **交互式查询数据库**，发现潜在富化表设计，编写批量富化脚本
3. **自动将 SQL 查询摄入追踪数据库**，让下次搜索前先探索历史查询路径

---

## 设计原则

- **SQLite 优先。** 一切用 SQL 查询。单文件，完全可审计。
- **一次构建，反复复用。** 索引成本只付一次，查询不再有代价。
- **追踪行为，不只追踪答案。** 每次会话为下一次留下可导航的路径。
- **永远不读整个文件。** 有界 `substr()` 能证明答案，就别把完整文件塞进上下文。
- **用 profile 策略代替 `.gitignore` 猜测。** 显式控制索引范围。
- **项目无关性是默认值。** Unreal 及其他项目的专项经验放在 `references/`，不进核心。

---

## 为什么是裸脚本，不是统一 CLI

每个脚本都是稳定入口：`python3 scripts/phase1/manything_build_db.py ...`

统一的 `manything build` 包装器会移动每条命令字符串里的每个 token 位置。Transformer 位置编码对偏移敏感，哪怕微小位移也会在后续 Agent 推理中引入噪声。保持裸脚本意味着：

- 各阶段 token 位置保持可预测
- Agent 写入查询追踪的命令可逐字复现
- 强迫 Agent 学习包装器约定的代价为零

第三阶段 sqlite3 包装器遵循同一原则：在二进制层拦截，从不修改进入 LLM 上下文的查询字符串。

---

## Windows / WSL 说明

对于 Windows 宿主的仓库，第一阶段索引尽量用 Windows Python 跑——WSL 通过 DrvFs 写入速度较慢。查询已有数据库用 WSL 没问题。

已提供模板：`templates/run_phase1_unreal_windows.bat`

---

## 参考文档

从这里开始：
```
.hermes/                — Hermes Agent 项目上下文
references/INDEX.md
scripts/INDEX.md
```

关键参考：
```
references/phase1/phase1-setup.md
references/phase1/gitignore-enumeration.md
references/phase2/enrich-cymbal.md
references/phase2/enrich-graphify.md
references/phase2/ue-uht-generated-files.md
references/phase3/phase3-design-rationale.md
references/unreal/unreal-installed-indexing-profiles.md
references/unreal/ue58-full-phase123-run.md
```

---

## License

MIT
