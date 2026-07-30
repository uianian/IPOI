# 解析质量 QA 报告

- 输入: `/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/qiniu/full_parse.json`
- 总页数: 666
- 问题条数: 69
- 建议重跑: `4,212,216,263,264,276,311,314,316,344,347,358,360,539,541,562,577,582,584,585,586`

## 按标签统计

| 标签 | 次数 |
| --- | ---: |
| `table_structure_medium` | 48 |
| `vertical_table_low_structure` | 20 |
| `missing_table_high_numeric` | 1 |

## 问题明细

- **p4** `vertical_table_low_structure` [high] score=1993, notes=['colspan_year_mismatch']
- **p18** `table_structure_medium` [low] score=2411, notes=['complex_colspan_header']
- **p19** `table_structure_medium` [low] score=614, notes=['sparse_table']
- **p30** `table_structure_medium` [low] score=539, notes=['sparse_table']
- **p137** `table_structure_medium` [low] score=636, notes=['sparse_table']
- **p186** `table_structure_medium` [low] score=541, notes=['sparse_table']
- **p191** `table_structure_medium` [low] score=570, notes=['sparse_table']
- **p192** `table_structure_medium` [low] score=610, notes=['sparse_table']
- **p205** `table_structure_medium` [low] score=734, notes=['sparse_table']
- **p212** `vertical_table_low_structure` [high] score=427, notes=['truncated_or_header_only']
- **p216** `vertical_table_low_structure` [high] score=407, notes=['truncated_or_header_only']
- **p255** `table_structure_medium` [low] score=1177, notes=['complex_colspan_header']
- **p263** `vertical_table_low_structure` [high] score=311, notes=['truncated_or_header_only']
- **p264** `vertical_table_low_structure` [high] score=233, notes=['sparse_table', 'truncated_or_header_only']
- **p265** `table_structure_medium` [low] score=1174, notes=['sparse_table']
- **p275** `table_structure_medium` [low] score=633, notes=['sparse_table']
- **p276** `vertical_table_low_structure` [high] score=522, notes=['truncated_or_header_only', 'sparse_table']
- **p278** `table_structure_medium` [low] score=767, notes=['sparse_table']
- **p295** `table_structure_medium` [low] score=650, notes=['sparse_table']
- **p296** `table_structure_medium` [low] score=494, notes=['sparse_table']
- **p310** `table_structure_medium` [low] score=561, notes=['sparse_table']
- **p311** `vertical_table_low_structure` [high] score=222, notes=['truncated_or_header_only']
- **p314** `vertical_table_low_structure` [high] score=464, notes=['truncated_or_header_only', 'sparse_table']
- **p315** `table_structure_medium` [low] score=345, notes=['sparse_table']
- **p316** `vertical_table_low_structure` [high] score=462, notes=['sparse_table', 'truncated_or_header_only']
- **p317** `table_structure_medium` [low] score=563, notes=['sparse_table']
- **p326** `table_structure_medium` [low] score=769, notes=['sparse_table']
- **p340** `table_structure_medium` [low] score=644, notes=['sparse_table']
- **p343** `table_structure_medium` [low] score=336, notes=['sparse_table']
- **p344** `vertical_table_low_structure` [high] score=323, notes=['truncated_or_header_only']
- **p347** `vertical_table_low_structure` [high] score=214, notes=['truncated_or_header_only']
- **p358** `vertical_table_low_structure` [high] score=442, notes=['sparse_table', 'truncated_or_header_only']
- **p360** `vertical_table_low_structure` [high] score=453, notes=['sparse_table', 'truncated_or_header_only']
- **p374** `table_structure_medium` [low] score=358, notes=['sparse_table']
- **p396** `table_structure_medium` [low] score=541, notes=['sparse_table']
- **p398** `table_structure_medium` [low] score=1029, notes=['sparse_table']
- **p409** `table_structure_medium` [low] score=539, notes=['sparse_table']
- **p426** `table_structure_medium` [low] score=331, notes=['sparse_table']
- **p428** `table_structure_medium` [low] score=534, notes=['sparse_table']
- **p430** `table_structure_medium` [low] score=710, notes=['sparse_table']
- **p443** `table_structure_medium` [low] score=436, notes=['sparse_table']
- **p479** `table_structure_medium` [low] score=339, notes=['sparse_table']
- **p539** `vertical_table_low_structure` [high] score=1402, notes=['truncated_or_header_only']
- **p541** `vertical_table_low_structure` [high] score=333, notes=['truncated_or_header_only', 'sparse_table']
- **p543** `table_structure_medium` [low] score=547, notes=['sparse_table']
- **p553** `table_structure_medium` [low] score=647, notes=['complex_colspan_header', 'sparse_table']
- **p554** `table_structure_medium` [low] score=808, notes=['sparse_table']
- **p556** `table_structure_medium` [low] score=483, notes=['sparse_table']
- **p557** `table_structure_medium` [low] score=963, notes=['sparse_table']
- **p558** `table_structure_medium` [low] score=1280, notes=['sparse_table']
- **p559** `table_structure_medium` [low] score=1169, notes=['sparse_table']
- **p560** `table_structure_medium` [low] score=1340, notes=['sparse_table']
- **p561** `table_structure_medium` [low] score=566, notes=['sparse_table']
- **p562** `missing_table_high_numeric` [high] 无 table，text 中约 42 个数值字段、15 行
- **p564** `table_structure_medium` [low] score=2417, notes=['sparse_table']
- **p565** `table_structure_medium` [low] score=541, notes=['sparse_table']
- **p566** `table_structure_medium` [low] score=1215, notes=['sparse_table']
- **p567** `table_structure_medium` [low] score=1215, notes=['sparse_table']
- **p568** `table_structure_medium` [low] score=233, notes=['sparse_table']
- **p575** `table_structure_medium` [low] score=477, notes=['sparse_table']
- **p577** `vertical_table_low_structure` [high] score=607, notes=['sparse_table', 'truncated_or_header_only']
- **p578** `table_structure_medium` [low] score=838, notes=['sparse_table']
- **p582** `vertical_table_low_structure` [high] score=318, notes=['truncated_or_header_only']
- **p584** `vertical_table_low_structure` [high] score=421, notes=['truncated_or_header_only']
- **p585** `vertical_table_low_structure` [high] score=712, notes=['truncated_or_header_only']
- **p586** `vertical_table_low_structure` [high] score=220, notes=['truncated_or_header_only']
- **p634** `table_structure_medium` [low] score=711, notes=['sparse_table']
- **p635** `table_structure_medium` [low] score=1222, notes=['sparse_table']
- **p648** `table_structure_medium` [low] score=556, notes=['sparse_table']
