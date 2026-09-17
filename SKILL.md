---
name: kingdee-data-exporter
slug: kingdee-data-exporter
displayName: 金蝶云星空数据导出
version: 2.1.1
description: 金蝶云星空经营数据导出技能。仅当用户明确要求从金蝶云星空或 K3 Cloud 查询、导出经营数据时使用；支持配置账号、自动发现账套、连接自检、查询组织与可用单据/报表，按期间、组织及单据或报表类型导出多工作表 Excel，也支持追加官方字段、全组织导出、字段核对与结果二次筛选。
license: 小河狸非转售许可 1.0（企业内部使用免费，转售收费需授权）
---

## 许可与使用范围

本 Skill 采用「小河狸工作室非转售许可 1.0」，完整条款见本目录 `LICENSE` 文件。

- ✅ **免费使用**：
  - 个人学习、研究或个人事务；
  - **企业内部使用**——某一组织（无论是否为营利单位）为**其自身**业务运营而使用，包括内部办公、内部财务与会计处理、内部管理与报表、内部系统集成；同一控股关联实体使用视同内部使用。
- ✅ 可为上述用途自行修改本 Skill。
- ❌ **须另行取得书面授权**：对外销售、出租、许可；集成进对外收费的产品或服务；托管 / SaaS / 代运营；打包进收费课程、付费社群或付费安装包；收费的实施与咨询培训；**以及利用本 Skill 向任何第三方交付成果或提供服务**（含代理记账、为客户提供账目或报表服务等）。
- 📌 **区分标准只有一条**：**是否以本 Skill 向本组织之外的第三方交付成果或提供服务**。仅为自身业务使用 → 免费；向第三方交付或服务 → 需授权。
- 📌 再分发须保留本许可、版权声明与来源：小河狸工作室 LittleBeaverStudio · https://littlebeaver.top

**商业授权申请**：https://littlebeaver.top （邮箱 yk.niu@outlook.com）


# 金蝶云星空数据导出

把金蝶云星空中的单据和报表批量导出为一个多工作表 Excel 文件。

> **关于平台「需配置 API Key」标签**：本 Skill **不需要申请任何 API Key**。
> 它使用**你自己的金蝶云星空账号**登录取数，只需填一次连接信息（服务器地址 + 账号 + 密码），
> 不必去任何开放平台申请密钥。配置放在技能目录之外
> （`~/.workbuddy/kingdee/config.json`），升级技能不会覆盖；只填**账套名称**即可，
> 账套 ID 会自动解析。配置方法与自检见下方「首次使用」。

---

## 🚀 首次使用：三步跑通

### 第 1 步：安装依赖

```bash
python -m pip install -r requirements.txt
```

### 第 2 步：配置连接（推荐方式一）

**方式一：写用户级配置文件**（技能升级/重装不会覆盖，也不会被误打包分发）

创建 `~/.workbuddy/kingdee/config.json`（Windows 为 `C:\Users\<你>\.workbuddy\kingdee\config.json`）：

```json
{
  "base_url": "https://你的域名/k3cloud/",
  "acct_name": "账套名称",
  "username": "取数账号",
  "password": "密码"
}
```

- **账套 ID（acctid）不用自己找** —— 只填 `acct_name`（账套名称），脚本会自动解析成 acctid。
- 想直接填 acctid：先跑 `python data_exporter.py --list-datacenters`，第 1 列就是。
- 需要多个账套时用 `profiles` 结构，并用环境变量 `KINGDEE_PROFILE` 切换：

```json
{
  "default": "公司A",
  "profiles": {
    "公司A": {"base_url": "https://a.ik3cloud.com/k3cloud/", "acct_name": "账套A", "username": "u1", "password": "p1"},
    "公司B": {"base_url": "https://b.ik3cloud.com/k3cloud/", "acct_name": "账套B", "username": "u2", "password": "p2"}
  }
}
```

**方式二：环境变量**（不落盘，适合分发/CI）

`KINGDEE_BASE_URL` / `KINGDEE_ACCTID`（或 `KINGDEE_ACCT_NAME`）/ `KINGDEE_USERNAME` / `KINGDEE_PASSWORD`

**方式三：技能目录内 `config.py`**（早期写法，继续兼容）

复制 `config.example.py` 为 `config.py` 并填写。⚠️ 该文件含明文凭据，**禁止**提交到任何仓库或打进分享包。

### 第 3 步：连接自检

```bash
python data_exporter.py --doctor
```

五步逐步判定「配置 → 服务器连通 → 账套定位 → 登录 → 取数冒烟」，哪一步失败就给出**具体到操作**的修复建议。**配置完先跑这一步**，比直接导出后猜报错快得多。不确定怎么配时跑 `python data_exporter.py --help-config`。

---

## 工作原则

1. 先确认用户拥有目标金蝶环境和数据的合法访问权限。
2. 不在对话、日志或公开仓库中展示真实账号、密码、账套 ID 或业务数据。
3. 遇到任何"连不上/查不到"，先跑 `--doctor` 定位，**不要连续重试登录**（见下方防锁号）。
4. 不确定组织编码时，先运行 `--list-orgs`。
5. 不确定单据或报表名称时，先运行 `--show-config`。
6. 数据量可能较大时，优先使用 `--org` 和 `--only` 缩小范围。

