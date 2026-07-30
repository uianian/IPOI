# 解析质量 QA 报告

- 输入: `/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/xiaomi/full_parse.json`
- 总页数: 697
- 问题条数: 68
- 建议重跑: `28,37,48,114,115,116,121,154,281,338,373,402,447,448,469,471,501,505,506,507,557,697`

## 按标签统计

| 标签 | 次数 |
| --- | ---: |
| `table_structure_medium` | 45 |
| `vertical_table_low_structure` | 13 |
| `missing_table_high_numeric` | 8 |
| `parse_failed` | 1 |
| `empty_page` | 1 |

## 问题明细

- **p15** `table_structure_medium` [low] score=1114, notes=['complex_colspan_header']
- **p22** `table_structure_medium` [low] score=3151, notes=['complex_colspan_header']
- **p23** `table_structure_medium` [low] score=439, notes=['sparse_table']
- **p24** `table_structure_medium` [low] score=1803, notes=['sparse_table']
- **p28** `vertical_table_low_structure` [high] score=423, notes=['truncated_or_header_only']
- **p36** `table_structure_medium` [low] score=647, notes=['sparse_table']
- **p37** `vertical_table_low_structure` [high] score=125, notes=['truncated_or_header_only']
- **p48** `vertical_table_low_structure` [high] score=423, notes=['truncated_or_header_only']
- **p51** `table_structure_medium` [low] score=727, notes=['sparse_table']
- **p114** `vertical_table_low_structure` [high] score=427, notes=['truncated_or_header_only']
- **p115** `vertical_table_low_structure` [high] score=442, notes=['truncated_or_header_only']
- **p116** `vertical_table_low_structure` [high] score=321, notes=['truncated_or_header_only']
- **p121** `vertical_table_low_structure` [high] score=320, notes=['truncated_or_header_only']
- **p125** `table_structure_medium` [low] score=665, notes=['sparse_table']
- **p153** `table_structure_medium` [low] score=722, notes=['sparse_table']
- **p154** `vertical_table_low_structure` [high] score=209, notes=['truncated_or_header_only']
- **p155** `table_structure_medium` [low] score=446, notes=['sparse_table']
- **p157** `table_structure_medium` [low] score=531, notes=['sparse_table']
- **p191** `table_structure_medium` [low] score=872, notes=['sparse_table']
- **p192** `table_structure_medium` [low] score=428, notes=['sparse_table']
- **p222** `table_structure_medium` [low] score=1114, notes=['complex_colspan_header']
- **p225** `table_structure_medium` [low] score=1275, notes=['complex_colspan_header']
- **p236** `table_structure_medium` [low] score=1286, notes=['complex_colspan_header']
- **p238** `table_structure_medium` [low] score=745, notes=['sparse_table']
- **p240** `table_structure_medium` [low] score=760, notes=['sparse_table']
- **p268** `table_structure_medium` [low] score=470, notes=['sparse_table']
- **p281** `vertical_table_low_structure` [high] score=215, notes=['truncated_or_header_only']
- **p320** `table_structure_medium` [low] score=3358, notes=['complex_colspan_header']
- **p321** `table_structure_medium` [low] score=1483, notes=['complex_colspan_header']
- **p322** `table_structure_medium` [low] score=947, notes=['complex_colspan_header']
- **p323** `table_structure_medium` [low] score=845, notes=['complex_colspan_header']
- **p324** `table_structure_medium` [low] score=1483, notes=['complex_colspan_header']
- **p325** `table_structure_medium` [low] score=1380, notes=['complex_colspan_header']
- **p329** `table_structure_medium` [low] score=1199, notes=['complex_colspan_header']
- **p330** `table_structure_medium` [low] score=576, notes=['complex_colspan_header']
- **p332** `table_structure_medium` [low] score=679, notes=['complex_colspan_header']
- **p333** `table_structure_medium` [low] score=450, notes=['sparse_table']
- **p338** `missing_table_high_numeric` [high] 无 table，text 中约 33 个数值字段、16 行
- **p347** `table_structure_medium` [low] score=331, notes=['sparse_table']
- **p348** `table_structure_medium` [low] score=1173, notes=['sparse_table']
- **p353** `table_structure_medium` [low] score=1066, notes=['sparse_table']
- **p366** `table_structure_medium` [low] score=475, notes=['sparse_table']
- **p373** `vertical_table_low_structure` [high] score=875, notes=['truncated_or_header_only']
- **p389** `table_structure_medium` [low] score=448, notes=['sparse_table']
- **p390** `table_structure_medium` [low] score=431, notes=['sparse_table']
- **p402** `vertical_table_low_structure` [high] score=1620, notes=['rotated_table_structure_unstable']
- **p409** `table_structure_medium` [low] score=654, notes=['sparse_table']
- **p447** `vertical_table_low_structure` [high] score=414, notes=['truncated_or_header_only']
- **p448** `vertical_table_low_structure` [high] score=519, notes=['sparse_table', 'truncated_or_header_only']
- **p469** `missing_table_high_numeric` [high] 无 table，text 中约 95 个数值字段、158 行
- **p471** `missing_table_high_numeric` [high] 无 table，text 中约 62 个数值字段、112 行
- **p480** `table_structure_medium` [low] score=634, notes=['sparse_table']
- **p501** `missing_table_high_numeric` [high] 无 table，text 中约 30 个数值字段、15 行
- **p505** `missing_table_high_numeric` [high] 无 table，text 中约 76 个数值字段、52 行
- **p506** `missing_table_high_numeric` [high] 无 table，text 中约 45 个数值字段、29 行
- **p507** `missing_table_high_numeric` [high] 无 table，text 中约 51 个数值字段、37 行
- **p518** `table_structure_medium` [low] score=639, notes=['sparse_table']
- **p528** `table_structure_medium` [low] score=1615, notes=['complex_colspan_header']
- **p545** `table_structure_medium` [low] score=1201, notes=['sparse_table']
- **p557** `missing_table_high_numeric` [high] 无 table，text 中约 43 个数值字段、37 行
- **p568** `table_structure_medium` [low] score=757, notes=['sparse_table']
- **p578** `table_structure_medium` [low] score=475, notes=['sparse_table']
- **p641** `table_structure_medium` [low] score=660, notes=['sparse_table']
- **p649** `table_structure_medium` [low] score=241, notes=['sparse_table']
- **p651** `table_structure_medium` [low] score=754, notes=['sparse_table']
- **p664** `table_structure_medium` [low] score=237, notes=['sparse_table']
- **p697** `parse_failed` [high] parse_status=failed
- **p697** `empty_page` [high] elements 为空
