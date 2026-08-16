# IPOI 仓库总说明

## 1. 当前仓库结论

- 远端：`origin -> git@github.com:uianian/IPOI.git`
- 对外主分支：`main`（已保护：必须走 PR，至少 1 个有写权限的人 Approve，禁止 force push / 删除）
- 协作者：仓库主人 + `likesnow97`（Collaborator，可推功能分支）
- 截至 2026-08-16，`main` 已合入：
  - PR #1：周杰市场情绪 Agent（`c44f862`）
  - PR #2：本地财务/法务/总控接回（`6a65d01`）
- Agent 模块说明见 [`agents/hk_ipo_risk/README.md`](agents/hk_ipo_risk/README.md)（市场改动 §14，冲突处理 §15，总控/辩论 §9）
- **所有协作者必须按第 7 节走功能分支 + PR，禁止直推 `main`**

`local-secret-backup` 仍是本机兜底分支，**不要推送到公开仓库**。工作区里的 `pdf_parsing/output`、报告成品、`*.local.yaml` 密钥不要提交。

## 2. 根目录结构

当前仓库根目录包含：

- `.cursor/`
- `agents/`
- `dataset/`
- `dataset_analysis/`
- `IPO_skills/`
- `pdf_parsing/`
- `retrieval/`
- `.gitignore`
- `README.md`

说明：

- `dataset/` 在根目录 `.gitignore` 中被忽略，不会进入公开仓库
- `**/.runtime/`、`*.log`、`*.jsonl`、模型权重、`.env` 等也已被忽略
- `示例 PDF`、报告、部分过程文件按当前策略保留
- 各子项目环境依赖见对应目录下的 `requirements.txt`（详见第 3 节）

## 3. 环境配置说明

本仓库 **不要混用同一个 Python 环境**。`pdf_parsing` 依赖 Torch / VLM 解析栈，与检索、Agent 分析环境分离。

### 3.1 环境与服务对照

| 模块 | Conda 环境 | Python | 默认端口 | 依赖文件 | 启动脚本 |
|------|------------|--------|----------|----------|----------|
| `pdf_parsing` | `infinity_parser` | 3.12.11 | `9100` | [`pdf_parsing/requirements.txt`](pdf_parsing/requirements.txt) | `pdf_parsing/scripts/start_expert_parse_service.sh` |
| `retrieval` | `ipo-risk` | 3.10.18 | `9101` | [`retrieval/requirements.txt`](retrieval/requirements.txt) | `retrieval/scripts/start_retrieval_service.sh` |
| `agents/hk_ipo_risk` | `ipo-risk` | 3.10.18 | `9102` | [`agents/hk_ipo_risk/requirements.txt`](agents/hk_ipo_risk/requirements.txt) | `agents/hk_ipo_risk/scripts/start_analysis_service.sh` |
| `agents/ipo` | `ipo-risk` | 3.10.18 | 历史 demo，非现行三端口主链路 | [`agents/ipo/requirements.txt`](agents/ipo/requirements.txt) | `agents/ipo/scripts/start_*.sh` |

说明：

- `retrieval`、`agents/hk_ipo_risk`、`agents/ipo` **共用** `ipo-risk` 环境；对应 `requirements.txt` 内容一致，均从该环境导出。
- `pdf_parsing` **必须**使用 `infinity_parser`，不要装进 `ipo-risk`。
- 本机 conda 路径示例：`/nfs/users/wuqianqian/anaconda3/envs/<env>/bin`。

### 3.2 创建 / 激活环境

解析环境：

```bash
conda create -n infinity_parser python=3.12
conda activate infinity_parser
pip install -r pdf_parsing/requirements.txt
```

检索 / Agent 环境：

```bash
conda create -n ipo-risk python=3.10
conda activate ipo-risk
pip install -r retrieval/requirements.txt
# 或
# pip install -r agents/hk_ipo_risk/requirements.txt
# pip install -r agents/ipo/requirements.txt
```

