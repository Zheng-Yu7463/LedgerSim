# 企业经营与会计舞弊数据仿真系统：第一阶段设计

> 文档版本：0.3.1
> 状态：架构基线；M1A 黄金案例与领域测试可开发，M1B/M2 按契约门禁准入
> 第一阶段性质：仿真与标签管线基准，不宣称形成可泛化的机器学习训练集

## 1. 文档目的

本文定义第一阶段的产品目标、数据产品、领域模型、技术架构、会计口径、舞弊语义、验证规则和交付标准。需求、设计、开发和验收均以本文为共同基线。

第一阶段只建立一个能够人工验算的纵向闭环，再扩展到年度规模。发现模型错误时修正根模型并重新生成数据，不维护错误模型的兼容分支。

## 2. 项目定位

本项目是面向财务舞弊研究的企业数字孪生与合成数据系统。系统模拟企业经营活动，分别保存经济事实、企业记录、报告账务和规范账务，在受控条件下引入舞弊行为，输出带有完整事实标签和数据血缘的研究数据。

系统不是：

- 随机生成会计分录的工具；
- 由大模型自由编写财务数据的应用；
- 只生成报表而不保留业务过程的数据生成器；
- 以异常规则命中结果充当舞弊真值的检测系统。

第一阶段主用户是数据集设计与验证人员。会计和舞弊研究人员作为专业评审者，不作为独立产品入口。

## 3. 第一阶段数据产品

### 3.1 产品目标

第一阶段交付“黄金场景与数据生成管线”，用于证明以下能力：

1. 企业经营、记录和会计数据能够稳定生成；
2. 报告账务与规范账务能够分别计算；
3. 舞弊行为、账面错报和可观察数据能够准确关联；
4. 特征数据与上帝视角真值能够隔离；
5. 同一场景能够确定性重放和重新导出。

第一阶段不以模型准确率衡量成功，也不将单一企业模板和单一舞弊机制生成的数据称为成熟训练集。

### 3.2 演示性检测任务

第一阶段同时定义一个演示性数据任务，用于验证数据契约和防泄漏机制：

| 项目 | 定义 |
| --- | --- |
| 预测单元 | 一条销售业务链，即销售订单及其关联发货、发票和收入分录 |
| 观察截止时间 | 报告期末关账完成时点 |
| 输入 | 截止时点前企业正常权限下可见的业务记录和报告账务 |
| 排除输入 | 经济事实、规范账务、分支身份、配对关系、舞弊计划、未来发现与更正 |
| 目标 | 该销售业务链是否包含故意虚假陈述，并在截止时点造成非零报告错报 |
| 输出标签 | `0 = 不满足目标定义`，`1 = 满足目标定义` |

该二元标签只服务演示性检测视图。研究母数据保留更细的正交标签，不把所有舞弊相关下游记录压缩为同一个二元含义。

### 3.3 基准规模

第一阶段生成：

- 1 对手工验算的最小黄金分支；
- 20 对参数化年度分支，用于验证稳定性、数据契约和批量生成能力；
- 每对分支由一个共同祖先、一个基线分支和一个舞弊分支组成；
- 每个年度实例至少包含 200 条销售业务链、100 条采购业务链和 12 个月度关账点；
- 基线数据中同时包含真实的年末大额销售。

第一阶段不划分训练集、验证集和测试集。正式数据集阶段再按公司实例、场景家族和分支对分组切分。

## 4. 时间和范围

### 4.1 时间边界

- 报告期间：2026 年 1 月 1 日至 2026 年 12 月 31 日；
- 关账完成时点：2027 年 1 月 10 日；
- 演示性检测观察截止时间：2027 年 1 月 10 日 23:59:59；
- 延伸仿真期间：至 2027 年 3 月 31 日，用于记录期后回款、异常暴露和更正；
- 数据集中的每个视图必须声明自己的 `observation_cutoff`。

报告期间、仿真期间和观察截止时间是三个独立概念。

### 4.2 纳入范围

- 单一法律主体和单一记账本位币；
- 商品贸易业务、权责发生制、永续盘存制；
- 客户、供应商、商品、员工、角色、银行账户和会计科目；
- 销售、采购、库存、资金和日常经营费用；
- 应收、应付、库存和银行子账；
- 报告账务、规范账务、试算平衡表、资产负债表和利润表；
- 直接法现金流量表；
- 正常经营、真实年末大额销售和期末虚构销售；
- 期后暴露与更正事件；
- 研究母数据包和盲化检测包；
- JSON 和 Parquet 导出。

### 4.3 不纳入范围

- 前端、多 Agent 和大模型调用；
- 多主体、集团合并和外币；
- 生产制造、固定资产、金融工具和所得税；
- 完整税务申报；
- OCR、真实银行和外部审计系统接口；
- 完整审计程序模拟；
- 舞弊检测模型训练；
- 多行业和多舞弊家族。

CSV 不是第一阶段正式交付格式，避免复杂关系和精度在扁平文本中失真。

## 5. 正交事实模型

系统使用“分支”和“事实层”两个正交维度，不能混用“世界”表达。

### 5.1 分支

```text
Scenario
└── Common Ancestor
    ├── Baseline Branch
    └── Fraud Branch
```

- `Common Ancestor` 保存舞弊决策点之前的共享历史；
- `Baseline Branch` 延续正常决策；
- `Fraud Branch` 包含舞弊决策及其因果后果；
- 共享历史只存储一次，不复制到两个子分支。

分支使用：

```text
branch_id
parent_branch_id
fork_global_position
branch_kind
```

`branch_kind` 只存在于受限研究元数据中，不得进入盲化检测包。

创建子分支后，共同祖先立即进入 sealed 状态，不再接受任何命令。祖先事件是两个子分支的只读前缀，后续变化只能追加到对应子分支。

### 5.2 每个分支的四层状态

```text
Branch
├── Economic Truth
├── Enterprise Records
├── Reported Accounting
└── Normative Accounting
```

| 层 | 含义 |
| --- | --- |
| Economic Truth | 实际发生的商品、资金和权利义务变化 |
| Enterprise Records | 企业人员和系统创建的合同、单据、审批及声明 |
| Reported Accounting | 企业依据当时记录实际过账并对外报告的账务 |
| Normative Accounting | 依据经济事实和既定会计政策应当形成的账务 |

同一分支的错报定义为：

```text
misstatement = reported_accounting - normative_accounting
```

基线分支仅用于反事实研究，不能替代舞弊分支的规范账务。

### 5.3 可观察视图

可观察视图不是第五套事实，而是对上述数据按观察者权限和截止时点形成的只读快照。第一阶段只实现：

