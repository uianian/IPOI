# 专家模式 PDF 解析服务 — 接口封装设计

> 负责人：吴倩倩（pdf_parsing 模块）
> 对齐文档：`dataset/interfaces.md` v3.0（第 6 节 PDF 解析 — 专家模式）
> 修订：v4 — 机房端口仅 9100–9200；不再以胡禹成 `ipo-risk`/8080 为主后端网关；前端直连本服务
> 状态：P0 契约桩已落地（9100）；内部组 / 真解析待 GPU 空闲；整体网关架构待团队重调

---

## 0. 本轮确定的口径（v3）

| 项 | 结论 | 影响 |
|----|------|------|
| 返回给前端的正文 | **直接用 `preview.md`**（清洗后） | 只做一层轻量清洗，不二次导出 |
| 返回给前端的统计 | **`parse_summary.json` 原样** + 契约 `ParseStats` 五字段 | `/result` 含 `parseSummary` |
| `full_parse.json` | **不返回前端** | 后续 `/internal` |
| 图片 | **解析时 `--no-figures`**；历史样本清洗掉 `![figure](...)` | 不传图片 |
| QA 报告 | **不做** | 无 Pass2 |
| GPU 分片（真解析时） | `--gpus auto` + `--page-workers 2` | 不指定具体卡 |
| 竖表旋转 | **`--rotate-mode none`，关闭 `--rotate-fallback`** | 不做竖表检测 |
| `textChunkCount` | **正文块数** = `categories.text + categories.title` | 已确认 |
| 前端 markdown | **开 raw HTML**（`rehype-raw`） | 保留 HTML 表格 |
| `min_free_mib` | **先不动**（默认 20000） | 真解析前再测 |
| 单 shard 崩溃 | **整任务失败** | 不缺页降级 |
| 当前落地范围 | **只做契约组**；无 GPU 时用现有 `output/samples_batch` 结果 | P0 桩服务 |
| 对外端口 | **仅 9100–9200**；默认 9100；前端直连 | 不作 8080/`ipo-risk` 网关依赖 |

---

## 1. 现状与硬约束

设计必须迁就的既有事实：

| 事实 | 数据 | 对接口的影响 |
|------|------|-------------|
| 解析是 GPU 重任务 | 翰思艾泰 704 页，5 卡 × 2 分片（=10 分片），墙钟 41 min | 必须异步任务化；进度必须细粒度；必须有缓存复用 |
| 解析环境独立 | 解析用 `infinity_parser` env（torch/transformers/qwen_vl_utils）；与 Agent/检索等其它 env 不混装 | **独立进程**对外提供 HTTP；勿塞进他人仓库进程 |
| 机房端口白名单 | 三台服务器防火墙仅放行 **9100–9200** | 凡需对外起服务，端口必须落在该区间；**禁止**再规划 8080/8100/5432/6379/5173 等作为项目对外端口 |
| 产物是文件不是内存对象 | `preview.md` 1.2–1.5 MB、`full_parse.json` 2.1–2.6 MB | 结果接口要 gzip；下游 retrieval 直接读文件路径 |
| 现有 CLI 只在结束时落盘 | `pdf_parser_pro.py` 无进度回调 | 需加 `--progress-file`，否则前端 500ms 轮询只能看到 0 或 100 |
| **`--gpus auto` 当前必然失败** | `free_gpu_ids()` 默认门槛 20000 MiB；实测 8 张 3090 每张仅剩 0.3–4.3 GB 空闲 | **落地阻塞项**，见 §9.2 |

### 1.1 服务默认参数（固化，来源 `README.md`）

服务端不暴露这些参数给前端，全部固化：

| 参数 | 取值 | 依据 |
|------|------|------|
| 解析入口 | `parse_pdf_sharded`（分片路径） | `page_workers=2` 恒 > 1，永远走分片 |
| `--gpus` | `auto` | 本轮确定，不绑定具体卡 |
| `--page-workers` | `2` | 本轮确定 |
| `--min-free-mib` | `20000`（先不动） | 当前无空闲卡，真解析前再实测 |
| `--dpi` | `300` | README 默认；bbox 坐标系依赖它 |
| `--batch-size` | `2` | README 分片示例用值 |
| `--max-new-tokens` | `16384` | README 默认 |
| `--rotate-mode` | **`none`** | 本轮确定：不做竖表检测 |
| `--rotate-fallback` | **关闭** | 与 rotate-mode=none 一致 |
| `--no-figures` | **开启** | 不提取图片 |
| `--no-risk-chunks` | 关闭（仍产出 `risk_chunks.json`） | 供 RAG，不返前端 |
| Pass2 QA | **跳过** | 本轮确定 |