日常激活：

```bash
# 解析服务
conda activate infinity_parser

# 检索 / 财务法务分析
conda activate ipo-risk
```

### 3.3 重新导出依赖（环境变更后）

环境里装过新包后，建议重新导出，避免文档与真实环境脱节：

```bash
# pdf_parsing <- infinity_parser
/nfs/users/wuqianqian/anaconda3/envs/infinity_parser/bin/pip freeze \
  > pdf_parsing/requirements.txt

# 共用 ipo-risk 的三个项目
/nfs/users/wuqianqian/anaconda3/envs/ipo-risk/bin/pip freeze \
  | tee retrieval/requirements.txt \
        agents/hk_ipo_risk/requirements.txt \
        agents/ipo/requirements.txt > /dev/null
```

导出后请在文件头部补回用途说明（环境名、Python 版本、对应端口），并对 `file://` 这类 conda 本地路径做可移植改写（当前 `pdf_parsing/requirements.txt` 已处理过）。

### 3.4 启动服务时指定环境

启动脚本已默认绑定对应 conda `bin`，一般直接执行即可：

```bash
# 9100 解析（infinity_parser）
cd pdf_parsing && ./scripts/start_expert_parse_service.sh

# 9101 检索（ipo-risk）
cd retrieval && ./scripts/start_retrieval_service.sh

# 9102 分析（ipo-risk）
cd agents/hk_ipo_risk && ./scripts/start_analysis_service.sh
```

如需临时覆盖：

```bash
CONDA_BIN=/nfs/users/wuqianqian/anaconda3/envs/infinity_parser/bin ./scripts/start_expert_parse_service.sh
CONDA_BIN=/nfs/users/wuqianqian/anaconda3/envs/ipo-risk/bin ./scripts/start_retrieval_service.sh
```

## 4. 分支说明

### `main`

公开主分支。**禁止直接 `git push origin main`。** 所有改动经功能分支 + Pull Request 进入。

### 功能分支

命名：`feat/主题`、`fix/主题`。从最新 `main` 拉出，推送到 `origin`，再开 PR。

### `local-secret-backup`

仅本机兜底，不要推送。日常开发不要在这个分支上继续写。

### `backup/local-wip-20260816`

本机备份提交（PR #2 合入前的财务/法务/总控工作区）。只作对照，不要推送、不要在上面继续开发。

## 5. `settings.yaml` 与密钥说明

当前重点文件：

- `agents/ipo/configs/settings.yaml`
- `agents/ipo/src/config.py`

### 仓库版本与本地版本的区别

仓库中公开的安全版本设计为：

- `settings.yaml` 中的 `api_key` 应为空
- 运行时优先从环境变量读取密钥

当前代码已支持以下读取顺序：

1. `settings.yaml` 中的 `api_key`
2. 环境变量 `OPENROUTER_API_KEY`
3. 环境变量 `OPENAI_API_KEY`

### 当前本地状态

为了不影响你本地后续运行，当前本地工作区中的 `agents/ipo/configs/settings.yaml` 已恢复你的密钥；但为了避免再次误提交，这个文件已被标记为：

- `skip-worktree`

可通过以下命令确认：

```bash
git ls-files -v agents/ipo/configs/settings.yaml
```

看到前缀 `S`，就表示该文件当前处于本地保护状态。

### 这意味着什么

- `git status` 默认不会再提示这个文件的本地密钥变更
- 该文件可以继续用于本地运行
- 但如果你要正式修改并提交这个文件，必须先取消 `skip-worktree`

### 取消本地保护

```bash
git update-index --no-skip-worktree agents/ipo/configs/settings.yaml
```

### 重新启用本地保护

```bash
git update-index --skip-worktree agents/ipo/configs/settings.yaml
```

## 6. 当前 `.gitignore` 策略

当前根目录 `.gitignore` 主要忽略以下内容：

