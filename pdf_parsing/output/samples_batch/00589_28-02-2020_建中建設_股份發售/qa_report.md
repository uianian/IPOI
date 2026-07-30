# 解析质量 QA 报告

- 输入: `/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/00589_28-02-2020_建中建設_股份發售/full_parse.json`
- 总页数: 566
- 问题条数: 87
- 建议重跑: `21,126,137,166,167,180,183,222,224,252,271,272,274,358,454,455,531,543`

## 按标签统计

| 标签 | 次数 |
| --- | ---: |
| `table_structure_medium` | 68 |
| `vertical_table_low_structure` | 16 |
| `missing_table_high_numeric` | 2 |
| `truncated` | 1 |

## 问题明细

- **p10** `table_structure_medium` [low] score=2336, notes=['complex_colspan_header']
- **p11** `table_structure_medium` [low] score=880, notes=['sparse_table']
- **p12** `table_structure_medium` [low] score=1350, notes=['complex_colspan_header']
- **p21** `vertical_table_low_structure` [high] score=319, notes=['truncated_or_header_only']
- **p99** `table_structure_medium` [low] score=435, notes=['sparse_table']
- **p100** `table_structure_medium` [low] score=648, notes=['sparse_table']
- **p101** `table_structure_medium` [low] score=648, notes=['sparse_table']
- **p102** `table_structure_medium` [low] score=445, notes=['sparse_table']
- **p126** `vertical_table_low_structure` [high] score=217, notes=['truncated_or_header_only']
- **p127** `table_structure_medium` [low] score=645, notes=['sparse_table']
- **p136** `table_structure_medium` [low] score=2050, notes=['sparse_table']
- **p137** `vertical_table_low_structure` [high] score=801, notes=['truncated_or_header_only']
- **p138** `table_structure_medium` [low] score=631, notes=['sparse_table']
- **p163** `table_structure_medium` [low] score=728, notes=['sparse_table']
- **p166** `vertical_table_low_structure` [high] score=631, notes=['sparse_table', 'truncated_or_header_only']
- **p167** `vertical_table_low_structure` [high] score=952, notes=['truncated_or_header_only']
- **p180** `vertical_table_low_structure` [high] score=1154, notes=['rotated_table_structure_unstable']
- **p182** `table_structure_medium` [low] score=873, notes=['complex_colspan_header', 'sparse_table']
- **p183** `vertical_table_low_structure` [high] score=795, notes=['truncated_or_header_only']
- **p186** `table_structure_medium` [low] score=1049, notes=['complex_colspan_header']
- **p189** `table_structure_medium` [low] score=697, notes=['sparse_table']
- **p192** `table_structure_medium` [low] score=772, notes=['sparse_table']
- **p193** `table_structure_medium` [low] score=775, notes=['sparse_table']
- **p200** `table_structure_medium` [low] score=652, notes=['sparse_table']
- **p201** `table_structure_medium` [low] score=661, notes=['sparse_table']
- **p207** `truncated` [medium] 模型输出被截断修复
- **p207** `table_structure_medium` [low] score=539, notes=['sparse_table']
- **p215** `table_structure_medium` [low] score=765, notes=['sparse_table']
- **p216** `table_structure_medium` [low] score=765, notes=['sparse_table']
- **p217** `table_structure_medium` [low] score=764, notes=['sparse_table']
- **p218** `table_structure_medium` [low] score=765, notes=['sparse_table']
- **p221** `table_structure_medium` [low] score=541, notes=['sparse_table']
- **p222** `vertical_table_low_structure` [high] score=866, notes=['truncated_or_header_only']
- **p223** `table_structure_medium` [low] score=550, notes=['sparse_table']
- **p224** `vertical_table_low_structure` [high] score=322, notes=['truncated_or_header_only']
- **p233** `table_structure_medium` [low] score=621, notes=['sparse_table']
- **p236** `table_structure_medium` [low] score=641, notes=['sparse_table']
- **p246** `table_structure_medium` [low] score=867, notes=['sparse_table']
- **p247** `table_structure_medium` [low] score=658, notes=['sparse_table']
- **p252** `vertical_table_low_structure` [high] score=438, notes=['truncated_or_header_only']
- **p264** `table_structure_medium` [low] score=664, notes=['sparse_table']
- **p267** `table_structure_medium` [low] score=653, notes=['sparse_table']
- **p271** `vertical_table_low_structure` [high] score=207, notes=['truncated_or_header_only']
- **p272** `vertical_table_low_structure` [high] score=207, notes=['truncated_or_header_only']
- **p274** `vertical_table_low_structure` [high] score=207, notes=['truncated_or_header_only']
- **p276** `table_structure_medium` [low] score=762, notes=['sparse_table']
- **p279** `table_structure_medium` [low] score=545, notes=['sparse_table']
- **p282** `table_structure_medium` [low] score=444, notes=['sparse_table']
- **p283** `table_structure_medium` [low] score=331, notes=['sparse_table']
- **p301** `table_structure_medium` [low] score=1092, notes=['complex_colspan_header']
- **p302** `table_structure_medium` [low] score=1187, notes=['complex_colspan_header']
- **p305** `table_structure_medium` [low] score=2727, notes=['complex_colspan_header']
- **p306** `table_structure_medium` [low] score=2245, notes=['complex_colspan_header']
- **p309** `table_structure_medium` [low] score=1110, notes=['complex_colspan_header']
- **p312** `table_structure_medium` [low] score=1693, notes=['complex_colspan_header']
- **p334** `table_structure_medium` [low] score=434, notes=['sparse_table']
- **p335** `table_structure_medium` [low] score=537, notes=['sparse_table']
- **p337** `table_structure_medium` [low] score=660, notes=['sparse_table']
- **p338** `table_structure_medium` [low] score=695, notes=['sparse_table']
- **p341** `table_structure_medium` [low] score=1076, notes=['sparse_table']
- **p346** `table_structure_medium` [low] score=365, notes=['sparse_table']
- **p347** `table_structure_medium` [low] score=2106, notes=['sparse_table']
- **p354** `table_structure_medium` [low] score=574, notes=['sparse_table']
- **p355** `table_structure_medium` [low] score=362, notes=['sparse_table']
- **p356** `table_structure_medium` [low] score=544, notes=['sparse_table']
- **p357** `table_structure_medium` [low] score=513, notes=['sparse_table']
- **p358** `vertical_table_low_structure` [high] score=211, notes=['truncated_or_header_only']
- **p361** `table_structure_medium` [low] score=646, notes=['sparse_table']
- **p399** `table_structure_medium` [low] score=620, notes=['sparse_table']
- **p450** `table_structure_medium` [low] score=838, notes=['sparse_table']
- **p451** `table_structure_medium` [low] score=1246, notes=['sparse_table']
- **p452** `table_structure_medium` [low] score=857, notes=['sparse_table']
- **p454** `missing_table_high_numeric` [high] 无 table，text 中约 32 个数值字段、25 行
- **p455** `missing_table_high_numeric` [high] 无 table，text 中约 40 个数值字段、33 行
- **p457** `table_structure_medium` [low] score=1033, notes=['sparse_table']
- **p460** `table_structure_medium` [low] score=1342, notes=['sparse_table']
- **p470** `table_structure_medium` [low] score=790, notes=['sparse_table']
- **p471** `table_structure_medium` [low] score=1428, notes=['sparse_table']
- **p472** `table_structure_medium` [low] score=630, notes=['sparse_table']
- **p476** `table_structure_medium` [low] score=660, notes=['sparse_table']
- **p481** `table_structure_medium` [low] score=455, notes=['sparse_table']
- **p486** `table_structure_medium` [low] score=643, notes=['sparse_table']
- **p530** `table_structure_medium` [low] score=468, notes=['sparse_table']
- **p531** `vertical_table_low_structure` [high] score=814, notes=['truncated_or_header_only']
- **p543** `vertical_table_low_structure` [high] score=704, notes=['truncated_or_header_only', 'sparse_table']
- **p544** `table_structure_medium` [low] score=435, notes=['sparse_table']
- **p545** `table_structure_medium` [low] score=635, notes=['sparse_table']
