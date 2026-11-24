# 复访路径分析

本地演练资料记录多轮活动报名、实际参与、渠道接触、家庭同行关系、关联证据等级和同意状态。身份标记为合成值，不包含个人信息。

## 工具概览

`pathway_tool/` 是可反复运行的参与路径分析工具，按新一轮报名与实际到场重跑即可。
它把"每张签到表当作互不相干人次"和"把相似姓名全部合并"两个极端都排除在外，
改为维护带证据等级的身份解析，并对每条结论标注依赖的判断。

### 双口径身份解析

| 口径 | 采纳的关联 | 结论性质 |
|---|---|---|
| `firm` 确定口径 | 仅在有效期内、`review=approved` 的 `confirmed` 关联 | 可作为确定结论对外使用 |
| `tentative` 存疑口径 | 在 firm 基础上追加 `possible`（含 `pending`）关联 | 依赖可撤回判断，报告中逐条标注 |

* `distinct` 是硬约束：被明确区分的两个标记在任何口径下都不允许合并，冲突时直接报 `IdentityConflictError` 交人工核查。
* `household_token` 只用于家庭分组与提示，**不用于合并人**；仅留家庭预约编号的登记生成家庭内匿名参与者，家庭成员之间也不互相继承反馈。
* 关联带 `valid_from/valid_to`，补录、取消或关联更正后重跑，首访与复访归属会自动重算。

### 同意与匿名化

* 同意按（人、场次）解析，同意事件优先于登记快照，取时间最晚一条；无证据记为 `unknown`，绝不默认同意。
* 撤回同意的（人、场次）记录退出一切个人路径分析（渠道、路径、反馈均不归因到个人）。
* 匿名汇总只按总体维度计数且不含个人标识；单元格人数不足 `k`（默认 3）即抑制。
  对历史已发布单元格给出 `retain / retain_historical_only / remove` 三选一的保留依据。

### 关键产出

* 首访/复访人数与首访渠道（只认 `attended`/`makeup` 实际到场，`cancelled` 不计）；
* 渠道实际参与效果与"接触 → 实际参与"转化，而非报名点击；
* 专题衔接矩阵与专题后续去向（如参加过钱币分享的人是否再来拓印/后续专题）；
* 反馈按人独立归属，含家庭隔离核查；
* 口径快照（输入哈希、参数、关键结果、证据清单）与两期快照 diff，用于解释身份更正前后的数字差异。

## 命令用法

Python 3.9 或更高版本即可，无第三方运行依赖。

```bash
# 输入契约审计
python3 input_audit.py
python3 run_pathway.py audit --data data

# 产出 JSON、Markdown 报告与口径快照
python3 run_pathway.py analyze --data data --out reports --k 3

# 新一轮数据到位后重跑，再对比两期口径差异
python3 run_pathway.py diff --previous reports/caliber_snapshot.json \
    --current reports_new/caliber_snapshot.json
```

## Local checks

Run `python3 input_audit.py` to verify the declared files and columns.
Run `python3 -m unittest discover -s tests -v` to check the input contract and
the full analysis behavior (identity tiers, consent withdrawal, first/repeat
visits, channel conversion, topic paths, feedback isolation, anonymization,
caliber diffing and the CLI).

The records are synthetic fixtures. Empty values and status labels retain their
literal input meaning. The manifest lists file columns and the stable row
identifier used by the input audit.
