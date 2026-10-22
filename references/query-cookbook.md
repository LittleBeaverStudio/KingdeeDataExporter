# 查询实战手册

写任何取数逻辑前的自查顺序：**业务对象存不存在 → 字段标识对不对 → 载荷格式对不对 → 口径去重对不对**。
不要跳步猜，猜出来的字段标识会直接报错。

## 1. 载荷格式速查（最容易踩的坑）

| 接口 | 端点 | 载荷 |
|---|---|---|
| 登录 | `AuthService.ValidateUser.common.kdsvc` | `{"acctid":..., "username":..., "password":..., "lcid":2052}` |
| 查单据/报表 | `DynamicFormService.ExecuteBillQuery.common.kdsvc` | `{"formid":"<FormId>", "data": "<内层 JSON 序列化成**字符串**>"}` |
| 查元数据 | `DynamicFormService.QueryBusinessInfo.common.kdsvc` | `{"data": {"FormId": "<FormId>"}}` |
| 账套列表（免认证） | `AccountService.GetDataCenterList.common.kdsvc` | `{}` |

- ⚠️ `ExecuteBillQuery` 的 `data` 是**字符串**，不是对象。传 dict 会报 `MsgCode 8「接口参数 data 不能为空」`。
- ⚠️ `QueryBusinessInfo` 外面必须包一层 `data`，否则同样报"data 不能为空"。
- 内层 JSON 的键：`FormId` / `FieldKeys` / `FilterString` / `OrderString` / `TopRowCount` / `StartRow` / `Limit`。
- **返回列顺序 = `FieldKeys` 的顺序**，可安全按位置解析。
- 错误会被**包装成数据行**返回（`[[{"Result": {...}}]]`），不抛异常 → 先判 `Result.ResponseStatus.IsSuccess`。

## 2. 分页

- 单次 `Limit` 上限 2000。超过部分用 `StartRow` 递增翻页，直到返回行数 < `Limit`。
- 本工具的导出流程已内置翻页（`get_bill_data_with_filter`），无需手工分页。
- 想知道"这次会导多少行"时，先加严格过滤条件跑一次小范围，再放宽 —— 避免为了数行数全量拉取。

## 3. 去重口径（多组织环境的关键）

同一物料/客户在**创建组织**与**使用组织**下可能各有一条记录，直接按 `FNumber` 计数会虚高。

| 场景 | 推荐去重键 |
|---|---|
| 物料种数（跨组织统计品种） | `FNumber`（物料编码） |
| 物料记录数（含组织维度） | `FMATERIALID` 或 `FID` |
| 往来单位 | `FNumber` + 结算组织 |

判断方法：先按 `FNumber` 分组看有没有重复行，若有，再对比两行的组织字段，即可确认是不是多组织重复。

## 4. 单据状态字典（`FDocumentStatus`）

| 值 | 含义 |
|---|---|
| `Z` | 暂存 |
| `A` | 创建（已保存未提交） |
| `B` | 审核中（已提交待审） |
| `C` | 已审核 |
| `D` | 重新审核（**审核被驳回**，可改可删可再提交，但不可被引用） |

> 注意：不同单据的状态语义并不完全一致，且录入态/作废/关闭等状态可能另用别的字段。
> 需要按状态筛选时，**先与用户确认每个单据的口径**，不要套用一张表。

## 5. 常见故障的机制解释

- **白名单 fail-closed**：未加入「允许调用WebAPI接口用户」的账号，无论业务权限多齐全，一律被拦（`MsgCode 11`）。配置路径见 `error-playbook.md`。
- **字段权限对 WebAPI 不生效**：界面上看不到的字段，API 可能照样查得到；反之亦然。所以"界面上有"不能作为"API 能取"的依据。
- **`SubSystemId` 许可陷阱**：单据菜单发布到多个应用、但许可未买全时，`ExecuteBillQuery` 可能查不到数据。排查时在过滤条件与字段可见性之后检查许可。
- **价格类字段脱敏**：部分字段返回 `***` 而非报错，且会动态变化。需要金额时换单据类型取价，或走税额反推。
- **`FNumber` vs `FCreatorId.FName`**：字段引用（`.` 写法）作为**返回字段**稳定可用；作为**过滤条件**则因字段而异 ——
  实测 `AR_receivable` 的 `FCustomerID.FName` / `FCreatorId.FName` 可以（返回行数正确），
  而 `SAL_OUTSTOCK` 的 `FCustId.FName` 会报「数据库执行异常」。报这个错时改用内码先查出主键，或用「按已保存的方案导出」直接复用界面上已配好的条件。

## 5.5 按已保存的过滤方案取数（`FScheme` 机制）

金蝶列表的「过滤方案」存在基础对象 `BOS_FilterScheme`（`FScheme` 字段），内容是一段 XML 外壳包三段 JSON：

```text
<ListFilterSchemeEntity>
  <FilterSetting>[{"FieldName":"FDATE","Compare":"63","Value":"","Left":"","Right":"","Logic":"0"}]</FilterSetting>
  <ColumnSetting>[{"F":"FCUSTOMERID_FName","V":1,...}]</ColumnSetting>
  <SortSetting>[]</SortSetting>
  <StatusFilterSetting>[{"Key":"FDOCUMENTSTATUS","Value":"[all]"}]</StatusFilterSetting>
</ListFilterSchemeEntity>
```