### 1.2 `--no-figures` 的确切效果

**不提取图片 ≠ 不识别图表元素**。`save_figures=False` 只是跳过 `save_figure_crops()` 的裁剪落盘，模型仍然会输出 `category: "figure"` 的布局元素。因此：

- `parse_summary.json` 的 `categories.figure` 依然准确（翰思艾泰 47 个），`chartCount` 可正常统计
- `full_parse.json` 里 figure 元素的 `bbox` 依然保留，证据高亮不受影响
- 元素上**不再有** `image_path` 字段 → `element_to_preview_md()` 走 else 分支，preview.md 里输出占位符 `> 🖼️ *[图片区域 — 未提取 OCR 文本]*`，而不是 `![figure](figures/p0144_fig001.png)`

对照实测：现有翰思艾泰产物是带图跑的，`preview.md` 里有 47 处 `![figure](...)` 引用，占位符 0 处；关掉后应为 0 处引用、47 处占位符。

- 不产出 `figures/` 目录
- E6 证据截图接口**不受影响**：它是从 `source.pdf` 按 300 DPI 重渲染再裁剪，不依赖 `figures/`

---

## 2. 总体架构与端口规划

> **架构口径（v4）**：胡禹成持有的 `ipo-risk` / 原 8080 网关 **不是** 当前主后端入口，团队后续会整体重调。本模块 **不以反代到 8080 为前提**；前端现阶段 **直连** 专家解析服务。任何新起的 HTTP 服务（本模块或其它模块）对外端口必须落在 **9100–9200**。

```
浏览器 / 前端
  │  expert base URL → http://<server>:9100
  ▼
:9100  专家模式解析服务（本模块，env=infinity_parser）
  ├── /api/v1/health
  ├── /api/v1/parse/expert/*     契约组（前端）
  ├── /health 、/capacity        运维
  └── （后续）/internal/parse/*  内部组
         │  服务主进程不常驻模型（纯 CPU 调度）
         ├── 任务队列（单 worker）
         ├── ProcessPoolExecutor
         │     └── _page_shard_worker × (N卡 × 2)  ← 真解析时才加载模型
         └── .runtime/tasks/{taskId}/ 产物落盘
                   │
                   └──▶ retrieval 建索引（读本地路径；可另开 9101–9200 服务）
```

**一个有利的副作用**：因为 `page_workers=2` 恒大于 1，`process_one()` 里 `use_shard` 永远为 `True`，走 `parse_pdf_sharded` 分支——该分支不要求主进程持有 `model/processor`，模型只在各 shard 子进程内加载。所以 **9100 服务进程是纯 CPU 的轻量进程**，不常驻显存，重启代价极低。

### 端口分配

> **机房硬约束**：防火墙仅放行 **9100–9200**。详见 `README.md` §7.1。

| 端口 | 服务 | 环境 | 归属 | 状态 |
|------|------|------|------|------|
| **9100** | **expert-parse-service** | **`infinity_parser`** | **本模块** | **默认对外端口** |
| **9101–9200** | 冲突备用 / 其它业务服务 | 各自 env | 团队共用 | 机房统一开放；新服务从此段选 |
| ~~8080~~ | ~~原 ipo-risk 网关~~ | — | 胡禹成 | **不作主网关；勿再按此规划** |
| ~~8100 / 8101~~ | ~~早期设计草稿~~ | — | — | **已作废（不在放行段）** |
| ~~5432 / 6379 / 5173~~ | ~~PG / Redis / 前端 dev~~ | — | — | **不作为本项目对外服务端口规划** |

**当前联调方式**：前端配置 `http://<server>:9100`，本服务自开 CORS（`allow_origin_regex`），路径与 `interfaces.md` 契约一致。

**后续若重做统一网关**：新网关进程本身也必须监听 **9100–9200** 内某端口，再反代到本机其它同段服务；**不要**再假设 8080。

---

## 3. 任务目录与状态机

### 3.1 目录布局

```
pdf_parsing/.runtime/
├── tasks/{taskId}/
│   ├── meta.json            # 任务元信息
│   ├── source.pdf           # 上传原件（证据截图/重跑要用）
│   ├── progress.json        # 聚合进度，服务写
│   ├── run.log              # 子进程 stdout/stderr
│   ├── parse/               # 解析器原样输出
│   │   ├── full_parse.json      → 内部用，不返前端
│   │   ├── preview.md           → 清洗后返前端
│   │   ├── parse_summary.json   → 返前端
│   │   ├── risk_chunks.json     → 内部用（RAG）
│   │   └── _shard*/progress.json# 分片进度，解析器写
│   └── export/
│       ├── content.md       # preview.md 清洗后的副本
│       └── result.json      # /result 完整响应体，生成一次后只读
└── cache/{pdfSha256} -> ../tasks/{taskId}   # 内容寻址软链，命中即秒回
```