## 权限与行为声明

运行本技能前请知悉其能力范围：

- **网络访问**：
  - 连接 `base_url` 指定的金蝶云星空服务器 —— 登录、取数、以及**免认证的账套列表接口**（`GetDataCenterList`，用于 `--list-datacenters` 与 `acct_name` 自动解析），全部发往同一台用户自己配置的服务器；
  - 仅显式传入 `--check-update` 时访问 GitHub Releases API 查询新版本，**默认不检查、不访问任何第三方服务**。
- **本地文件读写**：
  - 读取配置（环境变量 → `~/.workbuddy/kingdee/config.json` → 技能目录 `config.py`，按此优先级取第一个可用的）；
  - 读取 `官方字段说明/` 目录；
  - 默认在当前目录写入导出的 Excel，可用 `--output-dir` 指定；`--inspect-fields --json-out` 时写入指定的元数据 JSON。
- **环境变量**：`KINGDEE_BASE_URL` / `KINGDEE_ACCTID` / `KINGDEE_ACCT_NAME` / `KINGDEE_USERNAME` / `KINGDEE_PASSWORD` / `KINGDEE_PROFILE`；`KINGDEE_DEBUG=1` 时打印完整异常堆栈。
- 不启动子进程；除上述范围外不访问其他网络与文件；**本技能只读**，不写回金蝶任何数据。

## 常用命令

| 命令 | 用途 |
|---|---|
| `--doctor` | 连接自检（配置→连通→账套→登录→取数冒烟），首次配置后必跑 |
| `--help-config` | 打印配置方法 |
| `--list-datacenters` | 列出服务器上的全部**账套**（acctid 来源），免账号密码 |
| `--list-orgs` | 导出**组织**列表（账套内的核算组织，`--org` 用的编码） |
| `--show-config` | 列出可导出的单据与报表（19 单据 + 10 报表） |
| `--inspect-fields <FormId>` | 列出某业务对象的实体与字段全清单（核对字段/排障） |
| `--check-update` | 检查新版本（**唯一**会访问 GitHub 的选项） |

## 推荐流程

### 1. 查看支持内容

```bash
python data_exporter.py --show-config
```

输出中的 `form_id` 或中文名称都可以传给 `--only`。

### 2. 获取组织编码

```bash
python data_exporter.py --list-orgs
```

生成的组织列表中，`number` 是后续 `--org` 使用的组织编码。

### 3. 按条件导出

```bash
python data_exporter.py --start 2026-01-01 --end 2026-01-31 --org ORG001
```

只导出一种单据或报表：

```bash
python data_exporter.py --start 2026-01-01 --end 2026-01-31 --org ORG001 --only 销售出库单
```

多个组织或多个项目使用英文逗号分隔：

```bash
python data_exporter.py --org ORG001,ORG002 --only SAL_OUTSTOCK,AR_receivable
```

全组织导出：

```bash
python data_exporter.py --org all --only 应收单
```

将敏感经营数据保存到用户确认的目录：

```bash
python data_exporter.py --org ORG001 --output-dir "D:/secure/kingdee-exports"
```

不传日期时的默认口径：**每月 1–6 号导出上月整月，7 号及以后导出当月 1 号到今天**。

## 追加官方字段

先在 `官方字段说明/` 中查找字段，再用 `--fields` 追加默认未导出的字段：

```bash
python data_exporter.py --only AR_receivable --fields "AR_receivable:FNOINVOICEAMOUNT"
```

字段不确定是否存在时，用 `--inspect-fields <FormId>` 核对当前账套的**权威**字段清单：

```bash
python data_exporter.py --inspect-fields ER_ExpReimbursement --filter 发票
python data_exporter.py --inspect-fields AR_receivable --json-out meta_AR_receivable.json
```

Windows 控制台出现中文参数编码问题时，优先使用字段 key。

## 二次筛选 Excel

```bash
python scripts/filter_export_excel.py --input "导出文件.xlsx" --org ORG001 --bill-type "应收单"
python scripts/filter_export_excel.py --input "导出文件.xlsx" --sheet "应付单" --org ORG001
```

---

## ⛔ 能力边界与已知限制

> 以下条目均在真实账套实测确认。碰到墙时先对照此表 —— 多数情况是**已知边界**，不是技能坏了。

