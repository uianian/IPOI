# 翰思艾泰 — 法务合规 Agent 风险分析报告（DeepSeek V4 Flash）

- 生成时间：2026-08-04 22:42:15
- 招股书：`03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf`
- doc_id：`hansiaitai` / issuer_type：`18a`
- 模型：`deepseek-v4-flash`（provider=deepseek）
- 评分模式：`react+rules_floor`
- 结果 JSON：`.runtime/hansiaitai_legal_deepseek_flash.json`
- 辩论素材：`.runtime/debate/hansiaitai_legal_dossier_20260804_223352.json`
- 推理日志：`logs/翰思艾泰_legal_20260804_223225.log` / `.jsonl`
- 对照：Gemma 基线成功跑 score=**51** / medium（`logs/翰思艾泰_legal_20260804_173400`，rules_floor 主导）；rules-only 回归亦为 **51**

---

## 1. 总览与质量结论

| 项 | 本轮 DeepSeek | 说明 |
|----|---------------|------|
| 风险分 / 等级 | **100.0** / **very_high** | 分项加总约 124 后封顶 100 |
| 是否规则整段回退 | **否** | 无 `fallback pipeline`；`scoring_mode=react+rules_floor` |
| ReAct 轮次 | **6** | 理想路径约 7；本轮因并行 skill 压到 6 |
| auto_submit | **False** | 第 6 轮自主 `submit_legal_report` |
| search | **0 次** | 二阶段配额生效；rule_checks 无 coverage_hints |
| 风险点条数 | **21**（dossier claims=21） | Gemma 基线仅 5 条（多为规则披露类） |
| 摘要 | 法務 ReAct 完成 5 個 skill；風險分 100.0 (very_high) | |

**总体判断**：编排与工具链**成功跑通且无规则回退**，Skill 首次真正抽出多条带页码证据的风险点，比 Gemma 基线的「Skill 空跑 + 规则托底」信息量大得多。但 **分数严重偏高（100/very_high）**，存在把常规披露/通用风险因素当成高风险、以及把「无诉讼」也加分等问题；**不宜直接当作最终预警等级**，需规则主题去重与校准后再用。

---

## 2. 工具调用与思考过程

### 2.1 调用链

`retrieve_legal → run_legal_skill+run_legal_skill+run_legal_skill+run_legal_skill+run_legal_skill → run_rule_checks → (no_tool/nudge) → (no_tool/nudge) → submit_legal_report`

| 轮次 | 工具 | prompt | completion | total | reasoning_tokens | 备注 |
|------|------|-------:|-----------:|------:|-----------------:|------|
| 1 | `retrieve_legal` | 1618 | 230 | 1848 | 62 |  |
| 2 | `run_legal_skill+run_legal_skill+run_legal_skill+run_legal_skill+run_legal_skill` | 2067 | 643 | 2710 | 154 | 同轮并行 5 个 skill（DeepSeek 支持 multi-tool） |
| 3 | `run_rule_checks` | 4921 | 144 | 5065 | 19 |  |
| 4 | `—（空转/nudge）` | 5343 | 2048 | 7391 | 2048 | 只输出长 think，未调工具；触发 no_tool nudge |
| 5 | `—（空转/nudge）` | 5405 | 2048 | 7453 | 2048 | 只输出长 think，未调工具；触发 no_tool nudge |
| 6 | `submit_legal_report` | 5467 | 2048 | 7515 | 1731 |  |

### 2.2 思考质量

- **Turn 1–3**：路径清晰（retrieve → 并行 skill×5 → rule_checks），英文 think 简洁，符合二阶段「理想路径」。
- **Turn 4–5**：规则已提示「无缺口、必须 submit」，模型却连续两轮 **只 thinking、不调工具**，reasoning 被打满（completion=2048），浪费约 **14,844** tokens，过程质量在此处明显下滑。
- **Turn 6**：切回中文长推理后成功 submit；内容覆盖赎回期限、特别权利清理、关联交易、IP、人类遗传资源等，与 Skill 产出对齐较好。
- **一阶段生效**：`reasoning_display` 为英文/中文原文，无 translate 额外调用。

