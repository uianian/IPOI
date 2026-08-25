# IPO Risk Analyzer

港股 IPO 智能风险分析前端。上传招股书 PDF，经专家模式解析后，由多 Agent（法务 / 财务 / 市场 / 总控）协作分析并生成可解释风险报告。

- **技术栈**：React 19、Vite 7、TypeScript、Tailwind CSS 4、Radix UI、wouter
- **IPOI 仓库路径**：`frontend/ipo-risk-analyzer/`（本目录整体迁入，内部路径不变）

---

## 迁入 IPOI 仓库

在 [IPOI](https://github.com/uianian/IPOI) monorepo 中，本前端位于：

```text
IPOI/
└── frontend/
    └── ipo-risk-analyzer/    ← 前端包根（pnpm、.env、vite.config.ts 均在此层）
        ├── client/
        ├── server/
        ├── package.json
        └── ...
```

```bash
cd IPOI/frontend/ipo-risk-analyzer
pnpm install
cp .env.example .env   # 配置 VITE_API_BASE_URL
pnpm dev
```

**路径约定**：`vite.config.ts` 使用 `import.meta.dirname`，迁入子目录后无需改 alias；`.env` 放在 `frontend/ipo-risk-analyzer/`，不要放在 IPOI 根目录。

**提交时注意**：勿提交 `node_modules/`、`dist/`、`.env`、`.env.local`；只提交 `.env.example`。`backup/` 为仓库内置演示样例，应一并提交。

---

## 环境要求

| 工具 | 版本建议 | 说明 |
|------|----------|------|
| Node.js | 20+ | 建议用 [nodejs.org](https://nodejs.org/) LTS 或 `nvm` / `fnm` 安装 |
| pnpm | 10+ | 本仓库 `packageManager` 已锁定；未安装时执行 `npm install -g pnpm` |

确认版本：

```bash
node -v    # 应 ≥ v20
pnpm -v    # 应 ≥ 10
```

---

## 环境配置（详细步骤）

前端通过 **Vite 环境变量** 连接后端**统一 API 网关**（单端口，路径含 `/api/v1`）。  
变量文件必须放在**前端包根目录**（与 `vite.config.ts`、`package.json` 同级）：

- 独立克隆本仓库时：仓库根目录
- 在 IPOI 中：`frontend/ipo-risk-analyzer/`

**不要**把 `.env` 放进 `client/` 目录（Vite `envDir` 指向包根）。

### 步骤 1：进入前端包根

```bash
# 独立仓库
cd ipo-risk-analyzer

# 或 IPOI monorepo
cd IPOI/frontend/ipo-risk-analyzer
```

### 步骤 2：安装依赖

```bash
pnpm install
```

首次安装会生成 / 更新 `pnpm-lock.yaml`，并应用 `patches/wouter@3.7.1.patch`。

### 步骤 3：创建并编辑 `.env`

```bash
# Windows (cmd)
copy .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

用编辑器打开 `.env`，设置后端地址：

| 变量 | 必填 | 说明 |
|------|------|------|
| `VITE_API_BASE_URL` | 建议填写 | 后端 API 根路径，**必须包含** `/api/v1` 前缀 |

**本机联调示例：**

```bash
VITE_API_BASE_URL=http://localhost:9100/api/v1
```

**远程服务器示例：**

```bash
VITE_API_BASE_URL=http://223.3.95.129:9100/api/v1
```

**同域部署（生产）：** 可删除或注释该行，前端默认请求相对路径 `/api/v1`（由网关转发到后端）。

### 步骤 4：启动开发服务器

```bash
pnpm dev
```

浏览器打开终端提示的地址（默认 `http://localhost:3000`）。`--host` 已启用，局域网设备可用本机 IP 访问。

### 步骤 5：修改配置后必须重启

改动 `.env` 后，在运行 `pnpm dev` 的终端按 `Ctrl+C` 停止，再重新执行 `pnpm dev`。  
**只保存 `.env` 而不重启，变量不会生效。**

### 其他环境文件

| 文件 | 是否提交 Git | 作用 |
|------|--------------|------|
| `.env` | 否（已 ignore） | 本机联调配置 |
| `.env.example` | 是 | 模板，无密钥 |
| `.env.local` | 否 | 多为 Vercel CLI 生成，与本前端无关，可删 |

### 跨域与 SSE

- 前后端不同域时，后端需配置 **CORS**，并允许 `Authorization` 头
- 分析流使用 **SSE**（`EventSource`），后端需支持 `text/event-stream`，建议心跳
- 浏览器控制台若出现 CORS / 网络错误，优先核对 `VITE_API_BASE_URL` 与后端是否可达

### 可选：公司代码 lookup

首页输入 ticker 会查询 `client/public/company-lookup.json`。更新源表后：

```bash
# 将 data/companyinfo.xlsx 放在包根下的 data/ 目录
pnpm build:data
```

---

## 快速开始（命令速查）

```bash
pnpm install          # 安装依赖
pnpm dev              # 开发（http://localhost:3000）
pnpm check            # TypeScript 检查
pnpm build            # 生产构建（前端 + Express 静态服务）
pnpm preview          # 预览构建结果
pnpm start            # 生产启动（需先 build）
```

> Windows 下若 `pnpm start` 因 `NODE_ENV=production` 报错，可执行：  
> `set NODE_ENV=production && node dist/index.js`

---

## 使用流程

```mermaid
flowchart LR
  Home[首页项目列表] --> Upload[上传 PDF 创建项目]
  Upload --> Parse[解析页]
  Parse --> Index[向量索引就绪]
  Index --> Analysis[多 Agent 分析]
  Analysis --> Report[风险报告]
```

### 首页（`/`）

- **新建项目**：上传招股书 PDF，填写 Wind 代码 / 股票代码，可选项目名
- **是否生物医药**：必选（`isBiotech`）
- **标准 / 专业模式**：专业模式开启 `enableEmbellishment`（文本粉饰度）
- **项目列表**：查看、删除、下载报告 PDF
- **多选导出 / 导入**：见下文「项目导出与导入」
- **设置**：可选 Agent LLM（`apiBaseUrl` / `apiKey` / `model`）

### 解析页（`/project/:id`）

- 展示 Markdown 解析结果与统计
- 解析完成后轮询索引；仅 `index-status = ready` 时可启动分析

### 分析页（`/project/:id/analysis`）

- 四 Agent 思考流、专家辩论、专项报告
- SSE 实时推送；完成后拉 `analysis/result` 与报告
- **换路由保活**：分析进行中返回首页或打开其他页面，**不会中断**当前 SSE；回到该项目分析页可续看进度。F5 整页刷新仍会断开（需重新等待后端完成或从缓存恢复）
- 若总控判定无需辩论，右侧会显示「总控Agent认为无需辩论」
- 支持重新分析（原结果归档到历史版本）

### 报告页（`/project/:id/report`）

- 综合风险评分、维度、因子、走势与上市后验证等
- 专业模式下展示文本粉饰度（有数据时）
- 导出 PDF（优先本地缓存）

### 路由一览

| 路径 | 页面 |
|------|------|
| `/` | 项目列表 |
| `/project/:id` | 解析结果 |
| `/project/:id/analysis` | 多 Agent 分析 |
| `/project/:id/report` | 风险报告 |

---

## 项目导出与导入

项目数据存在**当前浏览器**的 `localStorage` + IndexedDB 中。换电脑、换浏览器或清站点数据前，请先导出。

### 导出

1. 打开首页项目列表
2. 勾选一个或多个项目（表头可全选）
3. 点击 **导出项目**
4. **Chrome / Edge**：弹出文件夹选择器，ZIP 写入所选目录  
   **其他浏览器**：可能不支持选文件夹，文件会下载到浏览器默认下载目录
5. 导出文件名形如：`项目显示名.ipo-project.zip`

包内大致结构：

```text
*.ipo-project.zip
├── project.json          # 项目元数据
└── cache/
    ├── source.pdf
    ├── parse-content.md
    ├── parse-stats.json
    ├── analysis.json
    ├── report.json
    ├── report.pdf        # 若有
    └── analysis-history/ # 历史版本（若有）
```

### 导入

1. 首页点击 **导入项目**
2. 选择 `.zip` 或 `.ipo-project.zip`
3. 成功后列表出现该项目；同 ID 会覆盖本地同名项目缓存

### `backup/` 目录作用

仓库内 **`backup/`** 存放导出的 **演示 / 样例** 项目包（随前端一并提交），例如：

```text
backup/
├── 02531_....ipo-project.zip
└── 02531_....ipo-project/     # 解压后的目录（可选）
    ├── project.json
    └── cache/
```

| 用途 | 说明 |
|------|------|
| 演示导入 | 克隆仓库后，用首页「导入项目」选择 `backup/*.ipo-project.zip` 即可还原样例 |
| 本地备份 | 也可把新导出的包放进 `backup/`，便于换机或回归 |
| 回归对照 | 固定样例包便于复现报告页与历史版本 |

**注意：**

- `backup/` **不是**运行时依赖；前端不会自动读取该目录
- 只能通过 UI「导入项目」把 ZIP 写回浏览器缓存
- 包内含招股书 PDF 与分析结果；公开仓库请确认样例可对外展示

---

## 数据与缓存

项目管理由**前端本地**完成，后端无项目 CRUD。

| 存储 | 键 / 库 | 内容 |
|------|---------|------|
| `localStorage` | `ipo:projects` | 项目元数据列表 |
| `localStorage` | `ipo:projectState` | 解析/分析完成标记 |
| `localStorage` | `ipo:agentLlmSettings` | 可选 LLM 配置 |
| IndexedDB | `ipo-cache` | PDF、解析、分析、报告、历史版本 |

---

## 项目结构

```
frontend/ipo-risk-analyzer/   # IPOI 仓库中的路径
├── client/                   # 前端源码（Vite root）
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── contexts/         # 含 AnalysisSessionProvider（分析保活）
│   │   ├── services/
│   │   ├── data/
│   │   └── lib/
│   └── public/
├── server/                   # 生产 Express 静态服务
├── scripts/
├── backup/                   # 本地导出备份（gitignored）
├── .env.example
├── vite.config.ts
└── 项目接口.md
```

---

## 后端依赖

前端对接真实 API。接口清单见 [`项目接口.md`](项目接口.md)，主要包括：

- `POST /parse/expert/start` — 上传并解析
- `GET /parse/expert/tasks/:taskId/progress` / `result`
- `GET /projects/:clientProjectId/index-status`
- `POST /projects/:clientProjectId/analysis/start`
- `GET /projects/:clientProjectId/analysis/stream`（SSE）
- `GET /projects/:clientProjectId/analysis/result`
- `GET /projects/:clientProjectId/report` / `report/export`

`clientProjectId` 为前端每次创建生成的 `proj-{hex}`。

---

## 常见问题

**Q：页面空白或接口 404？**  
检查 `.env` 中 `VITE_API_BASE_URL`、后端是否可达，并**重启** `pnpm dev`。

**Q：分析按钮不可点？**  
等待 `index-status` 为 `ready`。

**Q：报告页显示「暂无报告」？**  
需先完成分析；无本地缓存且 API 失败时不会展示演示数据。

**Q：分析中途回首页，再进分析页还能看到进度吗？**  
可以。会话在内存中保活，换路由不断开 SSE。整页 F5 刷新会断流。

**Q：换电脑后项目不见了？**  
用首页导出 ZIP，放到 `backup/` 备份，在新环境「导入项目」。
