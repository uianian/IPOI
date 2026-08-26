# 解析质量 QA 报告

- 输入: `/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/00368_30-06-2020_德合集團_股份發售/full_parse.json`
- 总页数: 420
- 问题条数: 64
- 建议重跑: `14,23,92,114,131,152,153,163,182,184,187,189,195,196,200,202,220,228,235,237,287,336,345,353,356,398,399`

## 按标签统计

| 标签 | 次数 |
| --- | ---: |
| `table_structure_medium` | 37 |
| `vertical_table_low_structure` | 27 |

## 问题明细

- **p14** `vertical_table_low_structure` [high] score=811, notes=['possible_vertical_table']
- **p23** `vertical_table_low_structure` [high] score=311, notes=['truncated_or_header_only']
- **p67** `table_structure_medium` [low] score=637, notes=['sparse_table']
- **p92** `vertical_table_low_structure` [high] score=426, notes=['truncated_or_header_only', 'sparse_table']
- **p114** `vertical_table_low_structure` [high] score=611, notes=['rotated_table_structure_unstable']
- **p118** `table_structure_medium` [low] score=346, notes=['sparse_table']
- **p131** `vertical_table_low_structure` [high] score=796, notes=['colspan_year_mismatch']
- **p134** `table_structure_medium` [low] score=777, notes=['sparse_table']
- **p135** `table_structure_medium` [low] score=777, notes=['sparse_table']
- **p136** `table_structure_medium` [low] score=777, notes=['sparse_table']
- **p140** `table_structure_medium` [low] score=772, notes=['sparse_table']
- **p141** `table_structure_medium` [low] score=772, notes=['sparse_table']
- **p142** `table_structure_medium` [low] score=772, notes=['sparse_table']
- **p147** `table_structure_medium` [low] score=772, notes=['sparse_table']
- **p148** `table_structure_medium` [low] score=772, notes=['sparse_table']
- **p149** `table_structure_medium` [low] score=772, notes=['sparse_table']
- **p152** `vertical_table_low_structure` [high] score=213, notes=['truncated_or_header_only']
- **p153** `vertical_table_low_structure` [high] score=321, notes=['truncated_or_header_only']
- **p161** `table_structure_medium` [low] score=725, notes=['sparse_table']
- **p163** `vertical_table_low_structure` [high] score=221, notes=['truncated_or_header_only']
- **p164** `table_structure_medium` [low] score=565, notes=['sparse_table']
- **p165** `table_structure_medium` [low] score=250, notes=['sparse_table']
- **p169** `table_structure_medium` [low] score=641, notes=['sparse_table']
- **p170** `table_structure_medium` [low] score=532, notes=['sparse_table']
- **p182** `vertical_table_low_structure` [high] score=314, notes=['truncated_or_header_only']
- **p184** `vertical_table_low_structure` [high] score=422, notes=['truncated_or_header_only']
- **p185** `table_structure_medium` [low] score=526, notes=['sparse_table']
- **p187** `vertical_table_low_structure` [high] score=313, notes=['truncated_or_header_only']
- **p189** `vertical_table_low_structure` [high] score=209, notes=['truncated_or_header_only']
- **p195** `vertical_table_low_structure` [high] score=478, notes=['truncated_or_header_only', 'sparse_table']
- **p196** `vertical_table_low_structure` [high] score=448, notes=['truncated_or_header_only', 'sparse_table']
- **p200** `vertical_table_low_structure` [high] score=913, notes=['colspan_year_mismatch', 'possible_vertical_table']
- **p202** `vertical_table_low_structure` [high] score=1722, notes=['sparse_table', 'colspan_year_mismatch']
- **p204** `table_structure_medium` [low] score=750, notes=['sparse_table']
- **p206** `table_structure_medium` [low] score=615, notes=['sparse_table']
- **p209** `table_structure_medium` [low] score=716, notes=['sparse_table']
- **p220** `vertical_table_low_structure` [high] score=205, notes=['truncated_or_header_only']
- **p228** `vertical_table_low_structure` [high] score=675, notes=['truncated_or_header_only']
- **p232** `table_structure_medium` [low] score=566, notes=['sparse_table']
- **p235** `vertical_table_low_structure` [high] score=339, notes=['truncated_or_header_only']
- **p237** `vertical_table_low_structure` [high] score=452, notes=['truncated_or_header_only']
- **p257** `table_structure_medium` [low] score=636, notes=['sparse_table']
- **p258** `table_structure_medium` [low] score=430, notes=['sparse_table']
- **p259** `table_structure_medium` [low] score=449, notes=['sparse_table']
- **p287** `vertical_table_low_structure` [high] score=413, notes=['truncated_or_header_only']
- **p316** `table_structure_medium` [low] score=553, notes=['sparse_table']
- **p318** `table_structure_medium` [low] score=534, notes=['sparse_table']
- **p336** `vertical_table_low_structure` [high] score=663, notes=['truncated_or_header_only', 'sparse_table']
- **p337** `table_structure_medium` [low] score=2916, notes=['sparse_table']
- **p338** `table_structure_medium` [low] score=1107, notes=['sparse_table']
- **p339** `table_structure_medium` [low] score=572, notes=['sparse_table']
- **p341** `table_structure_medium` [low] score=1296, notes=['sparse_table']
- **p342** `table_structure_medium` [low] score=978, notes=['sparse_table']
- **p345** `vertical_table_low_structure` [high] score=664, notes=['sparse_table', 'truncated_or_header_only']
- **p350** `table_structure_medium` [low] score=649, notes=['sparse_table']
- **p353** `vertical_table_low_structure` [high] score=789, notes=['truncated_or_header_only']
- **p354** `table_structure_medium` [low] score=1004, notes=['sparse_table']
- **p356** `vertical_table_low_structure` [high] score=425, notes=['truncated_or_header_only', 'sparse_table']
- **p357** `table_structure_medium` [low] score=425, notes=['sparse_table']
- **p359** `table_structure_medium` [low] score=428, notes=['sparse_table']
- **p361** `table_structure_medium` [low] score=347, notes=['sparse_table']
- **p397** `table_structure_medium` [low] score=449, notes=['sparse_table']
- **p398** `vertical_table_low_structure` [high] score=321, notes=['truncated_or_header_only']
- **p399** `vertical_table_low_structure` [high] score=213, notes=['truncated_or_header_only']
