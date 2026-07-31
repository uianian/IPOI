# IPOI 仓库总说明

## 1. 当前仓库检查结论

截至当前检查时间，`IPOI` 根仓库未发现明显的文件、代码或配置丢失，结论如下：

- 当前工作分支：`main`
- 当前远端：`origin -> git@github.com:uianian/IPOI.git`
- 当前工作区状态：`git status --short` 为空，说明工作区在 git 视角下是干净的
- 本地保留分支：`local-secret-backup`
- `main` 与 `local-secret-backup` 的跟踪文件数量一致，均为 `1314`
- `main` 与 `local-secret-backup` 的差异仅有 2 个文件：
  - `agents/ipo/configs/settings.yaml`
  - `agents/ipo/src/config.py`

因此可以判断：

1. 没有出现整批目录丢失、代码缺失或配置文件大面积遗漏。
2. 当前 `main` 是一份为 GitHub 公开仓库整理后的安全版本。
3. `local-secret-backup` 保留了本地历史，用于兜底和回看，但不建议直接推送。

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

这是当前对外发布分支，已经推送到 GitHub。

用途：

- 作为公开仓库主分支
- 不包含提交到历史中的真实密钥
- 适合作为后续正常开发、提交、推送的基础分支

### `local-secret-backup`

这是本地保留的备份分支，用于兜底，不建议直接推送。

用途：

- 保留此前本地整理过程中的历史
- 在需要核对某次中间状态时可参考

注意：

- 该分支不应直接推送到公开仓库
- 日常开发应以 `main` 为准

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

## 7. 以后日常必备 Git 命令

以下命令默认都在仓库根目录 `IPOI/` 下执行。

### 7.1 查看状态

```bash
git status
git status --short
git branch -vv
git remote -v
```

### 7.2 拉取远端最新内容

```bash
git fetch origin
git pull --rebase origin main
```

如果你当前就在 `main` 上，推荐优先使用：

```bash
git pull --rebase
```

### 7.3 提交本地修改

提交流程建议固定为：

```bash
git status
git add .
git status
git commit -m "你的提交说明"
```

更稳妥的检查方式：

```bash
git diff
git diff --cached
```

### 7.4 推送到远端

```bash
git push origin main
```

如果当前分支已经跟踪了远端，一般可直接：

```bash
git push
```

### 7.5 新建功能分支

```bash
git switch -c feature/your-topic
```

开发完成后切回主分支：

```bash
git switch main
git pull --rebase
```

### 7.6 查看提交历史

```bash
git log --oneline --decorate -20
git log --graph --oneline --decorate --all
```

### 7.7 查看两个分支差异

```bash
git diff --stat main..local-secret-backup
git diff main..local-secret-backup -- agents/ipo/configs/settings.yaml
```

### 7.8 检查某个文件是否被忽略

```bash
git check-ignore -v path/to/file
```

### 7.9 恢复误加到暂存区的文件

```bash
git restore --staged path/to/file
```

### 7.10 放弃工作区未提交修改

谨慎使用：

```bash
git restore path/to/file
```

不要在不确定时直接批量恢复整个仓库。

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

每次开始开发前：

```bash
git switch main
git pull --rebase
git status
```

每次修改后：

```bash
git diff
git add .
git diff --cached
git commit -m "your message"
git push
```

每次涉及 `settings.yaml` 前：

```bash
git update-index --no-skip-worktree agents/ipo/configs/settings.yaml
```

完成后若要恢复本地保护：

```bash
git update-index --skip-worktree agents/ipo/configs/settings.yaml
```

## 10. 当前仓库维护建议

- 公开仓库中不要再次提交真实 API Key
- 如需长期保留本地密钥，优先考虑环境变量方案
- 推送前始终执行一次 `git status` 和 `git diff --cached`
- 不要把 `local-secret-backup` 直接推送到远端
- 如果后续新增新的运行缓存、权重目录或本地输出目录，应及时补充 `.gitignore`
- `pdf_parsing` 与 `retrieval` / Agent **分环境维护**；改依赖后记得重新导出对应 `requirements.txt`