- `<FilterSetting>` 的结构与 `ExecuteBillQuery` 的 `FilterString` **完全相同**（`Left/FieldName/Compare/Value/Right/Logic`），
  所以可以直接把这段 JSON 数组当 `FilterString` 传 —— 不需要把比较符编码翻译成字符串。
- 已实测的比较符编码（同一字段、同一账套）：

  | Compare | 含义 | 例子 / 验证方式 |
  |---|---|---|
  | `17` | 等于（文本 / 引用名称精确匹配） | `FCUSTOMERID.FName` 17「某某医疗科技有限公司」→ 222 行（客户名精确匹配，非模糊） |
  | `67` | 等于（文本；**不是**包含） | `FRECACCOUNTNAME` 67「交通」→ 0 行，同值用 17 → 43 行 |
  | `105` | 等于（单选枚举/引用，**不认逗号多值**） | `FDocumentStatus` 105「C,Z」→ 0 行 |
  | `106` | 属于 / IN（值可写 `C,Z`） | `FDocumentStatus` 106「C,Z」→ 全量 7042 行 |
  | `63` | 相对日期区间「本期/本月」 | `FDATE` 63 + 空值 → 2026-10-08 ~ 10-21（当期实际数据范围） |
  | `92` | 相对日期区间「上期/上月」 | `FDATE` 92 + 空值 → 2026-09-14 ~ 09-30 |
  | `107` | 日期「小于等于今天」（= 已到期） | `FENDDATE_H` 107 + 空值 → 6960 行，到期日最大 = 今天 |

  日期类的 `63/92/107` **不需要传值**，由服务端按当天解析 —— 所以按方案取数天然是"当期"口径，不会因为存了固定日期而失效。

  ⚠️ `106` 的语义要点：把 `属于C` 和 `属于Z` 拆成**两行**传进去，接口按 AND 解释 → 0 行；
  必须合并成一行 `Value="C,Z"`，才和界面口径一致。
- `<ColumnSetting>` 里 `V=1` 的是显示列，`F` 是列表列名（`FCUSTOMERID_FName`），取数接口要写成 `FCUSTOMERID.FName`。
  个别列在本账套已不存在（自定义字段被删）会报「元数据中标识为 XXX 的字段不存在」，跳过该列即可。
- 报表对象的方案（`<SchemeEntity>` 外壳）是**版式方案**，`FilterSetting` 恒为空，不能当列表方案用。

命令行入口：`--list-schemes [表单]` 看方案，`--scheme "方案名"` 导出（见 `SKILL.md` 同名章节）。

## 6. 场景配方（可复制）

### 应收账龄 / 应收款汇总

```bash
# 应收款汇总表（按结算组织）
python data_exporter.py --org all --only AR_SumReport --start 2026-01-01 --end 2026-06-30

# 应收单明细 + 补充字段
python data_exporter.py --only AR_receivable --fields "AR_receivable:FNOINVOICEAMOUNT" \
  --start 2026-01-01 --end 2026-06-30 --org ORG001
```

### 资金头寸日报

```bash
python data_exporter.py --only 资金头寸表,银行存款流水账 --start 2026-06-01 --end 2026-06-30
```

> 资金头寸表的参数口径（如 `FAllCashAccount: True / FAllBankAccount: False`）已在工具内固化为默认 `model`。
> 口径取错会返回 0 行 —— 这时先怀疑参数口径，**不要**判定为"资金模块没建档"。

### 存货异常筛查（零数量有金额 / 有数量负金额 / 异常价格）

```bash
python data_exporter.py --only 存货收发存汇总表,存货收发存明细表 \
  --start 2026-06-01 --end 2026-06-30 --org ORG001
```

导出后在 Excel 里按「期末结存数量 = 0 且金额 ≠ 0」「数量 > 0 且金额 < 0」筛查；
需要物料编码/名称/批号/仓库/本期收发/期末结存共 10 项字段时，用 `--fields` 追加。

### 员工报销台账

```bash
python data_exporter.py --only 费用申请单,费用报销单,出差申请单,差旅费报销单 \
  --start 2026-01-01 --end 2026-06-30 --org all
```

需要审批进度时注意：**WebAPI 读不到"当前处理人"**（见 `error-playbook.md` 第 6 节），
只能按「单据状态 + 申请人」出待审清单。

### 采购执行与逾期未收料

```bash
python data_exporter.py --only 采购订单执行明细表 --start 2026-01-01 --end 2026-06-30 --org ORG001
```

由于官方导出为明细口径，「逾期未收料」需在本地按「交货日期 < 报告日 且 未收料数量 > 0」筛选。

## 7. 与下游技能的衔接

导出的 Excel 可直接交给 `kingdee-data-analyzer` 生成 HTML 报告：

```bash
python analyzer.py --type sales --excel "D:/data/金蝶导出.xlsx" --start 2026-01-01 --end 2026-06-30
```

也可以让 analyzer 自动调用本工具实时取数（两者放同一父目录时会自动发现）。