相比 v1 删除：`figures/`（不提图）、`qa_report.json` / `.md`（不做 QA）、`stats.json`（合并进 result.json）。

`meta.json` 字段：`taskId` / `clientProjectId` / `ticker` / `fileName` / `isBiotech` / `pdfSha256` / `pageCount` / `createdAt` / `startedAt` / `finishedAt` / `params`（实际生效的 gpuIds、shardCount、batchSize 等）/ `reusedFrom`（缓存命中时指向源 taskId）。

`taskId` 格式：`task_expert_{YYYYMMDD}_{6位序号}`，与契约示例 `task_quick_20260722_001` 同风格。

### 3.2 内部状态机

```
QUEUED ─▶ PREPARING ─▶ RENDERING ─▶ PARSING ─▶ MERGING ─▶ EXPORTING ─▶ READY
   │                                                                    
   └─────────────────────── FAILED / CANCELLED ◀───────────────────────┘
```

进度百分比按阶段切段，保证前端进度条单调不回退：

| 内部阶段 | progress | 推进依据 |
|----------|---------|---------|
| `QUEUED` | 0–1 | 排队中恒为 1 |
| `PREPARING` | 1–3 | 落盘 + sha256 + 页数探测 + GPU 检测 |
| `RENDERING` | 3–8 | 各 shard 渲染完成数 |
| `PARSING` | 8–90 | **Σ shard done / Σ shard total** |
| `MERGING` | 90–96 | 分片 full_parse 合并 + preview 重建 |
| `EXPORTING` | 96–99 | 清洗 content.md、生成 result.json |
| `READY` | 100 | result.json 就绪 |

（v1 的 `QA` 阶段已删除，`PARSING` 区间相应扩到 90。）

**对外只暴露契约允许的两个 stage**：`READY`（progress=100）与 `PARSING`（其余全部）。内部阶段放 `stageDetail`，前端可忽略也可用来做更好看的文案。

---

## 4. 接口清单

分两组：**契约组**（前端消费，严格遵守 `interfaces.md`）与**内部组**（Agent / RAG / 报告模块消费，前缀 `/internal`，避开 `/result` 的"禁止返回 chunk JSON、原始表格结构"约束）。

| # | 组 | 方法 | 路径（对外契约路径） | 功能边界 |
|---|-----|------|------|---------|
| E1 | 契约 | POST | `/api/v1/parse/expert/start` | 接收 PDF，建任务，入队，立刻返回 taskId |
| E2 | 契约 | GET | `/api/v1/parse/expert/tasks/{taskId}/progress` | 轻量轮询，只读 progress.json |
| E3 | 契约 | GET | `/api/v1/parse/expert/tasks/{taskId}/result` | preview.md + parse_summary.json + ParseStats |
| E3b | 契约 | GET | `/api/v1/parse/expert/tasks/{taskId}/result/content.md` | 同上正文的 `text/markdown` 版，逃生口 |
| E4 | 内部 | GET | `/internal/parse/tasks/{taskId}/artifacts` | 返回服务器本地产物**路径**，供 retrieval 建索引 |
| E5 | 内部 | GET | `/internal/parse/tasks/{taskId}/pages/{page}` | 页级 elements（bbox/category/text），供证据高亮 |
| E6 | 内部 | GET | `/internal/parse/tasks/{taskId}/evidence` | 按 page+bbox 从 source.pdf 裁图返回 PNG |
| E7 | 内部 | POST | `/internal/parse/tasks/{taskId}/reparse` | 定向重跑指定页并合并回全书（可选，见 §5） |
| E8 | 运维 | GET | `/health` | 存活 + 版本 + 模型路径可达 |
| E9 | 运维 | GET | `/capacity` | GPU 空闲、队列长度、可否接单 |
| E10 | 运维 | DELETE | `/internal/parse/tasks/{taskId}` | 清理任务目录（缓存源任务拒删） |
| E11 | 运维 | GET | `/internal/parse/tasks` | 任务列表，供运维页与批量报告浏览 |

v1 的「E7 QA 报告」接口已删除。

---

## 5. 接口详细定义

### E1 `POST /api/v1/parse/expert/start`

