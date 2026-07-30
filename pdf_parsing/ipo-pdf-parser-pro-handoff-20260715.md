# Handoff: IPO 招股书 PDF 解析（pdf_parser_pro）

- **Date**: 2026-07-15
- **Workspace**: `/nfs/users/wuqianqian/IPOI`
- **Focus for next session**: 理解并续作 `pdf_parsing/pdf_parser_pro.py` 生产管线（质量门禁、竖表/附录表修复、bbox 坐标一致性）
- **Conda env**: `/nfs/users/wuqianqian/anaconda3/envs/infinity_parser/bin/python`
- **Agent transcript**: [`港股IPO解析会话`](a7f36935-6aa3-44ae-96d8-3825d214c09f)

---

## Suggested skills

下一会话开始时请先读并遵循：

1. **`hk-ipo-pdf-parsing`** — `.cursor/skills/hk-ipo-pdf-parsing/SKILL.md`  
   招股书 PDF→结构化 JSON、竖表/表格丢失等异常必须以本 skill 流程处理。
2. **`ipo-risk-feature-extraction`** — 下游财务/风险抽取依赖 `category=table` HTML；低置信表禁止硬算。
3. **`ipo-risk-rag-retrieval`** — 证据需页码+bbox；旋转页 bbox 坐标系问题会影响高亮。

参考（勿重复抄写全文）：

- 已知异常案例：`.cursor/skills/hk-ipo-pdf-parsing/references/known_issues.md`
- 竖表 benchmark：`pdf_parsing/output/mixue-1-30-pro/rotation_benchmark.md`
- 30 页对比：`pdf_parsing/output/mixue-1-30-pro/compare_report.md`
- QA 样例：`pdf_parsing/output/mixue_default/qa_report.md`

---

## 1. 当前状态（一句话）

生产解析器是 **`pdf_parsing/pdf_parser_pro.py`**（Infinity-Parser2-Flash + 官方后处理 + 页级旋转/回退 + 表格置信度）。配套已有 **`table_quality.py` / `qa_parse_quality.py` / `merge_parse_pages.py`**。蜜雪 558 页默认跑通（`output/mixue_default`）；竖表与附录丢 table 结构尚未闭环修补。

---

## 2. 相关文件

| 路径 | 角色 |
|---|---|
| `pdf_parsing/pdf_parser_pro.py` | 生产主解析器 |
| `pdf_parsing/table_quality.py` | 表格质量分 + `table_structure_confidence`（无 torch） |
| `pdf_parsing/qa_parse_quality.py` | Pass2 质量门禁 → `qa_report.json` |
| `pdf_parsing/merge_parse_pages.py` | Pass3/4 页级合并重跑结果 |
| `pdf_parsing/benchmark_rotation.py` | 竖表旋转策略对比 |
| `pdf_parsing/compare_parse_outputs.py` | 两份 full_parse 同页对比 |
| `pdf_parsing/parse_prospectus.py` | 旧简版（150 DPI / 4096 tokens），不建议再生产主跑 |
| `pdf_parsing/pdf_parser.py` | 官方对齐底座（未再作主路径） |
| `pdf_parsing/models/infly/Infinity-Parser2-Flash/` | 本地模型 |
| `pdf_parsing/INF-MLLM/.../utils/utils.py` | 官方 `postprocess_doc2json_result` |
| `pdf_parsing/pdf/mixue.pdf` | 558 页样本 |
| `pdf_parsing/output/mixue_default/` | 默认参数全文解析结果 + QA |
| `pdf_parsing/output/mixue-first/` | 旧 `parse_prospectus`（或早期）对照 |
| `pdf_parsing/output/mixue-1-30-pro/` | 30 页 + 旋转实验 |

---

## 3. `pdf_parser_pro.py` 处理流程