- `dataset/`
- `**/.runtime/`
- `**/__pycache__/`
- `*.pyc`
- `**/.pytest_cache/`
- `**/.venv/`
- `**/venv/`
- `*.egg-info/`
- `*.log`
- `*.jsonl`
- `.env`
- `*.env`
- `*.pt`
- `*.pth`
- `*.ckpt`
- `*.bin`
- `*.onnx`
- `*.safetensors`
- `**/node_modules/`
- `pdf_parsing/INF-MLLM/**/docs/`
- `pdf_parsing/INF-MLLM/**/assets/`
- `pdf_parsing/INF-MLLM/**/demo_data/`
- `pdf_parsing/INF-MLLM/**/drive/chromedriver`

目的：

- 不把原始数据集、运行缓存、日志、模型权重、第三方 demo 资源和敏感文件传到公开仓库
- 保留与你项目直接相关的代码、报告、样例材料和必要过程产物

## 7. 协作者 Git 工作流程（所有人必须遵守）

仓库：`git@github.com:uianian/IPOI.git`。`main` 已保护，直接推 `main` 会被拒绝。自己的 PR 一般不能自己 Approve，需另一名有写权限的协作者 Approve 后再 Merge。

以下命令均在仓库根目录执行。不要 `git add -A` / `git add .`（会把解析产物、报告、密钥加进去）。不要 `git push --force` 到 `main`。不要 `git reset --hard`、`git clean -fd`，除非你明确知道会丢掉什么。

### 7.1 第一次：克隆官方仓库

周杰及后续协作者应直接克隆本仓库，不要把 fork 当主工作区。

```bash
git clone git@github.com:uianian/IPOI.git
cd IPOI
git remote -v
# 应看到 origin -> git@github.com:uianian/IPOI.git
```

若本地还是旧 fork：

```bash
git remote add official git@github.com:uianian/IPOI.git
git fetch official
git checkout -B main official/main
git branch -u official/main main
```

之后推送用 `official`，或把 `origin` 改成官方地址。

本机已有克隆（服务器 `/nfs/users/wuqianqian/IPOI`）只需：

```bash
cd /nfs/users/wuqianqian/IPOI
git checkout main
git pull origin main
```

### 7.2 每次开工：对齐 main，再开功能分支

```bash
git checkout main
git pull origin main
git checkout -b feat/你的主题
git branch --show-current
git log -1 --oneline
```

分支名示例：`feat/master-debate`、`feat/market-postlisting`、`fix/finance-runway`。不要两人都叫 `dev`。

`pdf_parsing/output` 等未提交文件可以留在工作区，只要后面只 `git add` 你改的代码。

### 7.3 提交（只加有价值的代码）

```bash
git status
git diff
git add agents/hk_ipo_risk/src/path/to/file.py
git diff --cached
git commit -m "说明为什么改，而不是改了哪些文件"
```

不要加入：`pdf_parsing/output`、`*.local.yaml`、`.env`、密钥、大 CSV/JSON 解析结果、`agents/hk_ipo_risk/reports/` 跑批成品（除非约定要入库）。

### 7.4 推功能分支（不要推 main）

```bash
git push -u origin feat/你的主题
```

成功后终端会给出开 PR 的链接。**不要**执行 `git push origin main`。

### 7.5 网页开 Pull Request

1. 打开 https://github.com/uianian/IPOI 或终端给出的  
   `https://github.com/uianian/IPOI/pull/new/feat/你的主题`
2. 也可手动：https://github.com/uianian/IPOI/compare/main...feat/你的主题
3. **base** 必须是 `main`，**compare** 是你的功能分支
4. 写清改了什么、是否动到共享文件（见下）
5. 点 **Create pull request**

### 7.6 网页审核与合并

1. 另一人打开 PR → **Files changed**
2. **Review changes** → **Approve**（或 Request changes）→ **Submit review**
3. 作者按意见改完后 `git add` / `commit` / `git push`（同一功能分支即可，PR 自动更新）
4. 若开启了 “Dismiss stale approvals”，改完后需要重新 Approve
5. 批准后：**Create a merge commit** → **Merge pull request** → **Confirm merge**

