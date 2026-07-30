# 解析质量 QA 报告

- 输入: `/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/01147_23-04-2020_伊登軟件_股份發售/full_parse.json`
- 总页数: 458
- 问题条数: 49
- 建议重跑: `30,120,131,160,185,216,222,281,306,336,337,392,393,439`

## 按标签统计

| 标签 | 次数 |
| --- | ---: |
| `table_structure_medium` | 34 |
| `vertical_table_low_structure` | 13 |
| `truncated` | 1 |
| `missing_table_high_numeric` | 1 |

## 问题明细

- **p7** `truncated` [medium] 模型输出被截断修复
- **p15** `table_structure_medium` [low] score=763, notes=['sparse_table']
- **p30** `vertical_table_low_structure` [high] score=124, notes=['truncated_or_header_only']
- **p96** `table_structure_medium` [low] score=639, notes=['sparse_table']
- **p120** `vertical_table_low_structure` [high] score=868, notes=['rotated_table_structure_unstable']
- **p128** `table_structure_medium` [low] score=571, notes=['sparse_table']
- **p131** `vertical_table_low_structure` [high] score=330, notes=['truncated_or_header_only']
- **p154** `table_structure_medium` [low] score=775, notes=['sparse_table']
- **p156** `table_structure_medium` [low] score=770, notes=['sparse_table']
- **p159** `table_structure_medium` [low] score=463, notes=['sparse_table']
- **p160** `vertical_table_low_structure` [high] score=2549, notes=['rotated_table_structure_unstable']
- **p178** `table_structure_medium` [low] score=778, notes=['sparse_table']
- **p179** `table_structure_medium` [low] score=778, notes=['sparse_table']
- **p180** `table_structure_medium` [low] score=772, notes=['sparse_table']
- **p181** `table_structure_medium` [low] score=772, notes=['sparse_table']
- **p183** `table_structure_medium` [low] score=660, notes=['sparse_table']
- **p185** `vertical_table_low_structure` [high] score=310, notes=['truncated_or_header_only']
- **p216** `vertical_table_low_structure` [high] score=326, notes=['truncated_or_header_only']
- **p218** `table_structure_medium` [low] score=530, notes=['sparse_table']
- **p222** `vertical_table_low_structure` [high] score=659, notes=['truncated_or_header_only', 'sparse_table']
- **p226** `table_structure_medium` [low] score=771, notes=['sparse_table']
- **p227** `table_structure_medium` [low] score=434, notes=['sparse_table']
- **p269** `table_structure_medium` [low] score=456, notes=['sparse_table']
- **p272** `table_structure_medium` [low] score=539, notes=['sparse_table']
- **p275** `table_structure_medium` [low] score=827, notes=['sparse_table']
- **p281** `missing_table_high_numeric` [high] 无 table，text 中约 31 个数值字段、18 行
- **p306** `vertical_table_low_structure` [high] score=413, notes=['truncated_or_header_only']
- **p336** `vertical_table_low_structure` [high] score=2620, notes=['colspan_year_mismatch']
- **p337** `vertical_table_low_structure` [high] score=535, notes=['truncated_or_header_only', 'sparse_table']
- **p363** `table_structure_medium` [low] score=770, notes=['sparse_table']
- **p365** `table_structure_medium` [low] score=579, notes=['sparse_table']
- **p367** `table_structure_medium` [low] score=341, notes=['sparse_table']
- **p371** `table_structure_medium` [low] score=568, notes=['sparse_table']
- **p373** `table_structure_medium` [low] score=851, notes=['sparse_table']
- **p375** `table_structure_medium` [low] score=744, notes=['sparse_table']
- **p376** `table_structure_medium` [low] score=817, notes=['sparse_table']
- **p377** `table_structure_medium` [low] score=697, notes=['sparse_table']
- **p382** `table_structure_medium` [low] score=632, notes=['sparse_table']
- **p385** `table_structure_medium` [low] score=1922, notes=['sparse_table']
- **p386** `table_structure_medium` [low] score=827, notes=['sparse_table']
- **p387** `table_structure_medium` [low] score=640, notes=['sparse_table']
- **p391** `table_structure_medium` [low] score=667, notes=['sparse_table']
- **p392** `vertical_table_low_structure` [high] score=220, notes=['truncated_or_header_only']
- **p393** `vertical_table_low_structure` [high] score=321, notes=['truncated_or_header_only']
- **p400** `table_structure_medium` [low] score=234, notes=['sparse_table']
- **p439** `vertical_table_low_structure` [high] score=214, notes=['truncated_or_header_only']
- **p440** `table_structure_medium` [low] score=761, notes=['sparse_table']
- **p441** `table_structure_medium` [low] score=434, notes=['sparse_table']
- **p454** `table_structure_medium` [low] score=719, notes=['sparse_table']
