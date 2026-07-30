Financial Agent Skill Architecture

Financial Agent



├── Profitability Skill

│

├── Growth Quality Skill

│

├── Cash Flow Skill

│

├── Solvency Skill

│

├── Business Model Skill

│

└── IPO Valuation Skill

Skill 1：盈利能力分析（已有，需要增强）

输入Feature



已有：



REV

GP

GP\_MARGIN

NET\_LOSS

ADJ\_NET



增加：

ROE

ROE = Net Profit / Equity



判断：



企业是否依靠资本投入产生收益。



利润质量



增加：



Net Profit

\-

Operating Cash Flow



如果：



利润增长，但是现金流下降：



风险。



例如：



净利润+30%

CFO-50%



↓



利润可能依赖:

应收账款

一次性收益

Skill 2：收入质量分析（强烈建议增加）



这是目前缺失最大的模块。



很多IPO最大风险不是亏损，而是：



收入增长不可持续。



增加：



Revenue Quality



Feature：



收入来源



抽取：



主营收入来源

客户类型

商业模式



例如：



蜜雪：



加盟商采购收入

\+

直营收入

收入集中度



已有客户集中：



但建议扩展：



不仅客户集中：



还分析：



产品集中

地区集中

渠道集中



例如：



新能源：



收入80%来自某车型



风险:

产品生命周期风险

Skill 3：现金流风险（已有，但应该从18A中抽离）



当前：



现金消耗压力放在非标风险中。



建议：



所有企业都分析：



Cash Flow Skill



不仅18A。



指标：



CFO



Free Cash Flow



Cash Runway



Burn Rate



风险：



指标	风险

连续CFO为负	经营风险

现金下降	流动性风险

融资依赖	持续经营风险

Skill 4：偿债能力分析（新增）



目前资产负债表只是抽取，没有风险解释。



已有：



TOTAL\_ASSETS

TOTAL\_LIAB

CASH

应收

应付



增加：



Debt Risk



指标：



资产负债率

Liability / Asset

流动比率

Current Asset / Current Liability

应收风险

AR Growth > Revenue Growth



风险：



应收快速增长

↓

收入可能虚增

Skill 5：商业模式风险（非常建议增加）



这是目前最大缺陷。



财务Agent不能只看财务表。



IPO风险很多来自商业模式。



例如：



蜜雪：



加盟模式

↓

门店快速扩张

↓

加盟商质量

↓

收入稳定性



Feature:



BUSINESS\_MODEL



加盟比例



直营比例



平台依赖



供应链依赖

Skill 6：估值风险（已有，需要扩展）



已有：



IPO vs Pre-IPO估值。



增加：



PE/PB异常

同行业估值比较



例如：



IPO PE

行业平均PE



偏离>50%



风险