```
main()
  ├─ collect_pdf_paths(input)
  ├─ load_model(model, device_map)
  └─ for each PDF:
       parse_pdf(...)
         ├─ render_pdf_pages          # PyMuPDF, 默认 300 DPI；可选 --pages
         ├─ resolve_page_rotation     # 每页角度（默认 none=0）
         │    └─ detect_vertical_table_rotation  # rotate-mode=auto 时
         ├─ rotate_image_cw           # ★ 整页旋转（非表格区域裁剪旋转）
         ├─ parse_pages_batch         # Infinity-Parser2 batch 推理
         └─ per page:
              ├─ postprocess_page     # 官方 extract→truncate→bbox还原→json.loads
              ├─ [optional] rotate_fallback: 原向再跑一轮，score_table_quality 择优
              ├─ save_figure_crops    # bbox 裁 figure（坐标系=送入后处理的那张图）
              ├─ annotate_table_confidence  # 元素级+页级置信度
              └─ page_to_preview_markdown
       save_outputs → full_parse.json / preview.md / parse_summary.json / risk_chunks.json
```

### 方法调用关系（核心）

| 函数 | 作用 |
|---|---|
| `load_model` | HF `AutoModelForImageTextToText` + `AutoProcessor`，`bfloat16`，`device_map=auto` |
| `convert_pdf_to_images` / `render_pdf_pages` | 整本或指定页渲染 |
| `detect_vertical_table_rotation` | PyMuPDF 竖排文本块 ≥5 → 建议 CW90 |
| `resolve_page_rotation` | `none/auto/cw90/ccw90/180/manual` + 可选 `--rotate-pages` 白名单 |
| `rotate_image_cw` | PIL 整页顺时针旋转 |
| `parse_pages_batch` | Qwen VL 风格 messages，`do_resize=False`，`image_patch_size=16`，`temperature=0` |
| `parse_single_page_raw` | batch_size=1，供旋转回退 |
| `postprocess_page` | 调用官方 `postprocess_doc2json_result`；失败标 `failed`/`partial`，不塞 raw JSON 整页 text |
| `score_table_quality` / `annotate_table_confidence` | 来自 `table_quality.py` |
| `extract_risk_chunks` | table 全收；text/title 命中风险关键词才收 |
| `save_outputs` / `build_parse_summary` | 落盘 + 摘要（含 `table_structure_confidence_pages`） |

### 关键设计约束（易踩坑）

1. **旋转是页级，不是表级**：整页 image rotate 后再推理。  
2. **bbox 在「送入后处理的图像」坐标系**：旋转保留时为旋转后像素；**未做逆变换回原 PDF**。下游证据高亮必须看 `rotation_applied`。  
3. **默认 `rotate-mode=none`，`rotate-fallback` 关闭**（需显式打开）。  
4. Figure 裁剪与 bbox 对齐：若保留旋转，用旋转图裁；回退后用原图。

---

## 4. 参数与默认值

| CLI / 函数参数 | 默认 | 说明 |
|---|---|---|
| `input` | 必填 | PDF 或含 `*.pdf` 的目录 |
| `-o/--output-dir` | `output/<stem>` | 输出根；实际目录为 `output_dir/stem` |
| `--model` | `./models/infly/Infinity-Parser2-Flash` | |
| `--dpi` | `300` | |
| `--batch-size` | `4` | 竖表/大表建议 1–2 |
| `--max-new-tokens` | `32768` | 对比旧版 prospectus 的 4096 |
| `--device-map` | `auto` | |
| `--pages` | 全部 | 1-based，逗号分隔 |
| `--rotate-mode` | `none` | `auto`=竖表检测后 CW90 |
| `--rotate-pages` | 全部适用 mode | 仅这些页允许旋转 |
| `--rotate-degrees` | `90` | `manual` 用 |
| `--rotate-fallback` | off | 仅 `auto` 有意义：旋转 vs 原向择优 |
| `--no-figures` / `--no-risk-chunks` | off | 关闭副产物 |

内部常量：`MIN_PIXELS=2048`，`MAX_PIXELS=16777216`。

---

## 5. 使用方法

**环境**：工作目录建议 `pdf_parsing/`，用 `infinity_parser` conda。

```bash
cd /nfs/users/wuqianqian/IPOI/pdf_parsing

# 生产推荐（竖表友好）
python pdf_parser_pro.py pdf/mixue.pdf \
  --rotate-mode auto --rotate-fallback --batch-size 2

# 默认全书（无旋转，约 2.5h/558 页量级）
python pdf_parser_pro.py pdf/mixue.pdf

# 定向重跑
python pdf_parser_pro.py pdf/mixue.pdf --pages 16,21,430,431 \
  --rotate-mode auto --rotate-fallback --batch-size 1 \
  -o output/mixue-reparse

# Pass2 QA（可 --write-confidence 写回置信度字段）
python qa_parse_quality.py output/mixue_default/full_parse.json --markdown --write-confidence

# Pass4 合并
python merge_parse_pages.py \
  --base output/mixue_default/full_parse.json \
  --patch output/mixue-reparse/mixue/full_parse.json \
  --pages 430,431 --prefer-higher-table-score --backup \
  -o output/mixue_default/full_parse.json
```