### 2.3 Skill 执行摘要

| Skill | exists | confidence | n_risk_points | success |
|-------|--------|------------|---------------|---------|
| `legal_governance` | True | high | 3 | None |
| `legal_shareholder_rights` | True | high | 3 | None |
| `legal_related_party` | True | high | 3 | None |
| `legal_contracts_and_ip` | True | high | 4 | None |
| `legal_regulatory_litigation` | True | high | 5 | None |

---

## 3. Token 消耗

| 口径 | Tokens | 说明 |
|------|-------:|------|
| ReAct 主循环（jsonl 6 轮合计） | **31,982** | prompt **24,821** + completion **7,161**（含 reasoning≈**6,062**） |
| 其中空转轮（t4+t5） | **~14,844** | 约占 ReAct 总量的 46% |
| Skill 抽取×5（隐藏，未入 jsonl usage） | **未入账** | 日志另有多次 DeepSeek HTTP；估额外数千–一万级 |
| 同口径对照：Gemma 基线全流程 | ≈74,000 | ReAct 可见 41k + translate≈14k + Skill≈19k |
| 同口径对照：节流后目标估 | ≈25–40k | 本轮 ReAct 已约 32k，但含 ~15k 空转；若去掉空转 ReAct≈**17,138** |

**结论**：相对 Gemma 基线，**主循环可见 token 已下降**（无 translate、无 search 膨胀）；但仍被 **两轮空转 think** 吃掉近一半 ReAct 预算。DeepSeek 并行 skill 减少了轮次，有利于限流，但单轮 observation 变大（t3 prompt 已到 ~5k）。

---

## 4. 得分分解

分项加总 **124** → 封顶 **100.0**。

| 代码 | 加分 | 来源 | 说明 | 证据页 |
|------|------|------|------|--------|
| RIGHTS_CLEANUP_INCOMPLETE | +20.0 | llm§legal_shareholder_rights |  | 262 |
| REDEMPTION_HIGH | +18.0 | llm§legal_shareholder_rights |  | 262 |
| REGULATORY_INVESTIGATION | +18.0 | llm§legal_regulatory_litigation |  | 85 |
| RELATED_PARTY_DISCLOSURE | +15.0 | doc§3.2 |  | — |
| CONCENTRATION_DISCLOSURE | +12.0 | doc§3.3 |  | — |
| PIPELINE_DISCLOSURE | +12.0 | doc§3.5 |  | — |
| GOVERNANCE_CONTROL_GT_50 | +10.0 | llm§legal_governance |  | 115 |
| IP_PATENT_REJECTION_RISK | +8.0 | llm§legal_contracts_and_ip |  | 386 |
| HUMAN_GENETIC_RESOURCE | +8.0 | llm§legal_regulatory_litigation |  | 86 |
| LITIGATION_ABSENT | +3.0 | llm§legal_regulatory_litigation |  | 406 |

规则托底仍并入了 `RELATED_PARTY_DISCLOSURE` / `CONCENTRATION_DISCLOSURE` / `PIPELINE_DISCLOSURE`（与 rules-only=51 同源主题）。

---

## 5. 风险点明细（含证据）

共 **21** 条（level: {'high': 3, 'medium': 13, 'low': 5}）。

