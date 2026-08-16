# test_set_v1 解析计划

- 复用已有解析：21
- 需新解析 need_parse：27
- 旧池缺失 missing_parse：0

## 复用映射

| 代码 | 来源 | parse_status | parse_dir |
|------|------|--------------|-----------|
| 00325 | new | need_parse |  |
| 01228 | new | need_parse |  |
| 01334 | new | need_parse |  |
| 01354 | new | need_parse |  |
| 01364 | samples | reuse_samples | pdf_parsing/output/samples_batch/01364_04-02-2025_古茗_全球發售 |
| 01384 | samples | reuse_samples | pdf_parsing/output/samples_batch/01384_20-10-2025_滴普科技_全球發售 |
| 01406 | samples | reuse_samples | pdf_parsing/output/samples_batch/01406_31-01-2022_清晰醫療_全球發售 |
| 01407 | new | need_parse |  |
| 01477 | 18a | reuse_18a | pdf_parsing/output/18a_batch/01477_29-06-2020_歐康維視生物－Ｂ_全球發售 |
| 01641 | new | need_parse |  |
| 01643 | samples | reuse_samples | pdf_parsing/output/samples_batch/01643_31-12-2020_現代中藥集團_全球發售 |
| 01828 | samples | reuse_samples | pdf_parsing/output/samples_batch/01828_26-06-2025_富衛集團_全球發售 |
| 01880 | new | need_parse |  |
| 01973 | new | need_parse |  |
| 02097 | samples | reuse_samples | pdf_parsing/output/samples_batch/02097_21-02-2025_蜜雪集團_全球發售 |
| 02121 | samples | reuse_samples | pdf_parsing/output/samples_batch/02121_17-01-2022_創新奇智_全球發售 |
| 02126 | samples | reuse_samples | pdf_parsing/output/samples_batch/02126_22-10-2020_藥明巨諾－Ｂ_全球發售 |
| 02137 | new | need_parse |  |
| 02155 | new | need_parse |  |
| 02160 | new | need_parse |  |
| 02161 | new | need_parse |  |
| 02197 | 18a | reuse_18a | pdf_parsing/output/18a_batch/02197_25-10-2021_三葉草生物－Ｂ_全球發售 |
| 02257 | new | need_parse |  |
| 02271 | new | need_parse |  |
| 02370 | new | need_parse |  |
| 02407 | new | need_parse |  |
| 02433 | new | need_parse |  |
| 02442 | new | need_parse |  |
| 02443 | new | need_parse |  |
| 02453 | new | need_parse |  |
| 02459 | new | need_parse |  |
| 02482 | samples | reuse_samples | pdf_parsing/output/samples_batch/02482_27-02-2023_維天運通_全球發售 |
| 02531 | new | need_parse |  |
| 02535 | samples | reuse_samples | pdf_parsing/output/samples_batch/02535_29-02-2024_泓基集團_股份發售 |
| 02540 | samples | reuse_samples | pdf_parsing/output/samples_batch/02540_29-02-2024_樂思集團_全球發售 |
| 02571 | new | need_parse |  |
| 02589 | samples | reuse_samples | pdf_parsing/output/samples_batch/02589_28-04-2025_滬上阿姨_全球發售 |
| 02603 | new | need_parse |  |
| 03288 | samples | reuse_samples | pdf_parsing/output/samples_batch/03288_11-06-2025_海天味業_全球發售 |
| 03347 | samples | reuse_samples | pdf_parsing/output/samples_batch/03347_28-07-2020_泰格醫藥_全球發售 |
| 06618 | new | need_parse |  |
| 06622 | 18a | reuse_18a | pdf_parsing/output/18a_batch/06622_16-04-2021_兆科眼科－Ｂ_全球發售 |
| 06963 | new | need_parse |  |
| 09636 | samples | reuse_samples | pdf_parsing/output/samples_batch/09636_28-02-2023_九方財富_全球發售 |
| 09663 | new | need_parse |  |
| 09926 | 18a | reuse_18a | pdf_parsing/output/18a_batch/09926_14-04-2020_康方生物－Ｂ_全球發售 |
| 09939 | 18a | reuse_18a | pdf_parsing/output/18a_batch/09939_12-05-2020_開拓藥業－Ｂ_全球發售 |
| 09995 | 18a | reuse_18a | pdf_parsing/output/18a_batch/09995_28-10-2020_榮昌生物－Ｂ_全球發售 |

## 待解析列表

见 `to_parse_list.csv`。建议命令（确认 GPU 后）：

```bash
cd pdf_parsing
# 可将 to_parse 的 PDF 链到临时目录后：
# batch_parse_samples.py --samples-dir <tmp> --limit N -o output/test_batch --rotate-mode none ...
```
