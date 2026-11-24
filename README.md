# 复访路径分析

本地演练资料记录多轮活动报名、实际参与、渠道接触、家庭同行关系、关联证据等级和同意状态。身份标记为合成值，不包含个人信息。

## Local checks

Python 3.9 or newer is sufficient. The repository has no third-party runtime dependencies.

Run `python3 input_audit.py` to verify the declared files and columns. Run `python3 -m unittest discover -s tests -v` to check the prepared input contract.

The records are synthetic fixtures. Empty values and status labels retain their literal input meaning. The manifest lists file columns and the stable row identifier used by the input audit.