- 企业普通业务记录视图；
- 企业报告账务视图；
- 受限研究真值视图。

完整的角色认知传播和审计程序留到后续阶段。

## 6. 时间语义

不同对象使用不同时间字段，不用一个字段表达多种语义：

- 经济事实：`occurred_at`；
- 企业记录声称的业务日期：`claimed_effective_at`；
- 企业记录录入时间：`entered_at`；
- 事件写入事件库时间：`committed_at`；
- 会计归属期间：`accounting_period`；
- 观察快照截止时间：`observation_cutoff`。

异常发现和舞弊发现通过新的 `DiscrepancyDetected` 或 `FraudDiscovered` 事件表达，只引用原对象，不回写历史事件。

对象的可见时间 `available_from` 不由场景或调用者填写，而由观察投影根据状态事件推导：

| 对象 | `available_from` |
| --- | --- |
| 销售订单 | `SalesOrderCreated.committed_at` |
| 发货记录 | `ShipmentRecordAccepted.committed_at` |
| 销售发票 | `SalesInvoiceIssued.committed_at` |
| 客户收款 | `CustomerReceiptRecorded.committed_at` |
| 报告凭证 | `ReportedJournalPosted.committed_at` |
| 凭证行 | 继承所属凭证的 `available_from` |
| 子账和余额 | 形成当前快照的最后一条已过账会计事件时间 |
| 财务报表 | `PeriodClosed.committed_at` |
| 舞弊决策真值 | `FraudDecisionRecorded.committed_at`，仅研究观察者允许访问 |

被拒命令和内部控制执行日志不进入普通业务可观察视图。盲化编译器统一按对象的 `available_from <= observation_cutoff` 过滤，不能直接使用业务声明日期代替可见时间。

可见性不是对象固有标签，而是版本化快照关系：

```text
object_id
+ observer_profile_id
+ observation_cutoff
+ view_policy_version
-> access_status
+ temporal_status
```

第一阶段定义 `ordinary_business_v1` 和 `restricted_research_v1` 两种观察者。`access_status` 只由观察者权限策略计算；`temporal_status` 只由 `available_from` 与截止时间比较计算。对象从未创建时不生成可见性关系；对象已在延伸仿真期创建但晚于截止时间时为 `not_yet_available`。

## 7. 总体架构

```text
场景定义 + 外生环境时间带
              |
              v
仿真调度器 -> 命令入口 -> 领域聚合 -> 持久业务事件
                              |
                              v
                         会计策略
                              |
                              v
                         持久会计事件

持久事件 -> 真实状态投影
         -> 企业记录投影
         -> 报告账簿投影
         -> 规范账簿投影
         -> 报表与标签投影
         -> 数据集编译器
```

### 7.1 唯一事件语义

- 业务事件和会计事件都是持久事实；
- 应用用例在内存中对源业务事件执行确定性的报告会计与规范会计反应；
- 源命令结果、业务事件、会计评估事件及全部凭证事件在同一个 PostgreSQL 事务中原子追加；
- 任一会计反应失败时整个事务回滚，不存在已经提交业务事件但缺少会计事件的状态；
- 报告会计和规范会计反应都是系统强制行为，场景策略和未来 Agent 均不能选择、跳过或直接调用；
- `SalesOrderCreated` 在同一提交中为收入和成本分别创建报告案例与规范案例；缺少必要经济输入的规范案例保持 `pending`，证明它存在但尚不满足确认条件；
- 会计反应产生凭证创建、过账、冲销和更正事件；
- 账簿、余额、试算平衡表和报表是可清空重建的读模型；
- 普通重放只消费已存事件重建读模型，不重新执行命令，不再次产生事件；
- 重新计算规范账务属于显式的新仿真运行，不属于普通重放。

### 7.2 架构原则

- 核心领域不读取 `FraudPlan`、`is_fraud` 或分支类型；
- 舞弊由通用动作的选择、遗漏、虚假陈述、串谋或控制覆盖形成；
- 一个事实只有一个写入所有者；
- 领域层不依赖数据库、导出格式和 Agent SDK；
- 第一阶段采用模块化单体和单进程；
- 投影处理必须幂等并保存检查点；
- 特征导出采用字段白名单，不采用泄漏字段黑名单。

## 8. 限界上下文与写入所有者

| 上下文 | 聚合根 | 负责写入 | 核心不变量 |
| --- | --- | --- | --- |
| 组织 | Company、Employee | 主数据和角色授权 | 身份有效、角色唯一 |
| 销售 | SalesOrder、ShipmentRecord、SalesInvoice | 销售承诺、发货声明和客户结算 | 状态迁移、数量和关联合法 |
| 采购 | PurchaseOrder、GoodsReceiptRecord、PurchaseInvoice | 采购承诺、收货声明和供应商结算 | 状态迁移、数量和关联合法 |
| 商业实质 | CustomerCommitment | 客户承诺、控制权转移和结算权利 | 经济事实不能由企业单据自动推定 |
| 实物流 | PhysicalInventory | 实际收发货与盘点 | 实物数量连续 |
| 资金 | BankAccount | 实际资金收付 | 余额连续、收付唯一 |
| 控制 | ControlCase | 授权检查、审批、覆盖和拒绝 | 每个受控动作有执行结论 |
| 报告会计 | ReportedJournal | 企业实际凭证 | 借贷平衡、期间开放、来源唯一 |
| 规范会计 | NormativeJournal | 正确会计凭证 | 借贷平衡、依据经济事实 |
| 会计案例 | AccountingCase | 多源条件评估、唯一过账、冲销和重开 | 同一确认周期最多过账一次 |
| 仿真 | SimulationRun、Branch | 调度、分叉和随机上下文 | 分支祖先稳定 |

`JournalLine` 是凭证子实体。试算平衡表、财务报表、标签和观察视图都是读模型，不是聚合。

## 9. 命令与动作

### 9.1 命令契约

```text
command_id
run_id
branch_id
actor_id
command_type
requested_at
aggregate_id
expected_version
business_chain_id
payload
correlation_id
request_fingerprint
```

`command_id` 全局唯一。命令先通过版本化强类型 schema 解析，再生成规范请求：

- 字段按 schema 固定顺序；
- 时间转换为 UTC 微秒精度 ISO 8601；
- Decimal 按字段固定刻度输出字符串；
- 缺失字段与显式 `null` 按 schema 默认值归一；
- 枚举使用稳定代码；
- 禁止未知字段。