| 代码 | 等级 | 来源 | 页 | 描述 | 证据摘录 |
|------|------|------|----|------|----------|
| GOVERNANCE_CONTROL_GT_50 | high | llm§legal_governance | 115 | 控股股東持有本公司已發行股本約55.89%，超過50%，形成單一控制集團，可能阻礙公司控制權變更，損害少數股東利益。 | 緊隨完成全球發售後，假設超額配股權未獲行使，則我們的控股股東將持有本公司已發行股本的約55.89%。該等所有權的集中可能會阻礙、延遲或阻止本公司控制權的變更，而這可能會剝奪其他股東在出售本公司股份時獲得溢價的機會，並可能降低本公司股份的價… |
| GOVERNANCE_CONCERT_PARTY | medium | llm§legal_governance | 254 | 本公司與武漢瀚中及杭州甘明就杭州翰思的管理訂立一致行動協議，該協議尚未終止，可能影響附屬公司層面的決策獨立性。 | 於2018年，本公司與武漢瀚中及杭州甘明就杭州翰思的管理訂立一致行動協議。根據一致行動協議，武漢瀚中、本公司及杭州甘明同意於杭州翰思股東會上就杭州翰思的營運及股東的行動採取一致行動。 |
| GOVERNANCE_BOARD_INDEPENDENCE | low | llm§legal_governance | 272 | 董事會結構未見詳細披露，但執行董事肖女士持股極少，獨立性需進一步評估。 | 肖女士（我們的執行董事）持有11,100股H股（於上市後佔我們已發行股份總額約0.01%）將不計入公眾持股量。 |
| REDEMPTION_HIGH | high | llm§legal_shareholder_rights | 262 | 贖回權觸發期限不足12個月（截至2025年8月31日，需於2025年12月31日前上市，剩餘約4個月），且贖回負債金額人民幣138.5百萬元，可能導致流動性風險及上市受阻。 | 倘發生下列情況：(i)上市申請被聯交所撤回或駁回；或(ii)申請上市的中國證監會備案被中國證監會駁回；或(iii)本公司未能於2025年12月31日前完成於聯交所的上市（以較早者為準），則特別權利將自動恢復。 |
| RIGHTS_CLEANUP_INCOMPLETE | high | llm§legal_shareholder_rights | 262 | 特別權利（包括購回權、反攤薄權、利潤分成權、董事提名權及知情權）僅在上市申請提交時終止購回權，其他特別權利於上市後終止，且若上市失敗或未在期限內上市則自動恢復，顯示上市前未完整解除。 | 首次公開發售前投資者已同意自本公司提交上市申請日期起終止其購回權。此外，首次公開發售前投資者已同意於上市後終止其他特別權利。倘發生下列情況...則特別權利將自動恢復。 |
| REDEMPTION_MEDIUM | medium | llm§legal_shareholder_rights | 497 | 贖回負債金額人民幣138.5百萬元，佔流動負債淨額比例高，可能影響財務穩健性，但董事認為未來十二個月不會有現金流出。 | 截至2025年8月31日，我們錄得流動負債淨額人民幣15.2百萬元，此乃主要由於普通股贖回負債人民幣138.5百萬元已入賬為流動負債，而其贖回權將於上市完成前一日自動終止。 |
| RELATED_PARTY_EXEMPTION | low | llm§legal_related_party | 424 | 關連交易獲完全豁免，但依賴豁免條件，需持續合規。 | 由於根據上市規則第十四A章個別及合計計算的HX301活性藥品成分及穩定性測試服務框架協議及原材料供應框架協議最高年度上限的最高適用百分比率（利潤比率除外）按年計預期低於5%且最高年度上限低於3,000,000港元，因此，於上市後，HX30… |
| RELATED_PARTY_TERM | medium | llm§legal_related_party | 416 | 協議期限超過三年，需依賴特殊情況豁免，存在合規風險。 | 上市規則第14A.52條規定，持續關連交易的協議期限不得超過三年，除非在特殊情況下，交易的性質要求較長的期限。董事認為，HX301活性藥品成分及穩定性測試服務框架協議的性質要求自協議日期起計的較長期間，並持續有效至2029年12月31日。 |
| RELATED_PARTY_APPROVAL | low | llm§legal_related_party | 425 | 非獲豁免交易需獨立股東批准，但當前交易已豁免，風險低。 | 倘無法取得獨立董事或獨立股東批准，我們將不會繼續進行框架協議項下交易，惟倘該等交易構成上市規則第14A.35條下的非獲豁免持續關連交易則除外。 |
| IP_PATENT_REJECTION_RISK | medium | llm§legal_contracts_and_ip | 386 | FcRn專利申請在中國被駁回，可能影響相關同族專利在其他司法權區的有效性，但法律顧問認為未必導致其他國家專利無效。 | 截至最後實際可行日期，中國國家知識產權局駁回了FcRn專利申請。然而，根據我們的中國知識產權法律顧問的意見，有關駁回未必會導致其同族專利／專利申請在其他國家／司法權區無效或被駁回。 |
| IP_MAINTENANCE_RISK | medium | llm§legal_contracts_and_ip | 93 | 專利維護需定期繳納費用並遵守程序，若未遵守可能導致專利放棄或失效，使競爭者進入市場。 | 不遵守規定可能會導致專利或專利申請被放棄或失效，從而部分或完全喪失在相關司法權區的專利權。可能導致專利或專利申請被放棄或失效的違規事件包括：未在規定時限內對官方行動作出回應、未支付費用，以及未適當合法化及提交正式文件。 |
| IP_THIRD_PARTY_CHALLENGE_RISK | medium | llm§legal_contracts_and_ip | 98 | 知識產權可能受到第三方質疑或失效，包括前僱員可能就專利產生潛在糾紛。 | 我們的知識產權（包括其他第三方轉讓或授權的知識產權）仍可能受到外部各方（包括但不限於我們的競爭對手及前僱員）質疑乃至失效。此外，本集團前僱員席先生可能與本公司就本公司的專利產生潛在糾紛。 |
| IP_INFRINGEMENT_CLAIM_RISK | low | llm§legal_contracts_and_ip | 386 | 法律顧問認為目前無侵犯第三方知識產權的重大風險，但未來可能因侵權申索而需訴訟，且可能無法及時發現侵權行為。 | 我們的中國知識產權法律顧問認為於往績記錄期間及直至最後實際可行日期，本集團並無因侵犯第三方知識產權而面臨任何法律、仲裁或行政程序。 |
| REGULATORY_PENALTY | medium | llm§legal_regulatory_litigation | 403 | 社會保險及住房公積金供款不足，可能被主管機關罰款或徵收滯納金，但公司已承諾補繳，風險相對較小。 | 鑒於本公司承諾並保證在接獲主管部門的社會保險供款通知後將按照相關部門的要求及時補繳，本公司在該解釋實施後因上述事項受到主管機關罰款的風險相對較小。 |
| REGULATORY_INVESTIGATION | medium | llm§legal_regulatory_litigation | 85 | 政府對涉嫌違法行為的調查可能耗費大量時間及資源，並產生負面影響，但未指明具體調查事項。 | 政府對涉嫌違法行為的任何調查均可能耗費我們大量的時間及資源，並可能產生負面影響。 |
| REGULATORY_COMPLIANCE | medium | llm§legal_regulatory_litigation | 83 | 生物製藥行業監管架構變化可能增加合規成本，或導致延遲或阻止候選藥物開發，若未能遵守監管要求可能面臨制裁。 | 獲得監管批准及遵守相關法律法規需要花費大量的時間及資金。在藥物開發或審批過程中的任何時候，或在審批之後，若我們未能遵守我們營運或未來目標營運所在司法權區的相應監管要求，我們可能會因此面臨爭議、行政制裁、刑事制裁及其他法律訴訟。 |
| HUMAN_GENETIC_RESOURCE | medium | llm§legal_regulatory_litigation | 86 | 在利用及處理中國人類遺傳資源時，可能未能完全遵守《人類遺傳資源條例》及《生物安全法》，存在合規風險。 | 我們無法向閣下保證，在利用及處理中國人類遺傳資源時，我們將始終被視為完全遵守《人類遺傳資源條例》、《中華人民共和國生物安全法》以及其他適用法律。因此，我們可能面臨著《人類遺傳資源條例》以及《中華人民共和國生物安全法》項下的合規風險。 |
| LITIGATION_ABSENT | low | llm§legal_regulatory_litigation | 406 | 截至最後實際可行日期，公司或董事未涉及重大訴訟、仲裁或行政程序，且無未決或可能提起的訴訟。 | 於往績記錄期間及直至最後實際可行日期，我們或任何董事概未牽涉或面臨任何可能對我們的業務、財務狀況或整體經營業績產生重大不利影響的重大訴訟、仲裁、行政程序、申索、損害或損失。 |
| RELATED_PARTY_DISCLOSURE | medium | doc§3.2 | 30 | 存在关联交易披露 | 我們已與中美華世通生物醫藥科技訂立若干交易，該等交易於上市後將構成持續關連交易。有關我們與中美華世通生物醫藥科技的持續關連交易的進一步詳情，請參閱本招股章程「關連交易」一節。 |
| CONCENTRATION_DISCLOSURE | medium | doc§3.3 | 28 | 存在客户/供应商集中度披露 | 截至2023年及2024年12月31日止年度及截至2025年8月31日止八個月，五大供應商應佔總採購額分別約為人民幣16.3百萬元、人民幣28.6百萬元及人民幣23.3百萬元，分別佔我們總採購額約51.8%、37.4%及45.5%。同期，… |
| PIPELINE_DISCLOSURE | medium | doc§3.5 | 16 | 存在核心产品/管线进度披露 | 除HX301乃自Onconova Therapeutics, Inc.授權引進外，我們的管線候選產品全部由我們自主研發。我們構建產品管線，旨在利用先天及適應性免疫實現潛在協同效應。我們的產品管線旨在解決現有檢查點抑制劑免疫療法的局限性，包… |