**边界**：只做"接收 + 校验 + 建任务 + 入队"，**不阻塞等待解析**，2 秒内返回。

请求 `multipart/form-data`：

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `file` | 是 | binary | PDF，≤ 100 MB，magic number 必须是 `%PDF-` |
| `ticker` | 是 | string | 如 `9988.HK` / `02097` |
| `clientProjectId` | 是 | string | 前端项目 ID `proj-xxx` |
| `fileName` | 是 | string | 原始文件名 |
| `isBiotech` | 是 | `"true"/"false"` | 存入 meta.json，供 Agent 使用 |
| `maxPages` | 否 | int | ❓建议新增：只解析前 N 页，演示/联调用 |
| `forceReparse` | 否 | bool | 否则命中 sha256 缓存直接复用 |

解析参数**一律不接受前端传入**，服务端按 §1.1 固化。

响应 **202**：

```json
{
  "success": true,
  "data": {
    "taskId": "task_expert_20260726_000012",
    "status": "parsing",
    "cached": false,
    "queuePosition": 0,
    "estimatedSeconds": 2470,
    "shardCount": 10
  }
}
```

`cached` / `queuePosition` / `estimatedSeconds` / `shardCount` 是契约外附加字段，前端可忽略；建议用 `cached: true` 跳过"预计数十分钟"的提示文案。

缓存命中时同样返回 202、同样走一次 progress 轮询（立刻读到 100），保持前端状态机唯一。

错误：`INVALID_FILE`(400)、`FILE_TOO_LARGE`(413)、`MISSING_FIELD`(400)、`QUEUE_FULL`(429)、`NO_GPU_CAPACITY`(503)。

### E2 `GET /api/v1/parse/expert/tasks/{taskId}/progress`

**边界**：**零计算**，只 `json.load(progress.json)` 并做 stage 映射。前端 500ms 轮询 × 40 分钟 ≈ 4800 次请求，任何一次都不能触碰 GPU 或大文件。

```json
{
  "success": true,
  "data": {
    "progress": 67,
    "stage": "PARSING",
    "stageDetail": "PARSING",
    "pagesDone": 470,
    "pagesTotal": 704,
    "shardCount": 10,
    "etaSeconds": 821,
    "updatedAt": "2026-07-26T15:31:02Z"
  }
}
```

失败态约定 `stage: "FAILED"` + `error`。❓这是对契约的扩展，需前端确认容错分支；若前端不愿改，退化为 `/result` 返回 500 + `PARSE_FAILED`。

任务不存在 → 404 `TASK_NOT_FOUND`。

### E3 `GET /api/v1/parse/expert/tasks/{taskId}/result`

**边界**：只在 `READY` 时返回；直接吐预生成的 `export/result.json`，不做实时计算。

```json
{
  "success": true,
  "data": {
    "taskId": "task_expert_20260726_000012",
    "projectId": "proj-a1b2c3d4",
    "mode": "expert",
    "status": "completed",
    "stats": {
      "totalPages": 704,
      "parsedPages": 704,
      "chartCount": 47,
      "tableCount": 263,
      "textChunkCount": 4536
    },
    "markdown": "## 第 1 页\n\n翰思艾泰生物醫藥科技（武漢）股份有限公司\n...",
    "parseSummary": {
      "total_pages": 704,
      "total_elements": 6490,
      "categories": { "text": 3618, "title": 918, "header": 795, "footer": 700,
                      "table": 263, "table_footnote": 126, "figure": 47,
                      "table_caption": 14, "figure_caption": 6, "page_footnote": 3 },
      "failed_pages": [],
      "empty_pages": [],
      "html_tables": 263,
      "markdown_tables": 0,
      "table_structure_confidence_pages": { "high": 103, "medium": 70, "low": 25 }
    },
    "timing": { "elapsedSec": 2471.4, "secPerPage": 3.51, "shardCount": 10 },
    "completedAt": "2026-07-24T17:46:02Z"
  }
}
```

- `markdown` = `preview.md` 清洗后的内容（见 §7）
- `parseSummary` = `parse_summary.json` **原样**（下划线命名保持不变，避免两边转换出错）
- **不含** `images`（契约禁止，且本轮已从源头不提图）
- **不含** `elements` / `full_parse` / `risk_chunks` / `pdfUrl`（契约禁止）
- `companyInfo` 不返（前端走 `company-lookup.json`）

未完成 → 404 `PARSE_NOT_COMPLETED`；失败 → 200 且 `status: "failed"` + `error`（契约 ParseResult 已定义 failed 态）。