`request_fingerprint` 是对除 `command_id` 和传输追踪字段之外的完整规范请求计算的 SHA-256，必须覆盖命令 schema 版本、命令类型、运行、分支、行为人、目标聚合、预期版本、`business_chain_id`、`requested_at`、`correlation_id` 和 payload。事件库保存 `canonical_request_version`、规范请求和摘要。

- 相同 `command_id` 与相同 `request_fingerprint` 属于重试，返回第一次执行结果；
- 相同 `command_id` 与不同 `request_fingerprint` 拒绝为 `CommandIdConflict`；
- 拒绝冲突不产生领域事件，但写入命令执行日志。

### 9.2 通用动作拆分

发货相关行为拆为天然独立的命令：

- `EstablishCustomerCommitment`：外部环境建立真实客户承诺；
- `RecordShipment`：在企业系统中创建发货声明；
- `DispatchPhysicalGoods`：实际移动商品；
- `IssueSalesInvoice`：创建销售发票；

`PostReportedJournal` 和 `PostNormativeJournal` 是应用层内部会计反应，不属于角色或场景可提交命令。正常策略按业务流程提交全部适用企业行为；舞弊策略可以故意提交虚假记录命令而不提交实际货物流命令。领域处理器对同一企业命令始终采用同一语义，不因舞弊场景改变行为。

### 9.3 控制执行

每个受控命令先写入命令执行日志，再执行授权和控制检查。日志保存：

```text
submitted
authorization_result
control_result
accepted_or_rejected
rejection_reason
override_reference
```

管理层凌驾通过通用 `OverrideControl` 命令和事件表达。串谋通过多个角色已经执行的通用动作和共同因果链表达，不通过系统后门绕过校验。

### 9.4 商业实质状态机

销售域负责企业记录，商业实质上下文负责经济权利义务。二者不能互相替代。

第一阶段销售商业条款固定为：CNY 固定对价、发货点交付、发货即控制权转移、无客户验收条件、无退货权、无可变对价、全量一次交付。其他条款在后续版本作为新的规则版本设计。

```text
CustomerCommitmentEstablished
  -> PhysicalGoodsDispatched
  -> ControlTransferred
  -> SettlementRightEstablished
  -> settled | cancelled
```

- `CustomerCommitmentEstablished` 只能由外部环境中的客户行为产生，保存 `commitment_id`、公司、客户、商品、数量、固定对价、CNY、`delivery_term=dispatch_point` 和 UTC `expires_at`；企业销售订单不能自动生成该事件；
- 客户承诺采用半开有效区间：`established_at <= dispatched_at < expires_at`；
- `DispatchPhysicalGoods` 必须引用 `commitment_id` 和 `business_chain_id`，并提供公司、客户、商品、数量和 UTC `dispatched_at`；`requested_at` 不能代替实际发运时间；
- 第一阶段只接受与有效承诺在公司、客户、商品、数量、币种和对价上完全匹配的全量发货；不匹配时拒绝为 `EconomicFulfillmentMismatch`，不产生部分经济事实；
- 有效发货在同一个提交中依次产生 `PhysicalGoodsDispatched`、`ControlTransferred`、`SettlementRightEstablished`；
- `ControlTransferred` 保存承诺、发货、商品、数量和控制权转移时间；
- `SettlementRightEstablished` 保存承诺、控制权转移、客户、商品、数量、固定对价、币种和权利成立时间；
- 企业发票只表达企业提出的结算主张，不能单独证明真实结算权利；
- 虚构销售没有 `CustomerCommitmentEstablished`、`ControlTransferred` 和 `SettlementRightEstablished`，即使企业记录完整也不满足规范收入条件。

第一阶段正常销售的规范收入条件固定为 `ControlTransferred + SettlementRightEstablished`。商业实质事件的写入所有者是 `CustomerCommitment` 聚合与经济事实反应器，不是销售单据聚合。

采购商业实质采用对称模型：

```text
SupplierCommitmentEstablished
  -> PhysicalGoodsReceived
  -> SupplierSettlementObligationEstablished
  -> SupplierInvoiceReceived
  -> settled | cancelled
```

`SupplierCommitmentEstablished` 保存供应商、商品、数量、固定对价、币种和 `delivery_term=receipt_point`。`ReceivePhysicalGoods` 必须引用有效承诺；完全匹配的收货在同一提交中产生 `PhysicalGoodsReceived` 和 `SupplierSettlementObligationEstablished`。真实供应商发票通过外部事件 `SupplierInvoiceReceived` 表达，企业 `PurchaseInvoiceRecorded` 不能自动生成该经济事实。

### 9.5 会计案例状态机

每条会计规则按业务链建立独立 `AccountingCase`：

```text
pending -> posted -> reversed
```

唯一案例键：

```text
accounting_case_key =
  run_id
  + branch_id
  + ledger_type
  + accounting_rule_id
  + business_chain_id
  + recognition_cycle
```

- `ledger_type` 为 `reported` 或 `normative`；
- `recognition_cycle` 初始为 1，只有原案例完成冲销后才能创建下一周期的新案例；
- 唯一约束建立在完整 `accounting_case_key` 上；
- 首次评估使用 `INSERT ... ON CONFLICT ...` 取得唯一案例，再以 `SELECT ... FOR UPDATE` 锁定；
- 每个相关业务事件到达后，应用层锁定案例并重新评估条件；
- 条件首次满足的事务产生唯一凭证并将案例置为 `posted`；
- 已 `posted` 案例收到重复或乱序事件时只更新输入审计记录，不重复过账；
- 冲销必须引用原案例和原凭证，将原案例置为 `reversed`；一张原凭证最多存在一个有效冲销；
- 重开创建 `recognition_cycle + 1` 的新案例并保存 `predecessor_case_id`，原案例不存在 `reopened` 状态；
- 报告案例读取企业记录，规范案例读取经济事实；
- 场景策略不能创建、跳过或修改规范案例。

多源血缘保存在 `accounting_case_inputs`，每行关联案例、输入事件、输入角色和首次观察位置。凭证保存 `accounting_case_key`，由此追溯全部触发条件。输入事件集合按稳定顺序计算 `input_digest`，相同摘要的重新评估必须是无副作用操作。

数据库约束固定为：

```text
UNIQUE(accounting_case_key)
UNIQUE(accounting_case_id, journal_role)
UNIQUE(reverses_journal_id)
UNIQUE(predecessor_case_id)
UNIQUE(accounting_case_id, input_event_id, input_role)
CHECK(status = 'pending'  AND posted_journal_id IS NULL
   OR status = 'posted'   AND posted_journal_id IS NOT NULL
   OR status = 'reversed' AND posted_journal_id IS NOT NULL
                        AND reversal_journal_id IS NOT NULL)
```