作者不能给自己的 PR 点 Approve。只有仓库主人可见 **Merge without waiting for requirements to be met (bypass rules)**，仅紧急时使用，日常不要旁路。

合完后网页上可 **Delete branch**。

### 7.7 合完后两边都拉 main

```bash
git checkout main
git pull origin main
git log -1 --oneline
```

本地功能分支可删：

```bash
git branch -d feat/你的主题
git push origin --delete feat/你的主题
```

### 7.8 与对方分支冲突时

在你的功能分支上：

```bash
git checkout feat/你的主题
git fetch origin
git merge origin/main
# 打开标为 both modified 的文件，搜 <<<<<<<
# 改完：
git add 解决完的文件
git commit
git push
```

高冲突共享文件（PR #2 已处理过一次，以后仍容易打架）：

- `agents/hk_ipo_risk/scripts/run_finance_legal.py`
- `agents/hk_ipo_risk/service/analysis_runner.py`
- `agents/hk_ipo_risk/service/thought_mapper.py`
- `agents/hk_ipo_risk/src/agents/market_agent.py`
- `agents/hk_ipo_risk/src/config.py`
- `agents/hk_ipo_risk/src/graph/parallel.py`
- `agents/hk_ipo_risk/src/models/evidence.py`
- `agents/hk_ipo_risk/src/skills/market_toolbox.py`

原则：市场正式实现以周杰侧为准；总控/财务/法务/辩论以接回后的 `main` 为准，不要再写回市场 demo stub。

### 7.9 常用只读命令

```bash
git status -sb
git branch -vv
git log --oneline --decorate -15
git diff --stat origin/main...HEAD
git check-ignore -v path/to/file
git restore --staged path/to/file    # 撤销误 add
```

放弃某个未提交文件（会丢该文件的工作区改动）：

```bash
git restore path/to/file
```

## 8. 与 `settings.yaml` 相关的常用命令

### 查看当前是否被保护

```bash
git ls-files -v agents/ipo/configs/settings.yaml
```

### 想编辑并提交它时

```bash
git update-index --no-skip-worktree agents/ipo/configs/settings.yaml
git status
```

修改、提交完成后，如果还想继续本地保留密钥：

```bash
git update-index --skip-worktree agents/ipo/configs/settings.yaml
```

### 推荐的更安全运行方式

长期来看，更推荐把密钥放在环境变量中，而不是长期写回文件：

```bash
export OPENROUTER_API_KEY="your-key"
```

或者：

```bash
export OPENAI_API_KEY="your-key"
```

## 9. 建议的日常操作顺序

```text
git checkout main && git pull origin main
    → git checkout -b feat/主题
    → 改代码（只 add 具体文件）
    → git commit && git push -u origin feat/主题
    → 网页开 PR
    → 另一人 Approve
    → 网页 Merge
    → git checkout main && git pull origin main
```

涉及 `agents/ipo/configs/settings.yaml` 前：

```bash
git update-index --no-skip-worktree agents/ipo/configs/settings.yaml
```

提交完成后若要继续本地留密钥：

```bash
git update-index --skip-worktree agents/ipo/configs/settings.yaml
```

市场 Agent 密钥用 `*.local.yaml` 或环境变量，不要提交真实 Key。

## 10. 当前仓库维护建议

- 公开仓库中不要再次提交真实 API Key
- 不要直接推 `main`；不要把 `local-secret-backup` 推到远端
- 推送前执行 `git status` 和 `git diff --cached`，确认没有解析产物
- 新增运行缓存、权重、本地输出目录时及时补 `.gitignore`
- `pdf_parsing` 与 `retrieval` / Agent **分环境维护**；改依赖后重新导出对应 `requirements.txt`
- 市场额外依赖：`agents/hk_ipo_risk/requirements-market.txt`