**响应体积**：markdown 1.5 MB + JSON 转义 ≈ 2.5 MB。必须开 `GZipMiddleware(minimum_size=1024)`，压缩后约 400 KB。若将来有同段反代，透传 body 与 `Content-Encoding`，不要二次解压再压缩。

### E3b `GET .../result/content.md`

`Content-Type: text/markdown; charset=utf-8`，直接返回正文，支持 `?pageFrom=&pageTo=` 分段。给前端在"整包 JSON 太大导致卡顿"时用。

### E4 `GET /internal/parse/tasks/{taskId}/artifacts`

给 retrieval 建索引用。retrieval 与解析服务在同一台机器，传路径比传内容高效得多。

```json
{
  "success": true,
  "data": {
    "taskId": "...",
    "fullParsePath": "/nfs/users/wuqianqian/IPOI/pdf_parsing/.runtime/tasks/xxx/parse/full_parse.json",
    "riskChunksPath": ".../risk_chunks.json",
    "previewMdPath": ".../preview.md",
    "sourcePdfPath": ".../source.pdf",
    "pdfSha256": "...",
    "ticker": "02097",
    "isBiotech": false,
    "renderDpi": 300
  }
}
```

（v1 的 `figuresDir` / `qaReportPath` 已删除。）

对接命令即现成的：

```bash
python scripts/build_index_from_parse.py --parse {fullParsePath} \
  --company-name ... --stock-code {ticker} --doc-id {clientProjectId}
```

### E5 `GET /internal/parse/tasks/{taskId}/pages/{page}`

```json
{ "success": true,
  "data": { "page": 123, "parseStatus": "ok", "rotationApplied": 90,
            "tableStructureConfidence": "high",
            "renderDpi": 300, "pageWidth": 2480, "pageHeight": 3508,
            "elements": [ { "bbox": [372,1028,2106,2067], "category": "table", "text": "<table>..." } ] } }
```

`renderDpi` / `pageWidth` / `pageHeight` 必须返回——前端 PDF viewer 用 PDF point（72 dpi）坐标系，而 bbox 是 300 DPI 像素系，换算因子 `72/300 = 0.24`。不给尺寸前端没法对齐高亮框，这正是 skill 里"bbox 与高亮对不齐"的根因。

支持 `?category=table` 过滤、`?pages=120-125` 批量取。

### E6 `GET /internal/parse/tasks/{taskId}/evidence?page=123&bbox=372,1028,2106,2067&padding=20`

返回 `image/png`：从 `source.pdf` 按 300 DPI 重渲染该页并裁剪。**因为已关掉 `--no-figures`，这是唯一的取图途径**，报告模块的证据截图完全依赖它。加 LRU 页图缓存（单页渲染约 0.3 s）。

### E7 `POST /internal/parse/tasks/{taskId}/reparse`（可选，优先级最低）

Body `{ "pages": [16,21], "rotateMode": "auto", "rotateFallback": true }`，串到队列，跑 `pdf_parser_pro --pages` → `merge_parse_pages.py --prefer-higher-table-score --backup` 合回，再重生成 export/。

**注意**：v1 里这个接口的页码来源是 QA 报告的 `reparse_pages`。现在不做 QA，页码只能由人工或下游 Agent 指定。若短期没有调用方，可暂不实现。

### E8 `GET /health`

```json
{ "success": true, "data": { "status": "healthy", "version": "2.0.0", "uptime": 12345,
   "model": "Infinity-Parser2-Flash", "modelPathExists": true, "torchCuda": true, "gpuCount": 8 } }
```

本服务自有 `/api/v1/health`；日后若有统一健康聚合，本服务不可达应标 `degraded` 而非整站 `down`。

### E9 `GET /capacity`

因为用 `--gpus auto`，这个接口从"参考信息"升级为**关键接口**——它直接决定 auto 检测会不会抛错。

```json
{ "success": true, "data": {
   "acceptingJobs": false, "running": 0, "queued": 0, "maxConcurrent": 1,
   "minFreeMiB": 20000,
   "gpus": [ {"index":0,"freeMiB":4370,"usable":false},
             {"index":4,"freeMiB":330,"usable":false} ],
   "usableGpuCount": 0,
   "plannedShardCount": 0,
   "reason": "no GPU with free memory >= 20000 MiB" } }
```

E1 在 `acceptingJobs=false` 时直接返回 503 `NO_GPU_CAPACITY`，**不要入队**——否则任务会卡在队列里假装在跑，直到子进程抛 `RuntimeError: 没有空闲显存 ≥20000MiB 的 GPU`。这是把 `resolve_gpu_ids()` 的硬失败提前到请求入口。

---