### 5.1 质量疑点（人工复核建议）

- **`GOVERNANCE_CONTROL_GT_50`**：控股~55.89% 在港股 IPO 很常见；标 high 且 legal_basis 扯十四A章略牵强（dossier 亦如此）。
- **`REGULATORY_INVESTIGATION`**：招股书通用风险因素表述，未必等于发行人正被调查；level=medium/+18 可能偏重。
- **`LITIGATION_ABSENT`**：描述为「无重大诉讼」，却作为加分风险计入（+3），更宜作 negative_finding。

- 与 Gemma/规则基线 **51/medium** 对比：本轮把大量 LLM 点直接累加至满分，**校准不足**；预警展示建议用「主题去重后的参考分」或总控再融合，而不是直接采用 100。
- 正向发现（如无重大诉讼）不应进入加分 breakdown。

---

## 6. 辩论素材包

- dossier_id：`fa6b2975-22c9-4e58-b064-7396481c71e2`
- claims：21；negative_findings：0
- 路径：`.runtime/debate/hansiaitai_legal_dossier_20260804_223352.json`

每条 claim 含 `statement` / `legal_basis` / `evidence_refs` / `reasoning`，可供总控辩论；本轮 negative_findings 为空（「无诉讼」被误放进 claims）。

---

## 7. 分析结论

