# 解析质量 QA 报告

- 输入: `/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/02097_21-02-2025_蜜雪集團_全球發售/full_parse.json`
- 总页数: 558
- 问题条数: 61
- 建议重跑: `52,114,124,140,217,273,274,275,415,430,431,494,548,550`

## 按标签统计

| 标签 | 次数 |
| --- | ---: |
| `table_structure_medium` | 47 |
| `vertical_table_low_structure` | 12 |
| `missing_table_high_numeric` | 2 |

## 问题明细

- **p26** `table_structure_medium` [low] score=505, notes=['sparse_table']
- **p27** `table_structure_medium` [low] score=3187, notes=['complex_colspan_header']
- **p30** `table_structure_medium` [low] score=747, notes=['sparse_table']
- **p52** `vertical_table_low_structure` [high] score=412, notes=['truncated_or_header_only']
- **p114** `vertical_table_low_structure` [high] score=421, notes=['truncated_or_header_only']
- **p124** `vertical_table_low_structure` [high] score=418, notes=['truncated_or_header_only']
- **p125** `table_structure_medium` [low] score=627, notes=['sparse_table']
- **p126** `table_structure_medium` [low] score=623, notes=['sparse_table']
- **p127** `table_structure_medium` [low] score=626, notes=['sparse_table']
- **p129** `table_structure_medium` [low] score=735, notes=['sparse_table']
- **p132** `table_structure_medium` [low] score=623, notes=['sparse_table']
- **p134** `table_structure_medium` [low] score=626, notes=['sparse_table']
- **p135** `table_structure_medium` [low] score=623, notes=['sparse_table']
- **p136** `table_structure_medium` [low] score=631, notes=['sparse_table']
- **p140** `vertical_table_low_structure` [high] score=415, notes=['truncated_or_header_only']
- **p175** `table_structure_medium` [low] score=520, notes=['sparse_table']
- **p181** `table_structure_medium` [low] score=645, notes=['sparse_table']
- **p213** `table_structure_medium` [low] score=1113, notes=['complex_colspan_header']
- **p217** `vertical_table_low_structure` [high] score=1044, notes=['rotated_table_structure_unstable']
- **p220** `table_structure_medium` [low] score=744, notes=['sparse_table']
- **p242** `table_structure_medium` [low] score=1458, notes=['complex_colspan_header']
- **p273** `vertical_table_low_structure` [high] score=688, notes=['truncated_or_header_only']
- **p274** `vertical_table_low_structure` [high] score=689, notes=['truncated_or_header_only']
- **p275** `vertical_table_low_structure` [high] score=688, notes=['truncated_or_header_only']
- **p290** `table_structure_medium` [low] score=554, notes=['sparse_table']
- **p294** `table_structure_medium` [low] score=451, notes=['sparse_table']
- **p313** `table_structure_medium` [low] score=535, notes=['sparse_table']
- **p325** `table_structure_medium` [low] score=612, notes=['sparse_table']
- **p327** `table_structure_medium` [low] score=2874, notes=['complex_colspan_header']
- **p329** `table_structure_medium` [low] score=1321, notes=['complex_colspan_header']
- **p330** `table_structure_medium` [low] score=1347, notes=['complex_colspan_header']
- **p331** `table_structure_medium` [low] score=1053, notes=['sparse_table', 'complex_colspan_header']
- **p333** `table_structure_medium` [low] score=1483, notes=['complex_colspan_header']
- **p334** `table_structure_medium` [low] score=1605, notes=['complex_colspan_header']
- **p349** `table_structure_medium` [low] score=827, notes=['sparse_table']
- **p354** `table_structure_medium` [low] score=1054, notes=['sparse_table']
- **p365** `table_structure_medium` [low] score=747, notes=['sparse_table']
- **p369** `table_structure_medium` [low] score=756, notes=['sparse_table']
- **p407** `table_structure_medium` [low] score=339, notes=['sparse_table']
- **p415** `vertical_table_low_structure` [high] score=871, notes=['truncated_or_header_only']
- **p418** `table_structure_medium` [low] score=545, notes=['sparse_table']
- **p430** `missing_table_high_numeric` [high] 无 table，text 中约 100 个数值字段、37 行
- **p431** `missing_table_high_numeric` [high] 无 table，text 中约 48 个数值字段、81 行
- **p446** `table_structure_medium` [low] score=612, notes=['sparse_table']
- **p466** `table_structure_medium` [low] score=909, notes=['sparse_table']
- **p477** `table_structure_medium` [low] score=1583, notes=['sparse_table']
- **p481** `table_structure_medium` [low] score=1098, notes=['sparse_table']
- **p482** `table_structure_medium` [low] score=2198, notes=['sparse_table']
- **p485** `table_structure_medium` [low] score=710, notes=['sparse_table']
- **p487** `table_structure_medium` [low] score=1480, notes=['sparse_table']
- **p494** `vertical_table_low_structure` [high] score=836, notes=['sparse_table', 'truncated_or_header_only']
- **p496** `table_structure_medium` [low] score=930, notes=['sparse_table']
- **p497** `table_structure_medium` [low] score=1123, notes=['sparse_table']
- **p498** `table_structure_medium` [low] score=1247, notes=['sparse_table']
- **p499** `table_structure_medium` [low] score=1248, notes=['sparse_table']
- **p507** `table_structure_medium` [low] score=632, notes=['sparse_table']
- **p547** `table_structure_medium` [low] score=877, notes=['sparse_table']
- **p548** `vertical_table_low_structure` [high] score=726, notes=['sparse_table', 'truncated_or_header_only']
- **p549** `table_structure_medium` [low] score=646, notes=['sparse_table']
- **p550** `vertical_table_low_structure` [high] score=422, notes=['truncated_or_header_only']
- **p553** `table_structure_medium` [low] score=734, notes=['sparse_table']