## 6. `parse_summary.json` → 契约 `ParseStats`

前端拿到 `parseSummary` 原文，但契约的五个字段仍需服务端算好：

| 契约字段 | 计算式 | 翰思艾泰实测 |
|---------|--------|------------|
| `totalPages` | `total_pages` | 704 |
| `parsedPages` | `total_pages - |failed_pages ∪ empty_pages|` | 704 |
| `chartCount` | `categories.figure` | 47 |
| `tableCount` | `categories.table` | 263 |
| `textChunkCount` | `categories.text + categories.title` | 4536 |

`header` / `footer` / `page_footnote` 不计入任何对外计数——它们是页眉页脚噪声。

❓`textChunkCount` 语义确认：按"正文语义块数"算（text+title=4536）。若前端想表达"RAG 入库块数"，应改用 `len(risk_chunks)`（约 1.2k）。两者差近 4 倍，展示含义完全不同，需要定死。

---

## 7. `preview.md` 清洗规则

本轮不再重写 markdown 生成逻辑，只在返回前做一层**幂等的轻量清洗**，产出 `export/content.md`：

| 规则 | 处理 | 原因 |
|------|------|------|
| 图片引用 `![figure](figures/...)` | 若出现，替换为 `> 图表 — 第 N 页（图像未随结果返回）` | 防御性：`--no-figures` 已从源头消除，但历史产物 / 参数误配时仍可能出现，绝不能让前端拿到指向服务器本地路径的碎图 |
| 占位符 `> 🖼️ *[图片区域 — 未提取 OCR 文本]*` | 原样保留 | 这是 `--no-figures` 下的正常输出 |
| 表格 `<!-- table html -->\n<table>...\n<!-- /table -->` | 原样保留 | 见下方 ❓ |
| 页锚点 | 默认不加；`?anchors=true` 时在每个 `## 第 N 页` 前插入 `<a id="page-N"></a>` | 前端若要精确跳页再开 |
| 其余内容 | 原样透传 | 不做加工 |

清洗必须幂等：重复执行结果不变，便于缓存复用时直接套用。

❓**前端 markdown 渲染器必须开启 raw HTML**（`react-markdown` 需 `rehype-raw`）。招股书表格大量使用 `colspan/rowspan`（翰思艾泰 263 张全是 HTML 表），转 GFM 表格会把结构全丢掉。`<!-- table html -->` 注释在标准 markdown 里不可见，可以保留不动。

---

## 8. 需要改动的代码

### 8.1 必改：`pdf_parser_pro.py` 加进度上报

```python
p.add_argument("--progress-file", default=None, help="周期性写入 {stage,done,total} 的 JSON 路径")
```

- `parse_pages_batch()` 增加 `progress_cb: Optional[Callable[[int, int], None]]`，每个 batch 结束调一次 `(done, total)`
- `parse_pdf()` 透传，并在渲染阶段先写 `{"stage":"RENDERING","done":0,"total":N}`
- 写文件用「临时文件 + `os.replace`」原子替换，避免轮询读到半截 JSON

### 8.2 必改：`batch_parse_samples.py`

1. `_page_shard_worker()` 的 payload 增加 `progress_file`，透传 `--progress-file {shard_out}/progress.json`
2. 新增 `--skip-qa`（当前只有 `--skip-pass1`，没有跳过 Pass2 的开关）

服务侧聚合进度：`glob(parse/_shard*/progress.json)` 求 `Σdone / Σtotal`。

**替代方案**：服务直接调用 `parse_pdf_sharded()` 而不走 `batch_parse_samples` 的 CLI，则 `--skip-qa` 可以不加——因为 QA 是在 `process_one()` 里调的，绕开 `process_one` 就自然跳过。这个方案耦合更低，**推荐**；`--skip-qa` 作为 CLI 侧的顺手补充。

### 8.3 新增文件

```
pdf_parsing/
├── service/                 # ✅ P0 已实现（契约组 + 桩模式）
│   ├── app.py               # FastAPI：/health /capacity + 契约路由
│   ├── config.py            # STUB_MODE、PARSE_DEFAULTS（rotate=none）
│   ├── routes_contract.py   # E1–E3b
│   ├── sample_catalog.py    # 扫描 samples_batch，sha/ticker/文件名匹配
│   ├── stub_runner.py       # 模拟进度并导出 result
│   ├── task_store.py
│   ├── preview_clean.py
│   └── schemas.py
├── scripts/start_expert_parse_service.sh
│   # 后续真解析再加：runner.py / routes_internal.py / capacity.py
```

