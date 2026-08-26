# 解析质量 QA 报告

- 输入: `/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/01024_26-01-2021_快手－Ｗ_全球發售/full_parse.json`
- 总页数: 848
- 问题条数: 54
- 建议重跑: `44,171,326,412,583,627,666,673,686,687,840`

## 按标签统计

| 标签 | 次数 |
| --- | ---: |
| `table_structure_medium` | 42 |
| `missing_table_high_numeric` | 6 |
| `vertical_table_low_structure` | 5 |
| `truncated` | 1 |

## 问题明细

- **p28** `table_structure_medium` [low] score=2130, notes=['complex_colspan_header']
- **p29** `table_structure_medium` [low] score=1537, notes=['complex_colspan_header']
- **p35** `table_structure_medium` [low] score=654, notes=['sparse_table']
- **p44** `vertical_table_low_structure` [high] score=424, notes=['truncated_or_header_only']
- **p170** `table_structure_medium` [low] score=640, notes=['sparse_table']
- **p171** `vertical_table_low_structure` [high] score=326, notes=['truncated_or_header_only']
- **p187** `table_structure_medium` [low] score=521, notes=['sparse_table']
- **p198** `table_structure_medium` [low] score=603, notes=['sparse_table']
- **p200** `table_structure_medium` [low] score=636, notes=['sparse_table']
- **p202** `table_structure_medium` [low] score=385, notes=['sparse_table']
- **p237** `table_structure_medium` [low] score=649, notes=['sparse_table']
- **p292** `table_structure_medium` [low] score=549, notes=['sparse_table']
- **p324** `table_structure_medium` [low] score=444, notes=['sparse_table']
- **p326** `vertical_table_low_structure` [high] score=221, notes=['truncated_or_header_only']
- **p360** `table_structure_medium` [low] score=446, notes=['sparse_table']
- **p361** `table_structure_medium` [low] score=120, notes=['sparse_table']
- **p367** `table_structure_medium` [low] score=552, notes=['sparse_table']
- **p372** `table_structure_medium` [low] score=442, notes=['sparse_table']
- **p375** `table_structure_medium` [low] score=545, notes=['sparse_table']
- **p389** `table_structure_medium` [low] score=458, notes=['sparse_table']
- **p390** `table_structure_medium` [low] score=770, notes=['sparse_table']
- **p397** `table_structure_medium` [low] score=552, notes=['sparse_table']
- **p410** `table_structure_medium` [low] score=693, notes=['sparse_table']
- **p412** `vertical_table_low_structure` [high] score=323, notes=['truncated_or_header_only']
- **p444** `table_structure_medium` [low] score=547, notes=['sparse_table']
- **p449** `table_structure_medium` [low] score=1074, notes=['complex_colspan_header']
- **p453** `table_structure_medium` [low] score=1079, notes=['complex_colspan_header']
- **p455** `table_structure_medium` [low] score=1291, notes=['complex_colspan_header']
- **p471** `table_structure_medium` [low] score=3226, notes=['complex_colspan_header']
- **p508** `table_structure_medium` [low] score=454, notes=['sparse_table']
- **p509** `table_structure_medium` [low] score=654, notes=['sparse_table']
- **p583** `missing_table_high_numeric` [high] 无 table，text 中约 65 个数值字段、36 行
- **p627** `missing_table_high_numeric` [high] 无 table，text 中约 46 个数值字段、39 行
- **p629** `table_structure_medium` [low] score=911, notes=['sparse_table']
- **p639** `table_structure_medium` [low] score=771, notes=['sparse_table']
- **p640** `table_structure_medium` [low] score=755, notes=['sparse_table']
- **p655** `table_structure_medium` [low] score=635, notes=['sparse_table']
- **p665** `table_structure_medium` [low] score=673, notes=['sparse_table']
- **p666** `missing_table_high_numeric` [high] 无 table，text 中约 35 个数值字段、25 行
- **p673** `missing_table_high_numeric` [high] 无 table，text 中约 36 个数值字段、30 行
- **p682** `table_structure_medium` [low] score=544, notes=['sparse_table']
- **p684** `table_structure_medium` [low] score=755, notes=['sparse_table']
- **p686** `missing_table_high_numeric` [high] 附录页疑似财务表丢失 table 结构（nums=15）
- **p687** `missing_table_high_numeric` [high] 附录页疑似财务表丢失 table 结构（nums=18）
- **p692** `truncated` [medium] 模型输出被截断修复
- **p692** `table_structure_medium` [low] score=455, notes=['sparse_table']
- **p693** `table_structure_medium` [low] score=799, notes=['sparse_table']
- **p738** `table_structure_medium` [low] score=426, notes=['sparse_table']
- **p792** `table_structure_medium` [low] score=539, notes=['sparse_table']
- **p793** `table_structure_medium` [low] score=644, notes=['sparse_table']
- **p813** `table_structure_medium` [low] score=363, notes=['sparse_table']
- **p814** `table_structure_medium` [low] score=364, notes=['sparse_table']
- **p840** `vertical_table_low_structure` [high] score=314, notes=['truncated_or_header_only']
- **p841** `table_structure_medium` [low] score=618, notes=['sparse_table']