`journal_role` 只允许 `recognition` 或 `reversal`。`business_chain_id` 由销售或采购业务链聚合在创建时分配，后续命令只能引用已有 ID；命令不能自行声明新的链 ID。所有业务事件从聚合继承该 ID。

## 10. 事件存储

### 10.1 事件契约

```text
event_id
run_id
branch_id
aggregate_type
aggregate_id
event_type
stream_position
global_position
commit_id
event_occurred_at
committed_at
actor_id
causation_id
correlation_id
payload
schema_version
```

### 10.2 提交不变量

- 一个 `commit_id` 中的命令结果和全部事件原子保存；
- `expected_version` 用于聚合级乐观并发；
- `stream_position` 在聚合流内连续；
- 第一阶段同一 `run_id` 的事件提交严格串行：事务开始后先以 `SELECT ... FOR UPDATE` 锁定 `simulation_runs` 行；
- 事务根据事件数量从该行的 `next_global_position` 分配无缺口连续区间，并在同一事务更新下一个位置；
- 事务回滚时位置分配同时回滚，不使用 PostgreSQL sequence；
- 数据库约束包含 `UNIQUE(run_id, global_position)` 和 `UNIQUE(event_id)`；
- 因同一运行不允许并发分配位置，不存在低位置晚于高位置提交；
- 被拒命令保存在执行日志中，不伪装成领域事件；
- 投影按 `global_position = checkpoint + 1` 顺序处理；发现缺口时停止并报告事件存储损坏；
- 事件只追加，不原地修改。

### 10.3 分支读取

读取子分支时，先读取祖先分支截至 `fork_global_position` 的事件前缀，再读取子分支自身事件。分叉前事件只有一个 `event_id`，保证共享历史、血缘和摘要一致。

聚合流版本采用以下唯一规则：

- 聚合状态由祖先截至分叉点的聚合事件与当前子分支事件共同重建；
- `expected_version` 表示解析祖先前缀后的逻辑聚合版本；
- 子分支首个聚合事件的 `stream_position` 从祖先该聚合的最后版本加一开始；
- 两个子分支可以分别拥有相同的下一逻辑版本；
- 事件唯一约束为 `run_id + branch_id + aggregate_type + aggregate_id + stream_position`；
- 对共同祖先追加事件和跨子分支写入均属于非法操作；
- 聚合仓储必须接收显式 `branch_id`，不允许在没有分支上下文时加载或保存聚合。

## 11. 仿真与随机性

### 11.1 离散时间

系统时钟直接推进到下一个计划动作。稳定排序依次使用：

1. 计划时间；
2. 动作优先级；
3. 语义业务键；
4. 确定性动作 ID。

禁止使用系统当前时间、随机 UUID 和数据库默认顺序参与业务结果。

### 11.2 外生环境时间带

客户需求、市场价格和客户付款能力等外生变量在分叉前一次性生成不可变时间带。两个子分支读取同一时间带，不因分支内调用次数不同而错位。

### 11.3 按语义键寻址的随机数

随机值由以下键确定：

```text
root_seed
+ generator_version
+ variable_type
+ entity_id
+ period
+ occurrence_index
+ counterfactual_key
```

任何随机结果都不能依赖此前调用次数。内生决策默认使用共享的 `counterfactual_key + decision_id`，不加入 `branch_id`。当两个分支的决策输入状态在该决策所需字段上相同时，它们必须得到相同随机值和相同选择。

只有满足以下全部条件，决策才能使用 `causal_branch` 随机域：

1. 决策输入包含已经发生的分支差异；
2. 该差异可以沿因果图追溯到直接舞弊行为；
3. 决策记录明确的 `cause_event_id` 和 `causal_context_id`；
4. 随机键使用 `counterfactual_key + decision_id + causal_context_id`；
5. 决策结果登记为该原因的因果后代。

禁止仅以 `branch_id` 不同产生随机分歧。无法满足上述条件的分支特有决策属于 `unexplained_difference`。

每类随机决策必须注册版本化 `DecisionSpec`，固定 `decision_spec_id`、输入字段白名单、状态规范化方式、`decision_id` 派生规则和随机变量分布。`counterfactual_key` 由场景对、决策规格、实体语义 ID、期间和发生序号派生。

`causal_context_id` 只能由排序后的因果祖先语义键、`decision_spec_id` 和规则版本计算，且每个祖先必须通过 `causal_edges` 外键链追溯到直接舞弊事件。调用者不能传入 `decision_id`、`counterfactual_key` 或 `causal_context_id`。

### 11.4 跨分支对象配对

共享或可比较对象具有受限研究字段 `twin_key`。差异分为：

- `direct_fraud_action`：舞弊行为直接造成；
- `causal_descendant`：直接行为的因果后代；
- `common_external_event`：两个分支共同接收的外部事件；
- `unexplained_difference`：无法由前三类解释的差异。

验收要求 `unexplained_difference = 0`。

## 12. 会计政策

### 12.1 基础口径

- 权责发生制；
- 单一记账本位币 CNY；
- 永续盘存制；
- 移动加权平均法；
- 直接法现金流量表；
- 报告账与规范账使用同一会计政策和同一科目表；
- 报告账依据企业已接受记录实际过账；
- 规范账依据经济事实正确过账；
- 第一阶段税额统一为零，金额结构仍保留未税金额、税额和含税金额。

### 12.2 精度与舍入

| 数据 | 精度 |
| --- | --- |
| 数量 | Decimal(18, 4) |
| 单价 | Decimal(18, 4) |
| 单位成本 | Decimal(18, 6) |
| 会计金额 | Decimal(18, 2) |

- 所有计算使用十进制定点数；
- 舍入方式为 `ROUND_HALF_UP`；
- 业务明细先按高精度计算，在生成凭证行时舍入到分；
- 凭证尾差由明确的尾差行处理，不修改任意商品行；
- 时区存储为 UTC，业务日历使用 Asia/Shanghai。

### 12.3 借贷、余额与错报方向

凭证行不保存模糊的有符号金额，只保存两个非负字段：

```text
debit_amount
credit_amount
```

每行必须且只能有一侧大于零。科目表必须定义 `normal_balance = debit | credit`。

用于报表和错报比较的正常余额值：

```text
raw_balance = debit_total - credit_total

display_balance =
  raw_balance       when normal_balance = debit
  -raw_balance      when normal_balance = credit
```

`display_balance` 在科目正常方向增加时为正，反方向余额为负。同一科目或派生指标的错报金额定义为：

```text
misstatement_amount =
  reported_display_value - normative_display_value
```