### 输出 schema（页）

```json
{
  "page": 16,
  "parse_status": "ok",
  "elements": [
    {
      "bbox": [x1,y1,x2,y2],
      "category": "table|text|...",
      "text": "<table>...</table> 或 Markdown",
      "table_structure_confidence": "high|medium|low",
      "table_quality_score": 1234,
      "table_quality_notes": ["..."]
    }
  ],
  "rotation_applied": 90,
  "table_structure_confidence": "low",
  "table_quality_score": 1234,
  "table_quality_notes": ["possible_vertical_table"]
}
```

副产物：`preview.md`、`parse_summary.json`、`risk_chunks.json`、`figures/pXXXX_figYYY.png`。

---

## 6. 已验证结论（蜜雪）

对照历史实验（详见 conversation / compare_report；勿重复全量复跑除非改模型）：

| 点 | 结论 |
|---|---|
| vs `parse_prospectus` | pro 更稳：0 失败页（旧版第 7 页 raw-JSON 失败）；页眉/脚注更好；复杂表合并（如 p461）更好 |
| 默认 none 跑 558 页 | 可用；附录 **430–431 丢 table→text**（数值在、结构没） |
| 竖表 16/21 | auto+fallback：16 常保留旋转；21 旋转易截断表体，需回退 |
| bbox | 旋转后坐标 ≠ 原 PDF 页坐标；无逆变换 |
| QA（mixue_default） | 建议重跑约 13 页；含 430/431 `missing_table_high_numeric` |

---

## 7. 已知不足

1. **表结构回归**：大财务表偶发成纯 `text`（附录 I 典型）。  
2. **竖表结构仍脆**：旋转非万能；置信度启发式对「有年份但 colspan 错位」可能仍判 high。  
3. **仅页级旋转**：页内局部竖表会带动整页（页眉页脚等）旋转。  
4. **bbox 未映射回原向**：证据截图/PDF 高亮若忽略 `rotation_applied` 会错位。  
5. **`--rotate-fallback` 默认关**，且每触发页多 1 次推理，成本高。  
6. **图过度切分**（如叙事页多 figure）。  
7. **跨页表未拼接**（skill 案例 3）。  
8. **无自动「QA→重跑→merge」一键编排**；脚本有了，流水线未串。  
9. **`render_pdf_pages` 先渲全书再切片**：`--pages` 仍打开整本 PDF 渲染，大文件浪费 IO。  
10. **risk_chunks** 仅关键词命中，覆盖不全。

---

## 8. 推荐改进方向（按优先级）

1. **立刻**：生产默认建议文档化为 `--rotate-mode auto --rotate-fallback`；对 QA `reparse_pages` 定向重跑 + `merge_parse_pages`。  
2. **bbox 逆变换**：`rotation_applied≠0` 时把元素 bbox 映回原向，并同步裁图；或输出双坐标系字段。  
3. **缺表修复**：加强 table prompt / 区域裁剪二次推理 / text→HTML 兜底；附录跨页拼接。  
4. **置信度规则收紧**：对竖表页（检测器命中或 notes）强制 low，供下游禁算。  
5. **性能**：`--pages` 只渲染目标页；大书可考虑官方 vLLM backend。  
6. **工程**：`parse_pipeline.sh` 串 Pass1–4；把 QA 结论写回 skill `known_issues.md`（430–431 案例）。

---

## 9. 下一会话可执行的第一刀

1. 读本 handoff + `hk-ipo-pdf-parsing` skill。  
2. 对 `mixue_default` 的 QA `reparse_pages`（至少 **430,431**）跑定向重跑并 merge。  
3. 若要做证据高亮，先实现旋转页 **bbox 逆变换**，再对接 RAG/前端。

---

## 10. 敏感信息

本文未包含密钥。模型路径与服务器用户路径为团队共享环境信息，按站点惯例即可，勿提交凭据文件。
