"""参与路径分析工具（合成数据演练，无第三方依赖）。

模块划分：

* ``models``        输入记录的数据类
* ``loading``       按清单读取 CSV 并做行级校验
* ``identity``      分层身份解析（确定 / 存疑 / 明确不同）
* ``consent``       逐（人、场次）同意状态解析
* ``participation`` 首访、复访与参与时间线
* ``channel``       渠道实际参与效果与接触转化
* ``paths``         专题衔接路径
* ``feedback``      事后反馈（家庭成员不互相继承）
* ``anonymization`` k-匿名抑制与历史汇总保留依据
* ``caliber``       口径快照与差异对比
* ``analysis``      一次完整分析的编排
* ``reporting``     JSON / Markdown 报告
* ``cli``           命令行入口
"""

__version__ = "1.0.0"

FIRM_VIEW = "firm"
TENTATIVE_VIEW = "tentative"

CONFIRMED = "confirmed"
POSSIBLE = "possible"
DISTINCT = "distinct"

APPROVED = "approved"
PENDING = "pending"

GRANTED = "granted"
WITHDRAWN = "withdrawn"
UNKNOWN = "unknown"
DENIED = "denied"