- `misstatement_amount > 0`：overstated；
- `misstatement_amount < 0`：understated；
- `misstatement_amount = 0`：none。

分录行对余额的标准化影响：

```text
line_balance_effect =
  debit_amount - credit_amount   when normal_balance = debit
  credit_amount - debit_amount   when normal_balance = credit
```

资产、负债、权益、收入和费用先按各自科目正常余额转换，再汇总报表。利润固定为收入正常余额之和减费用正常余额之和，利润错报仍使用“报告值减规范值”。禁止根据借方或贷方字面位置直接推断高估、低估。

### 12.4 期初与采购

公司成立时投入现金资本：

```text
借：银行存款
贷：实收资本
```

采购收货与采购发票允许分时发生。报告账读取 `GoodsReceiptRecordAccepted` 和 `PurchaseInvoiceRecorded`；规范账分别读取 `PhysicalGoodsReceived + SupplierSettlementObligationEstablished` 和 `SupplierInvoiceReceived`。企业单据不能替代这些经济事件。

```text
实际或记录收货：
借：库存商品
贷：暂估应付

收到采购发票：
借：暂估应付
贷：应付账款

支付供应商：
借：应付账款
贷：银行存款
```

采购订单、收货、发票必须按业务链、公司、供应商、商品、数量、币种和对价完全匹配。实际付款必须引用 `SupplierSettlementObligationEstablished`，报告付款必须引用企业应付项目。M1A 黄金夹具不覆盖采购；采购在 M3 前必须新增独立黄金夹具验证上述经济血缘。

### 12.5 销售

第一阶段要求销售发票与发货记录在同一业务日完成，但保留两个独立动作和对象。订单、发货记录和发票必须在 `business_chain_id`、公司、客户、商品、数量、币种上完全一致，发票未税金额必须等于数量乘固定单价；不一致时拒绝为 `ReportedSalesMismatch`。

确认规则固定如下：

| 规则 | 必要输入 | 数量与金额 | 会计日期 |
| --- | --- | --- | --- |
| `reported_sales_revenue_v1` | `ShipmentRecordAccepted + SalesInvoiceIssued` | 数量取已接受发货记录；收入取已验证发票未税金额 | 发货记录的 `claimed_effective_at` |
| `reported_sales_cogs_v1` | `ShipmentRecordAccepted + SalesInvoiceIssued` | 数量取已接受发货记录；单位成本取发货记录接受前的报告库存成本快照 | 发货记录的 `claimed_effective_at` |
| `normative_sales_revenue_v1` | `ControlTransferred + SettlementRightEstablished` | 数量取控制权转移；收入取真实结算权固定对价 | `ControlTransferred.occurred_at` |
| `normative_sales_cogs_v1` | `ControlTransferred + SettlementRightEstablished` | 数量取控制权转移；单位成本取实际发货前的规范库存成本快照 | `ControlTransferred.occurred_at` |

`ShipmentRecordAccepted` 必须保存 `reported_cost_snapshot_id`；`PhysicalGoodsDispatched` 必须保存 `normative_cost_snapshot_id`。后续事件到达时只引用快照，不能按当前库存余额重新计算历史成本。

报告收入与成本案例满足各自条件后处理：

```text
借：应收账款
贷：主营业务收入

借：主营业务成本
贷：库存商品
```

规范收入与成本案例在 `ControlTransferred` 与 `SettlementRightEstablished` 同时存在时采用相同分录。二者来自商业实质上下文，不能由销售订单、发货记录或发票自动推定。舞弊不改变规则，只改变报告账所依赖的企业记录与规范账所依赖的经济事实是否一致。

客户收款：

```text
借：银行存款
贷：应收账款
```

### 12.6 费用、结账与报表

经营费用按受益期间确认。月末依次执行子账核对、试算平衡和期间关闭；年末额外执行损益结转和报表生成。

现金流量表采用直接法：

- 客户收款归入经营活动现金流入；
- 商品采购付款和经营费用付款归入经营活动现金流出；
- 初始资本投入归入筹资活动现金流入。

第一阶段不发生投资活动现金流。

## 13. 舞弊场景

### 13.1 场景定义

管理层在报告期末面临利润目标压力，决定创建不存在真实履约的销售记录，以虚增收入、利润和应收账款。

### 13.2 通用动作组成的行为链

1. 管理层形成舞弊决策并产生受限真值事件；
2. 外部环境不产生 `CustomerCommitmentEstablished`；
3. 相关人员创建异常销售订单；
4. 仓储角色执行 `RecordShipment`，但不执行 `DispatchPhysicalGoods`；
5. 因此不产生 `ControlTransferred` 和 `SettlementRightEstablished`；
6. 销售角色执行 `IssueSalesInvoice`；
7. 企业控制流程接受这些记录，报告会计案例满足条件并形成收入、成本和应收账款；
8. 规范会计案例保持不满足条件，不确认该销售及成本；
9. 报告库存低于实际库存，形成盘点差异；
10. 下一期间出现逾期、盘点差异或更正事件。

核心领域命令不读取舞弊计划。舞弊意图、参与者和因果关系只保存在受限真值事件与标签中。

### 13.3 手工可验算示例

假设虚构销售商品 100 件，售价 120.00 元，移动平均单位成本 80.000000 元。

报告账：

```text
借：应收账款       12,000.00
贷：主营业务收入   12,000.00

借：主营业务成本    8,000.00
贷：库存商品        8,000.00
```

规范账不产生上述分录。因此期末错报为：

| 项目 | 报告账相对规范账 |
| --- | ---: |
| 应收账款 | 高估 12,000.00 |
| 营业收入 | 高估 12,000.00 |
| 主营业务成本 | 高估 8,000.00 |
| 库存商品 | 低估 8,000.00 |
| 利润 | 高估 4,000.00 |

对应审计认定：

- 营业收入：发生；
- 应收账款：存在；
- 主营业务成本：发生、准确性；
- 库存商品：完整性、准确性。

该纯虚构交易不自动标记为截止错报。只有实际交易属于另一期间却被提前或延后确认时，才标记截止认定。

### 13.4 困难负样本

基线分支必须包含金额和时间特征相似的真实年末大额销售。它具有真实客户承诺、控制权转移、结算权利、企业订单、实际发货、有效发票和后续合理回款，不具有故意虚假陈述或报告错报。

## 14. 标签模型

标签采用正交维度，不使用一个 `fraud_type` 字段覆盖全部语义。

### 14.1 标签轴