启动脚本：

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /nfs/users/wuqianqian/IPOI/pdf_parsing
exec /nfs/users/wuqianqian/anaconda3/envs/infinity_parser/bin/uvicorn \
  service.app:app --host 0.0.0.0 --port 9100 --workers 1
```

`--workers 1` 是硬要求：队列状态在进程内存里，多 worker 会各自调度导致 GPU 抢占。

### 8.4 统一网关（暂缓）

~~原计划在 `agents/ipo`（8080）加 `parse_proxy` 反代。~~ **已取消作为前提**：`ipo-risk` 不是现行主网关，架构待重调。当前与后续默认均为 **前端 / 调用方直连 `:9100`**。若重做网关，其监听端口仍须落在 **9100–9200**，再用环境变量指向本服务（例如 `EXPERT_PARSE_BASE=http://127.0.0.1:9100`），multipart 须流式转发。

---

## 9. 缓存、容量与容错

### 9.1 内容寻址缓存（演示的生命线）

40 分钟的解析在答辩现场跑不了。上传时算 `sha256(pdf)`，命中 `.runtime/cache/{sha256}` 就建一个指向已有产物的新任务（新 taskId、新 clientProjectId，产物软链复用），progress 立刻 100。

**上线前必须预热**已解析的样本：

```
蜜雪集團 02097(558p)、翰思艾泰-B 03378(704p)、快手-W 01024、
伊登軟件 01147、建中建設 00589、德合集團 00368、小米 xiaomi
```

预热脚本读 `output/samples_batch/*/`，为每份 PDF 算 sha256、建 cache 软链、跑一遍 §7 清洗补齐 `export/`。

注意现有样本是**带图**跑出来的，preview.md 里有 47 处 `![figure](...)`——清洗规则第一条正是为它们准备的，预热后必须核对 content.md 里 `![figure]` 计数为 0。

### 9.2 GPU 容量（当前的头号落地阻塞）

`--gpus auto` 调 `free_gpu_ids(min_free_mib=20000)`，只收 **空闲显存 ≥ 20 GB** 的卡。实测 8 张 3090 的空闲量：

```
GPU0 4370  GPU1 4368  GPU2 4368  GPU3 4368
GPU4  330  GPU5 1942  GPU6  372  GPU7 1624   (MiB)
```

**一张都不满足**，`resolve_gpu_ids()` 会直接抛 `RuntimeError`。所以：

1. **实测 Infinity-Parser2-Flash 单进程峰值显存**（`batch_size=2`、`max_new_tokens=16384`、300 DPI），把 `min_free_mib` 下调到「峰值 × 1.2」。20000 是给一卡多进程留的保守值，单分片未必需要。
2. 注意 `page_workers=2` 意味着**同一张卡上跑 2 个模型进程**，门槛要按 2 份峰值算。
3. E9 `/capacity` 把这个判定前置到请求入口，避免任务入队后才炸。
4. 中期需要与集群其他使用者协调固定留卡。

### 9.3 分片数与 ETA

分片数 = `len(auto检测到的卡) × 2`，**每次任务可能不同**，ETA 不能写死。

由实测反推单分片速度：翰思艾泰 704 页 / 10 分片 = 70.4 页/分片，41 min ⇒ **约 35 s/页/分片**。

```
etaSeconds ≈ 60 (每分片模型加载) + ceil(totalPages / shardCount) × 35
```

对照：10 分片 → 约 2530 s（实测 2471 s，误差 2%）。若 auto 只检测到 2 张卡（4 分片）→ 约 6220 s（约 104 分钟）。**卡越少越慢是线性的**，前端提示文案要用接口返回的 `estimatedSeconds`，不能写死"约 40 分钟"。

运行中按已完成页数用 EWMA 修正 ETA。

### 9.4 并发

- `maxConcurrent = 1`（GPU 现状下唯一安全值），可配
- 队列 FIFO，`QUEUE_FULL` 阈值默认 5
- 服务重启后扫描 `tasks/`，把 `RUNNING` 的孤儿任务标 `FAILED`（`error.code=SERVICE_RESTARTED`），不自动续跑

### 9.5 超时与失败

| 情形 | 处理 |
|------|------|
| 子进程无输出 > 15 min | 判定 hang，kill 并标 FAILED |
| 单页 OOM | 解析器已有 `parse_status=failed` 逐页降级，不整任务失败 |
| 某个 shard 整体崩溃 | `parse_pdf_sharded` 的 `as_completed` 会抛出 → 整任务 FAILED；❓是否要改成缺页降级完成，待定 |
| `failed_pages` 占比 > 10% | 任务仍标 `completed`，但在 `parseSummary.failed_pages` 里如实暴露 |
| 磁盘不足 | E1 预检 `source.pdf 大小 × 6` 的可用空间（v1 是 ×10，不提图后产物变小），不足直接 503 |