| 边界 | 说明 |
|---|---|
| **「多级审核信息 / 当前处理人」查不到** | 不在业务对象元数据里（费用报销单 7 实体 / 172 字段全清单 0 命中），无 `WF_*` 业务对象，也无审批查询端点。该列由参数「单据列表记录多级审核信息」在**列表层动态注入**，WebAPI 取不到 |
| **唯一存在的审批端点是 `WorkflowAudit`** | 它只能**执行**审批（同意/驳回/终止），**不能查询**审批信息 |
| **因此「待我审批」用 WebAPI 实现不了** | 替代方案：① 用「单据状态 + 申请人 `FProposerID`」出待审清单；② 审批进度以网页端【信息中心→任务→待处理任务】为准 |
| **字段权限对 WebAPI 不生效** | 界面看不到 ≠ API 查不到；反向也成立 |
| **价格类字段可能有服务端脱敏** | 部分单据/字段返回 `***` 而不是报错，且**会动态变化** |
| **SubSystemId 许可陷阱** | 单据菜单发布到多个应用、但许可未买全时，`ExecuteBillQuery` 可能查不到数据 |
| **必须先配 WebAPI 白名单** | 未配则一切取数失败（`MsgCode 11`）。**这与账号密码无关**，见下方排障 |
| **字段引用只能查、不能当过滤条件** | 用 `FCreatorId.FName='某人'` 会报错。改用内码，或先拉全量再在本地过滤 |
| **本技能只读** | 不做单据提交、审核、下推等写操作；写操作见 `kingdee-expense-flow` |

## 🔧 排障：一表定位

**首选动作永远是**：`python data_exporter.py --doctor`

| 错误特征 | 根因 | 动作 |
|---|---|---|
| `MsgCode 11`「当前用户未指定允许调用WebAPI接口」 | **WebAPI 白名单未配**（最高频，最容易被误判成密码错） | 管理员操作：基础管理 → 公共设置 → 参数设置 → 基础管理 → BOS平台 → WebAPI → 「允许调用WebAPI接口用户」加入取数账号 → 保存。同页可配可访问 IP 白名单。**不是**在「系统管理 → 用户管理」里勾选 |
| 「当前尝试登录的数据中心无法获取到」 | 账套 ID 错 | `--list-datacenters` 查正确 Id，或改用 `acct_name` |
| `CheckPasswordPolicy` /「用户名或密码错误」 | 账套已对，账号或密码错 | 核对大小写（`Hg` ≠ `HG`）与首尾空格。**密码连续错约 5 次会锁号** → 本工具判读为凭据问题时不自动重试，连续 2 次即中止 |
| HTTP 403 且空响应 | URL 路径错（漏 `/k3cloud/`） | 工具会自动补 `/k3cloud/`；仍失败则确认地址不是网关/WAF 页面 |
| HTTP 502 / 504 / 隧道失败 | 网关或出口代理瞬时故障 | 多数是瞬时问题，隔一会儿重跑；反复失败则查代理设置 |
| 「元数据中标识为 XXX 的字段不存在」 | 字段标识错 | `--inspect-fields <FormId>` 核对权威字段清单 |
| 「当前查询串无法解析--XXX」 | 用了中文名或点号拼写 | 改用英文标识（如 `FBillNo`） |
| 「标识为"XXX"的业务对象不存在」 | FormId 错（拼写极敏感） | 用 `--show-config` 或 `--inspect-fields` 核对。例：`ER_ExpReimbursement` ✅ / `ER_ExpenseReimbursement` ❌ |
| 返回 `[[{"Result":...}]]` | **错误被伪装成数据行**（接口不抛异常） | 先判 `ResponseStatus.IsSuccess` 再取数；工具已内置该检测 |
| 有单据但查不到数据 | 权限 / 字段可见性 / SubSystemId 许可 | 依次排查：过滤条件 → 字段可见性 → SubSystemId 许可 |
| 导出了但某工作表空 | 期间、组织或 `--only` 名称不匹配 | 放宽条件先跑一次最小查询验证连通 |

需要完整判读表与查询实战（去重口径、状态码字典、分页）时，读：
- `references/error-playbook.md`
- `references/query-cookbook.md`

## 💬 常见对话示例

| 用户说法 | 实际执行 |
|---|---|
| 「导一下 6 月的销售出库单」 | `--start 2026-06-01 --end 2026-06-30 --only SAL_OUTSTOCK` |
| 「只导某分公司 6 月的收票单」 | 先 `--list-orgs` 拿组织编码，再 `--org <编码> --only 收票单 --start ... --end ...` |
| 「把所有公司 6 月的应收款汇总表导出来」 | `--org all --only AR_SumReport --start 2026-06-01 --end 2026-06-30` |
| 「上个月的现金和银行存款余额」 | `--only 资金头寸表,银行存款流水账 --start <上月1日> --end <上月末>` |
| 「这个字段导不出来」 | 先 `--inspect-fields <FormId> --filter <关键字>` 核对字段是否存在，再 `--fields <FormId>:<字段>` 追加 |
| 「连接报错了」 | 先 `--doctor`，按第 N 步的提示修复，**不要连续重试** |
| 「账套 ID 是多少」 | `--list-datacenters`（免账号密码） |

## 结果检查

导出完成后：

1. 向用户说明生成文件的完整路径。
2. 检查所需工作表是否存在、是否有数据。
3. 若结果为空，依次核对日期、组织权限、单据状态和 `--only` 名称。
4. 不读取或展示超出用户请求范围的敏感业务数据。