| 标签轴 | 允许值 |
| --- | --- |
| `intent_class` | normal、error、intentional、not_applicable |
| `record_truth_status` | truthful、fabricated、omitted、amount_incorrect、not_applicable |
| `causal_role` | direct_action、concealment、downstream_effect、exposure、correction、unrelated |
| `misstatement_status` | none、overstated、understated、not_applicable |
| `access_status` | allowed、restricted |
| `temporal_status` | available、not_yet_available |

错报标签同时保存账户、报表项目、方向和 Decimal 金额。

`misstatement_amount` 始终保存有符号的“报告显示值减规范显示值”；`direction` 必须由其符号派生，不是独立输入。数据契约拒绝正金额与 `understated`、负金额与 `overstated` 或零金额与非 `none` 的组合。

### 14.2 传播规则

- 舞弊决策和虚假记录创建属于 `direct_action`；
- 由虚假记录自动生成的凭证属于 `downstream_effect`，不称为具有主观意图；
- 为隐藏差异而执行的后续行为属于 `concealment`；
- 盘点差异、逾期和函证不符属于 `exposure`，不称为舞弊行为；
- 冲销和调整凭证属于 `correction`；
- 与舞弊业务链没有因果关系的异常属于 `unrelated`。

每类对象必须通过标签真值表生成标签，不允许导出阶段依靠名称匹配或金额阈值推断。

### 14.3 黄金场景真值矩阵

M2 的虚构销售必须得到以下唯一标签结果：

下表的可见性列以 `observer_profile_id=ordinary_business_v1`、`view_policy_version=1` 和第一阶段报告观察截止时间为条件。

| 对象 | `intent_class` | `record_truth_status` | `causal_role` | `misstatement_status` | `access_status` | `temporal_status` |
| --- | --- | --- | --- | --- | --- | --- |
| 舞弊决策 | intentional | not_applicable | direct_action | not_applicable | restricted | available |
| 销售订单 | intentional | fabricated | direct_action | not_applicable | allowed | available |
| 发货记录 | intentional | fabricated | direct_action | not_applicable | allowed | available |
| 实际货物流 | 不创建对象；以发货声明与经济事实不一致关系表达 | | | | | |
| 销售发票 | intentional | fabricated | direct_action | not_applicable | allowed | available |
| 报告凭证头 | not_applicable | not_applicable | downstream_effect | not_applicable | allowed | available |
| 应收账款借方行 | not_applicable | not_applicable | downstream_effect | overstated | allowed | available |
| 主营业务收入贷方行 | not_applicable | not_applicable | downstream_effect | overstated | allowed | available |
| 主营业务成本借方行 | not_applicable | not_applicable | downstream_effect | overstated | allowed | available |
| 库存商品贷方行 | not_applicable | not_applicable | downstream_effect | understated | allowed | available |
| 应收账款期末余额影响 | not_applicable | not_applicable | downstream_effect | overstated | allowed | available |
| 营业收入报表影响 | not_applicable | not_applicable | downstream_effect | overstated | allowed | available |
| 主营业务成本报表影响 | not_applicable | not_applicable | downstream_effect | overstated | allowed | available |
| 库存商品期末余额影响 | not_applicable | not_applicable | downstream_effect | understated | allowed | available |
| 期后盘点差异 | not_applicable | truthful | exposure | not_applicable | allowed | not_yet_available |
| 更正凭证头 | not_applicable | truthful | correction | not_applicable | allowed | not_yet_available |

规范账没有对应凭证时，不创建“缺失凭证”占位对象。对应规范案例保持 `pending` 且 `posted_journal_id` 为空，错报投影用报告分录与该规范案例的零分录结果计算差额。

`misstatement_status` 的方向只适用于分录、账户余额和报表项目，不强行上卷到订单、单据、暴露事件或凭证头。`access_status` 由观察者权限决定；`temporal_status` 由 `available_from` 与观察截止时间比较得到。两者不能合并为一个“不可见”状态。

### 14.4 标签粒度

研究母数据支持场景、行为人、命令、事件、业务记录、凭证、分录、科目余额、报表项目和审计认定级标签。

演示性二元检测标签只附着于盲化后的销售业务链，不向特征表传播内部真值字段。

## 15. 数据产品与防泄漏

### 15.1 研究母数据包

受限研究包包含：

- 经济事实；
- 企业记录；
- 报告账务和规范账务；
- 分支配对、`twin_key` 和因果图；
- 舞弊计划、标签、期后发现与更正；
- 运行版本、种子和完整血缘。

该数据包用于生成器验证和因果研究，不直接用于盲化检测训练。

### 15.2 盲化检测包

盲化包采用字段白名单，只包含观察截止时间前可见的：

- 销售订单、发货记录、销售发票和客户收款记录；
- 客户主数据的业务可见字段；
- 报告凭证和分录；
- 截止时点的应收、库存、收入和成本账面信息；
- 独立标签文件中的业务链二元目标。

研究母数据包与盲化检测包是不同访问级别的制品，不向同一盲测参与者同时分发。每个数据集主版本的公开盲化制品遵守：

- 每个 `branch_pair` 最多选择一个子分支；
- 被选择分支的孪生分支不能出现在同一主版本的其他公开盲化制品中；
- 基线和舞弊样本从不同分支对中选择；
- 选择映射只保存在受限发布清单，不进入盲化包；
- 场景级标签文件只使用盲化样本 ID，不包含研究包关联键；
- 需要反事实配对数据的研究者使用研究母数据包，该使用方式不再声称是盲测。

公开成员资格保存在受限 `dataset_release_members`，并建立：

```text
UNIQUE(dataset_major_version, branch_pair_id)
UNIQUE(dataset_release_id, public_sample_id)
```

盲化处理必须：

- 将内部 ID 重映射为无语义、确定性的样本内 ID；
- 删除 `branch_id`、`branch_kind`、`scenario_id`、`twin_key` 和配对信息；
- 删除经济事实、规范账务、舞弊计划和因果角色；
- 排除观察截止时间后的回款、发现、冲销和调整；
- 不导出内部事件类型、执行拒绝原因或仅在舞弊流程出现的技术字段；
- 固定文件命名、表顺序和字段顺序，使分支类型无法从制品结构推断。

发布前执行配对重识别门禁：

1. 在受限环境中为每个公开候选样本计算分叉前历史的内部 `shared_history_fingerprint`；
2. 断言全部公开盲化制品中每个指纹最多出现一次；
3. M2 只执行分支对唯一约束、共享历史精确指纹唯一、schema 完全一致、ID 格式一致和受限映射不可达等结构性门禁；
4. M5 样本量达到统计测试要求后，才启用版本化 `LeakageProbeSpec`；该规格必须固定特征白名单、近似指纹算法、相似度阈值、分组切分、随机种子、评价指标、置信区间和阻断阈值；
5. 第一版统计规格要求至少 100 个独立分支对，使用按分支对分组的 5 折交叉验证；技术元数据探针 balanced accuracy 点估计不得超过 0.55，95% bootstrap 置信区间必须包含 0.50；
6. 任何结构性或适用的统计门禁失败都阻断发布，不能通过删除单个命中字段绕过。