### 9.6 错误码表

| code | HTTP | 触发 |
|------|------|------|
| `INVALID_FILE` | 400 | 非 PDF / 损坏 / 0 页 |
| `MISSING_FIELD` | 400 | 缺 ticker / clientProjectId 等 |
| `FILE_TOO_LARGE` | 413 | > 100 MB |
| `TASK_NOT_FOUND` | 404 | taskId 不存在 |
| `PARSE_NOT_COMPLETED` | 404 | 契约指定，`/result` 未完成 |
| `QUEUE_FULL` | 429 | 队列已满 |
| `PARSE_FAILED` | 500 | 子进程非零退出 |
| `NO_GPU_CAPACITY` | 503 | auto 检测无可用卡 |
| `SERVICE_RESTARTED` | 500 | 孤儿任务 |

---

## 10. 落地阶段与验收

| 阶段 | 内容 | 交付判据 | 依赖 |
|------|------|---------|------|
| **P0 契约桩（当前）** | 9100 契约组 E1–E3b；匹配 `output/samples_batch` 现有产物；模拟进度；不接 GPU | 前端直连 9100 跑通上传→轮询→展示 | 无 |
| P1 显存实测 | 有空闲卡后再测峰值；`min_free_mib` 暂保持 20000 | `/capacity` 扫真卡 | 空闲卡窗口 |
| P2 真解析 | `--progress-file` + `parse_pdf_sharded`（rotate=none, no-figures, page_workers=2, gpus=auto） | 新 PDF 真跑 0→100 | P1 |
| ~~P3 8080 网关~~ | ~~ipo-risk 反代~~ | **取消**：架构待重调；直连 9100 | — |
| P4 内部接口 | E4–E6（若另起服务，端口仍在 9100–9200） | retrieval / 证据截图 | 后续 |
| P5 运维 | E9–E11 | 批量浏览 | 后续 |

P0 是关键路径：把"前端联调"和"GPU 调优"解耦，前端不用等 40 分钟任务跑完才能改一行 CSS。

### 冒烟脚本

```bash
BASE=http://127.0.0.1:9100
curl -s $BASE/health | jq
curl -s $BASE/capacity | jq '.data | {acceptingJobs, usableGpuCount, plannedShardCount}'

TASK=$(curl -s -X POST $BASE/api/v1/parse/expert/start \
  -F "file=@pdf/03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf" \
  -F "ticker=03378" -F "clientProjectId=proj-smoke01" \
  -F "fileName=翰思艾泰.pdf" -F "isBiotech=true" | jq -r .data.taskId)

watch -n1 "curl -s $BASE/api/v1/parse/expert/tasks/$TASK/progress | jq .data"

# 契约字段齐全性
curl -s $BASE/api/v1/parse/expert/tasks/$TASK/result | jq '.data | {stats, parseSummary}'
# 关键回归：正文里绝不能有图片引用
curl -s $BASE/api/v1/parse/expert/tasks/$TASK/result/content.md | grep -c '!\[figure\]'   # 必须为 0

curl -s $BASE/internal/parse/tasks/$TASK/artifacts | jq
curl -s "$BASE/internal/parse/tasks/$TASK/pages/144?category=figure" | jq '.data.elements[0].bbox'
curl -s "$BASE/internal/parse/tasks/$TASK/evidence?page=144&bbox=372,1028,2106,2067" -o /tmp/ev.png
```

---

## 11. 待确认清单

| # | 问题 | 影响面 | 建议 |
|---|------|--------|------|
| Q1 | `textChunkCount` | **已确认：正文块数**（text+title） |
| Q2 | 前端 markdown raw HTML | **已确认：开启** |
| Q3 | `/result` 扩展 `parseSummary` | **已确认：允许** |
| Q4 | `progress` 的 `stage: "FAILED"` | 接受（建议）；否则靠 `/result` 兜底 |
| Q5 | `maxPages` | 加，默认不限（演示用） |
| Q6 | 网关 vs 直连 | **已定：直连 9100**；原 8080/`ipo-risk` 网关不作主入口；新服务端口仅 9100–9200 |
| Q7 | `min_free_mib` | **先不动 20000**，有空闲卡再测 |
| Q8 | 单 shard 崩溃 | **已确认：整任务失败** |
| Q9 | `table_structure_confidence_pages` | 保留在 parseSummary 里 |
