# 解析质量 QA 报告

- 输入: `/nfs/users/wuqianqian/IPOI/pdf_parsing/output/samples_batch/03378_15-12-2025_翰思艾泰－Ｂ_全球發售/full_parse.json`
- 总页数: 704
- 问题条数: 104
- 建议重跑: `35,149,181,191,241,250,251,263,273,308,311,312,314,360,365,385,394,429,459,491,548,562,563,564,572,595,596,613,614,618,620,688,698`

## 按标签统计

| 标签 | 次数 |
| --- | ---: |
| `table_structure_medium` | 70 |
| `vertical_table_low_structure` | 25 |
| `missing_table_high_numeric` | 8 |
| `truncated` | 1 |

## 问题明细

- **p23** `table_structure_medium` [low] score=459, notes=['sparse_table']
- **p34** `table_structure_medium` [low] score=325, notes=['sparse_table']
- **p35** `vertical_table_low_structure` [high] score=423, notes=['truncated_or_header_only']
- **p144** `table_structure_medium` [low] score=547, notes=['sparse_table']
- **p147** `table_structure_medium` [low] score=547, notes=['sparse_table']
- **p149** `vertical_table_low_structure` [high] score=327, notes=['truncated_or_header_only']
- **p152** `table_structure_medium` [low] score=547, notes=['sparse_table']
- **p164** `table_structure_medium` [low] score=547, notes=['sparse_table']
- **p166** `table_structure_medium` [low] score=459, notes=['sparse_table']
- **p172** `table_structure_medium` [low] score=663, notes=['sparse_table']
- **p181** `vertical_table_low_structure` [high] score=1567, notes=['truncated_or_header_only']
- **p185** `table_structure_medium` [low] score=547, notes=['sparse_table']
- **p190** `table_structure_medium` [low] score=441, notes=['sparse_table']
- **p191** `vertical_table_low_structure` [high] score=327, notes=['truncated_or_header_only']
- **p194** `table_structure_medium` [low] score=439, notes=['sparse_table']
- **p196** `table_structure_medium` [low] score=555, notes=['sparse_table']
- **p198** `table_structure_medium` [low] score=752, notes=['sparse_table']
- **p199** `table_structure_medium` [low] score=439, notes=['sparse_table']
- **p201** `table_structure_medium` [low] score=1004, notes=['sparse_table']
- **p241** `vertical_table_low_structure` [high] score=102, notes=['truncated_or_header_only']
- **p245** `table_structure_medium` [low] score=719, notes=['sparse_table']
- **p249** `table_structure_medium` [low] score=1836, notes=['sparse_table']
- **p250** `vertical_table_low_structure` [high] score=218, notes=['truncated_or_header_only']
- **p251** `vertical_table_low_structure` [high] score=433, notes=['truncated_or_header_only']
- **p259** `table_structure_medium` [low] score=557, notes=['sparse_table']
- **p260** `table_structure_medium` [low] score=637, notes=['sparse_table']
- **p262** `table_structure_medium` [low] score=678, notes=['sparse_table']
- **p263** `vertical_table_low_structure` [high] score=211, notes=['truncated_or_header_only']
- **p273** `vertical_table_low_structure` [high] score=2422, notes=['colspan_year_mismatch']
- **p308** `vertical_table_low_structure` [high] score=104, notes=['truncated_or_header_only']
- **p309** `table_structure_medium` [low] score=638, notes=['sparse_table']
- **p311** `vertical_table_low_structure` [high] score=237, notes=['truncated_or_header_only']
- **p312** `vertical_table_low_structure` [high] score=230, notes=['truncated_or_header_only']
- **p314** `vertical_table_low_structure` [high] score=341, notes=['truncated_or_header_only']
- **p333** `table_structure_medium` [low] score=640, notes=['sparse_table']
- **p360** `vertical_table_low_structure` [high] score=767, notes=['truncated_or_header_only', 'sparse_table']
- **p364** `truncated` [medium] 模型输出被截断修复
- **p365** `vertical_table_low_structure` [high] score=416, notes=['truncated_or_header_only']
- **p368** `table_structure_medium` [low] score=660, notes=['sparse_table']
- **p370** `table_structure_medium` [low] score=657, notes=['sparse_table']
- **p383** `table_structure_medium` [low] score=494, notes=['sparse_table']
- **p385** `vertical_table_low_structure` [high] score=464, notes=['truncated_or_header_only', 'sparse_table']
- **p388** `table_structure_medium` [low] score=774, notes=['sparse_table']
- **p389** `table_structure_medium` [low] score=777, notes=['sparse_table']
- **p390** `table_structure_medium` [low] score=775, notes=['sparse_table']
- **p394** `vertical_table_low_structure` [high] score=474, notes=['sparse_table', 'truncated_or_header_only']
- **p396** `table_structure_medium` [low] score=339, notes=['sparse_table']
- **p418** `table_structure_medium` [low] score=748, notes=['sparse_table']
- **p421** `table_structure_medium` [low] score=342, notes=['sparse_table']
- **p422** `table_structure_medium` [low] score=119, notes=['sparse_table']
- **p428** `table_structure_medium` [low] score=454, notes=['sparse_table']
- **p429** `vertical_table_low_structure` [high] score=223, notes=['truncated_or_header_only']
- **p430** `table_structure_medium` [low] score=443, notes=['sparse_table']
- **p441** `table_structure_medium` [low] score=357, notes=['sparse_table']
- **p456** `table_structure_medium` [low] score=655, notes=['sparse_table']
- **p458** `table_structure_medium` [low] score=436, notes=['sparse_table']
- **p459** `vertical_table_low_structure` [high] score=210, notes=['truncated_or_header_only']
- **p470** `table_structure_medium` [low] score=428, notes=['sparse_table']
- **p482** `table_structure_medium` [low] score=1457, notes=['complex_colspan_header']
- **p483** `table_structure_medium` [low] score=1557, notes=['complex_colspan_header']
- **p484** `table_structure_medium` [low] score=3034, notes=['complex_colspan_header']
- **p486** `table_structure_medium` [low] score=1697, notes=['complex_colspan_header']
- **p491** `missing_table_high_numeric` [high] 无 table，text 中约 67 个数值字段、26 行
- **p498** `table_structure_medium` [low] score=325, notes=['sparse_table']
- **p501** `table_structure_medium` [low] score=915, notes=['sparse_table']
- **p502** `table_structure_medium` [low] score=1746, notes=['sparse_table']
- **p504** `table_structure_medium` [low] score=642, notes=['sparse_table']
- **p539** `table_structure_medium` [low] score=442, notes=['sparse_table']
- **p548** `vertical_table_low_structure` [high] score=102, notes=['truncated_or_header_only']
- **p551** `table_structure_medium` [low] score=531, notes=['sparse_table']
- **p562** `missing_table_high_numeric` [high] 无 table，text 中约 60 个数值字段、31 行
- **p563** `missing_table_high_numeric` [high] 无 table，text 中约 52 个数值字段、30 行
- **p564** `missing_table_high_numeric` [high] 无 table，text 中约 31 个数值字段、18 行
- **p572** `missing_table_high_numeric` [high] 无 table，text 中约 66 个数值字段、38 行
- **p589** `table_structure_medium` [low] score=1547, notes=['sparse_table']
- **p595** `missing_table_high_numeric` [high] 无 table，text 中约 70 个数值字段、39 行
- **p596** `missing_table_high_numeric` [high] 附录页疑似财务表丢失 table 结构（nums=24）
- **p598** `table_structure_medium` [low] score=341, notes=['sparse_table']
- **p600** `table_structure_medium` [low] score=912, notes=['sparse_table']
- **p604** `table_structure_medium` [low] score=809, notes=['sparse_table']
- **p605** `table_structure_medium` [low] score=480, notes=['sparse_table']
- **p610** `table_structure_medium` [low] score=760, notes=['sparse_table']
- **p611** `table_structure_medium` [low] score=765, notes=['sparse_table']
- **p612** `table_structure_medium` [low] score=651, notes=['sparse_table']
- **p613** `vertical_table_low_structure` [high] score=785, notes=['sparse_table', 'truncated_or_header_only']
- **p614** `missing_table_high_numeric` [high] 附录页疑似财务表丢失 table 结构（nums=22）
- **p615** `table_structure_medium` [low] score=990, notes=['sparse_table']
- **p617** `table_structure_medium` [low] score=918, notes=['sparse_table']
- **p618** `vertical_table_low_structure` [high] score=1455, notes=['truncated_or_header_only']
- **p619** `table_structure_medium` [low] score=1185, notes=['sparse_table']
- **p620** `vertical_table_low_structure` [high] score=805, notes=['truncated_or_header_only']
- **p679** `table_structure_medium` [low] score=349, notes=['sparse_table']
- **p680** `table_structure_medium` [low] score=447, notes=['sparse_table']
- **p688** `vertical_table_low_structure` [high] score=336, notes=['truncated_or_header_only']
- **p689** `table_structure_medium` [low] score=480, notes=['sparse_table']
- **p690** `table_structure_medium` [low] score=479, notes=['sparse_table']
- **p691** `table_structure_medium` [low] score=479, notes=['sparse_table']
- **p692** `table_structure_medium` [low] score=478, notes=['sparse_table']
- **p693** `table_structure_medium` [low] score=484, notes=['sparse_table']
- **p694** `table_structure_medium` [low] score=484, notes=['sparse_table']
- **p695** `table_structure_medium` [low] score=461, notes=['sparse_table']
- **p697** `table_structure_medium` [low] score=338, notes=['sparse_table']
- **p698** `vertical_table_low_structure` [high] score=102, notes=['truncated_or_header_only']
- **p699** `table_structure_medium` [low] score=718, notes=['sparse_table']