### 15.3 主要表

业务与报告账务包括：

```text
companies, employees, customers, suppliers, products
sales_orders, shipment_records, sales_invoices, customer_receipts
purchase_orders, goods_receipt_records, purchase_invoices
supplier_payments, expense_claims, approvals
reported_journal_entries, reported_journal_lines
reported_subledger_items, reported_trial_balances
reported_financial_statements
```

研究真值额外包括：

```text
physical_goods_movements, customer_commitments
control_transfers, settlement_rights
normative_journal_entries, normative_journal_lines
fraud_decisions, fraud_actions, ground_truth_labels
statement_misstatements, assertion_impacts
branch_pairs, causal_edges, branch_differences
```

## 16. 可复现性

### 16.1 规范化内容摘要

逻辑可复现性以规范化内容摘要为准：

- 确定性业务 ID；
- 稳定表、字段和行排序；
- UTC ISO 8601 时间；
- Decimal 使用固定字符串表示；
- 明确空值和布尔表示；
- 排除运行耗时、数据库内部 ID 和文件创建时间；
- 对规范化记录计算 SHA-256。

会计摘要分为：

- `accounting_content_digest`：会计规则版本、账簿类型、会计期间、币种，以及按科目、借贷方向、辅助维度和金额稳定排序的分录行；
- `lineage_digest`：按输入角色和事件语义 ID 稳定排序的会计案例输入；
- 触发顺序、数据库位置、提交时间、事件 ID 和过账技术时间不进入 `accounting_content_digest`；
- 会计日期、规则版本、币种和金额必须进入 `accounting_content_digest`。

V1 的 `accounting_content_digest` 输入固定为以下对象，字段名按字典序编码，`lines` 按 `(account, debit_amount, credit_amount)` 排序；V1 没有辅助维度，后续增加辅助维度必须升级摘要规则版本：

```json
{
  "accounting_date": "YYYY-MM-DD",
  "accounting_period": "YYYY-MM",
  "currency": "CNY",
  "ledger_type": "reported | normative",
  "lines": [
    {
      "account": "account_semantic_id",
      "credit_amount": "0.00",
      "debit_amount": "0.00"
    }
  ],
  "rule_version": "accounting_rule_version"
}
```

V1 的 `lineage_digest` 输入是由 `input_role` 和 `event_semantic_id` 组成的数组，按 `(input_role, event_semantic_id)` 排序。单次完整交付下，`event_semantic_id` 固定派生为 `event_type + "|" + business_chain_id`；技术 `event_id` 不进入摘要。两个摘要均将对象编码为 UTF-8 JSON，键按字典序排列，不输出多余空白，再计算 SHA-256。任何字段、排序或语义 ID 派生规则变化都必须升级摘要规则版本，不能静默改变。

### 16.2 发布文件摘要

字节级文件摘要用于同一发布环境下的制品校验。发布清单固定：

- 源码提交摘要；
- 生成器版本；
- 场景版本；
- 数据库迁移版本；
- Python 与依赖锁文件摘要；
- PRNG 和分布实现版本；
- PyArrow 版本；
- 每个导出文件的 SHA-256。

逻辑内容摘要和发布文件摘要不能混为同一验收指标。

### 16.3 模型生命周期

- 1.0 发布前允许清库并从场景重新生成，不维护旧事件兼容；
- 发布后的基准数据集连同生成器版本冻结为独立制品；
- 领域语义变更产生新的数据集主版本；
- 不在运行时代码中长期堆积旧事件 upcaster；
- 必须升级内部事件时执行一次性全量重建并重新签发清单。

## 17. 存储和模块结构

第一阶段采用 PostgreSQL 单库，逻辑隔离事件、投影、研究真值和导出清单。

```text
src/ledger_sim/
  domain/          # 聚合、值对象、领域服务和持久事件
  application/     # 命令处理、事务和幂等
  simulation/      # 时间、环境带、随机键和分支
  accounting/      # 报告与规范记账策略
  projections/     # 账簿、报表、标签和观察快照
  scenarios/       # 正常策略与舞弊决策策略
  validation/      # 业务、会计、血缘、泄漏和差异验证
  datasets/        # 白名单视图、盲化和导出
  infrastructure/  # PostgreSQL、仓储、配置和日志
  cli/             # run、replay、validate、inspect、export
tests/
  unit/
  integration/
  golden/
  properties/
docs/
```

技术选型：

- Python 3.12；
- Pydantic；
- SQLAlchemy 2；
- PostgreSQL；
- Alembic；
- Pytest 与 Hypothesis；
- PyArrow；
- Typer；
- Ruff 与 mypy。

第一阶段不引入消息队列、微服务和大模型编排框架。

## 18. 命令行

```text
ledger-sim run <scenario>
ledger-sim replay <run-id>
ledger-sim validate <run-id>
ledger-sim inspect <run-id> <object-id>
ledger-sim export <run-id> --package research|blind
```

- `run`：生成共同祖先、基线分支和舞弊分支；
- `replay`：仅从持久事件重建投影；
- `validate`：执行全部质量门禁；
- `inspect`：查看对象的来源、因果关系和账务血缘；
- `export`：编译研究包或盲化包。

## 19. 验证体系

### 19.1 业务与事件

- 聚合状态转换合法；
- 正常经营下实际货物流与企业记录一致；
- 每个受控命令都有授权和控制结论；
- 重复命令不产生重复事件；
- 事务中断不产生半提交；
- 分支共享历史只存储一次；
- 所有无法解释的跨分支差异为零。

### 19.2 会计

- 每张报告凭证和规范凭证借贷平衡；
- 报告账与企业记录血缘完整；
- 规范账与经济事实血缘完整；
- 应收、应付、库存和银行子账与对应总账一致；
- 试算平衡表借贷合计一致；
- 资产等于负债加所有者权益；
- 直接法现金流量净增加额等于现金余额变化；
- 错报金额等于同一分支报告账与规范账差额。

### 19.3 标签与泄漏