1. **编排成功**：无规则整段回退；二阶段 search 配额与路径约束有效；DeepSeek 并行 skill 效率高。  
2. **证据与叙述**：多数点有页码与原文摘录，赎回/特别权利/控股比例等核心点可读性强，优于 Gemma 基线「空 Skill」。  
3. **评分不可直接采信**：100/very_high 相对规则基线 51 明显过激；存在通用风险因素误伤与「无诉讼」加分。  
4. **过程浪费**：t4–t5 空转约占 ReAct token 近半，后续可对「hint 已要求 submit」做强制 tool_choice / 缩短 reasoning。  
5. **建议下一步**：对 score_rules 做 LLM 点权重校准与主题去重；把 ABSENT/无风险类写入 negative_findings；空转轮硬截断。

---

## 8. 复现命令

```bash
cd agents/hk_ipo_risk
python scripts/run_finance_legal.py --agent legal \
  --doc-id hansiaitai --doc-name 翰思艾泰 \
  --pdf-name "03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf" \
  --issuer-type 18a \
  --parse-json "/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/03378_15-12-2025_翰思艾泰－Ｂ_全球發售/full_parse.json" \
  --retrieval-legal-json /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json \
  --provider deepseek --chat-model deepseek-v4-flash \
  --max-turns 8 \
  --out .runtime/hansiaitai_legal_deepseek_flash.json

python scripts/generate_analysis_report.py \
  --result .runtime/hansiaitai_legal_deepseek_flash.json \
  --doc-name 翰思艾泰 \
  --pdf-name "03378_15-12-2025_翰思艾泰－Ｂ_全球發售.pdf" \
  --legal-retrieval /nfs/users/wuqianqian/IPOI/retrieval/.runtime/agent_retrieval_hansiaitai_legal.json \
  --out reports/hansiaitai_legal_deepseek_flash_report.md
```