- 每个标签来自明确命令、事件或账务差额；
- 下游影响不被错误标记为具有主观意图；
- 受影响分录能够聚合到科目和报表错报；
- 盲化包只包含字段白名单；
- 所有记录满足投影推导的 `available_from <= observation_cutoff`；
- 盲化 ID、文件名、顺序和元数据不暴露分支身份；
- 公开盲化制品中每个分支对最多出现一个子分支；
- 共享历史精确与近似重识别门禁通过；
- 研究包与盲化包的行级关联只能通过受限映射完成。

### 19.4 可复现性

- 相同版本、配置和种子产生相同规范化内容摘要；
- 删除投影后重放得到相同摘要；
- 分叉前共享事件摘要唯一且稳定；
- 依赖升级造成字节摘要变化时，逻辑内容摘要仍按契约比较；
- 发布清单包含全部版本和校验信息。

## 20. 测试策略

- 黄金测试：以经校验的期初余额人工验算正常销售、收款、虚构销售和错报；采购使用独立后续夹具；
- 单元测试：值对象、状态机、移动平均、舍入和记账规则；
- 集成测试：命令、事务、事件、会计事件和投影；
- 性质测试：借贷平衡、金额守恒、库存连续和确定性；
- 变形测试：增加一笔已知交易后验证账户与报表的确定变化；
- 故障测试：重复命令、预期版本冲突、提交中断和投影恢复；
- 差异测试：共享历史、直接影响、因果后代和不可解释差异；
- 契约测试：字段、主外键、观察截止、ID 盲化和标签隔离。
- 泄漏测试：孪生分支互斥发布、共享历史重识别和技术元数据探针。

测试不依赖系统时间、外部网络、数据库默认顺序或测试执行顺序。

## 21. 纵向开发里程碑

### M1A：黄金案例与纯领域测试

先用机器可读夹具固定经校验的期初余额、一笔正常销售及收款，以及一笔成对的真实年末销售和虚构销售。夹具必须逐步给出：

```text
输入命令与事件
-> 每步经济和记录状态
-> 报告账与规范账凭证
-> 最终余额与错报
-> 对象标签
-> 乱序与重复输入预期
```

本阶段只实现不依赖数据库的值对象、聚合、会计案例评估和黄金测试。

机器可读契约位于 `fixtures/golden/sales-fraud-v1.json`，其 JSON Schema 位于同目录的 `sales-fraud-v1.schema.json`。夹具逐命令定义完整输入、预期领域及会计事件、事件信封推导规则、四层状态快照、双账凭证、多源血缘、标签、乱序、幂等、冲销、反事实随机和发布门禁。

唯一验收命令为：

```bash
python fixtures/golden/validate_sales_fraud_v1.py
```

该命令必须同时执行 Schema 正向与负向案例、跨引用、会计等式、凭证内容与血缘摘要、乱序等价、反事实随机向量、可见性关系和发布唯一约束；只运行 JSON 语法检查不构成 M1A 验收。

验收：人工计算结果与夹具及纯领域测试逐项一致；多前置事件交换顺序不改变最终凭证；重复命令不重复过账。

### M1B：最小持久化闭环

在 M1A 契约上实现命令幂等、事件原子追加、会计案例、多源血缘、报告账、规范账、投影和重放。

入口条件：商业实质状态机、`accounting_case_key`、余额符号和错报方向已通过 0.3 聚焦评审。

验收：一笔正常销售贯通经济事实、企业记录、双账、账簿、报表和导出；人工结果一致；事务中断无半提交；重放不生成新事件。

### M2：最小舞弊与分支闭环

在 M1B 模型上增加分支祖先、一笔虚构销售、正交标签和盲化检测视图。

入口条件：反事实随机域、孪生分支互斥发布和配对重识别门禁已通过 0.3 聚焦评审。

验收：手工示例的五项错报金额和方向完全一致，分叉前只存在一份共享历史，盲化包无真值、未来信息和配对泄漏。

### M3：月度经营闭环

扩展主数据、销售、采购、库存、费用和控制执行，运行一个月的多交易场景。

验收：所有业务、会计、血缘、幂等和差异验证通过。

### M4：年度经营闭环

扩展至完整报告期和期后延伸期，加入真实年末大额销售与期末虚构销售。

验收：月末及年末关账通过，报告账、规范账和直接法现金流量表全部勾稽。

### M5：基准数据产品

生成 1 对黄金分支和 20 对参数化年度分支，发布研究包、盲化包、数据字典、质量报告和制品清单。

验收：一条命令能够重新生成全部制品，并通过逻辑内容摘要、文件摘要和泄漏门禁。

## 22. 第一阶段交付物

- 可执行的模块化单体和命令行程序；
- PostgreSQL 数据结构与迁移；
- 共同祖先、基线分支和舞弊分支；
- 报告账务和规范账务；
- 正常经营、真实年末大额销售和期末虚构销售场景；
- 正交真实标签与分支差异；
- JSON、Parquet 研究包和盲化包；
- 手工验算黄金案例；
- 自动化测试、质量报告、数据字典和发布清单。

## 23. 最终验收门禁

只有同时满足以下条件，第一阶段才完成：

1. 黄金场景的业务数量、金额、凭证和错报与人工答案一致；
2. 正常销售具备独立客户承诺、控制权转移和结算权利事件，规范账不从企业单据推定这些事实；
3. 每个会计案例由唯一键约束，多源事件乱序和重复到达不会重复过账；
4. 所有报告账、规范账、子账、总账和报表勾稽通过；
5. 错报金额按科目正常余额转换后计算，方向与黄金答案一致；
6. 普通重放不产生新事件，并能完整重建投影；
7. 分叉前事件只存储一次，两个子分支共享同一祖先；
8. 同一舞弊分支内的错报能由报告账与规范账计算；
9. 相同决策状态使用共享反事实随机量，`unexplained_difference` 为零；
10. 标签语义符合正交标签轴和传播规则；
11. 盲化包不包含真值、分支身份、未来信息或配对泄漏；
12. 公开盲化制品不同时包含任何一对孪生分支，配对重识别测试通过；
13. 相同版本、配置和种子产生相同逻辑内容摘要；
14. 1 对黄金分支和 20 对年度分支全部通过质量门禁；
15. 所有自动化测试、静态检查和数据契约检查通过。

## 24. 进入后续阶段的条件

0.3 只批准 M1A 立即开发。M1B 和 M2 分别满足第 21 节入口条件后开发；M3 至 M5 必须逐级验收。

只有第一阶段通过最终门禁，才设计多 Agent。未来 Agent 只能根据自己的目标和可观察信息提交结构化命令；权限、控制、经济事实、会计和标签仍由现有内核负责。

前端、完整审计程序、更多舞弊家族、多行业和模型训练分别作为独立阶段设计，不提前改变第一阶段领域语义。
