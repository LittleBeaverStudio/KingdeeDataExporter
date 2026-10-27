---
name: kingdee-data-exporter
slug: kingdee-data-exporter
displayName: 金蝶云星空数据导出
version: 2.4.6
description: 金蝶云星空经营数据导出技能。仅当用户明确要求从金蝶云星空或 K3 Cloud 查询、导出经营数据时使用；支持配置账号、自动发现账套、连接自检、查询组织与可用单据/报表，按期间、组织及单据或报表类型导出多工作表 Excel，也支持按金蝶里已保存的过滤方案（列表方案的条件+显示列+排序）直接导出、追加官方字段、全组织导出、字段核对与结果二次筛选；含对象探查（列子系统、列业务对象、体检对象能否取数），用于不知道 FormId 时定位任意业务对象。更多效率工具请关注公众号：财务小河狸。
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

> **2.4.4 新增：按金蝶里已保存的过滤方案导出**
>
> 你在金蝶列表页【过滤】→ 设好条件 →【保存方案】存下来的方案（如应收单的「日报表」），
> 现在可以一条命令原样复用：**条件、显示列、排序全套照搬**，不用再在命令行重复描述。
> `--list-schemes` 看有哪些方案，`--scheme "方案名"` 直接导。详见下方「按已保存的方案导出」。

> **2.4.x 相比 2.3.x 改了什么**（都不改变已有用法，老命令参数照旧）：
>
> - **依赖减到两个**：去掉 `requests`、`python-dateutil`，HTTP 与日期改用标准库 →
>   受控内网 / 装不上轮子的机器也能跑；连接级重试 + 中文编码自适应解码（UTF-8 / GBK）。
> - **新增对象探查**：`--list-subsystems` / `--list-objects` / `--test-form`，
>   不知道 FormId 时也能定位到凭证、资产卡片这类清单外的对象。
> - **Excel 交付格式**：表头加粗、首行冻结、列宽按内容自适应、自动筛选。
> - **审计日志**：`~/.workbuddy/kingdee/audit.log` 记「谁在什么时候导了什么」，只记元数据。
> - **报错判读更准**：组织列表失败会分清「没权限」和「对象不存在」—— 这两种的处理动作完全不同。
> - **版本号单一来源** + 更新检查兼容「语义版本」与「日期形态」两种 tag（旧版本换了 tag 形态后提示会永久失效）。

---

## 🚀 首次使用：三步跑通

### 第 1 步：安装依赖

```bash
python -m pip install -r requirements.txt
```

> **只有两个依赖**：`pandas`（数据整理）、`openpyxl`（写 Excel）。
> 网络请求、凭据加密、日期计算全部用 Python 标准库实现，**不需要 requests / python-dateutil**。
> 这一点很实际：很多客户内网装不上轮子、或者把已装的 pandas 强制降级会连带崩掉别的系统，
> 依赖越少，装成功的概率越高。装不上时加国内镜像：
>
> ```bash
> python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```
>
> 版本要求：Python 3.8+；pandas 2.x、openpyxl 3.1+。

### 第 2 步：配置连接（推荐方式一）

**方式一（推荐）：配置向导 —— 弹窗填写，明文不落盘**

```bash
python setup_credentials.py
```

弹窗里**只需填 3 项：公司名（账套名称）、用户名、密码**。凭据用 **Windows 系统加密（DPAPI）**
保存到 `~/.workbuddy/kingdee/credentials.bin`：

- 🔒 绑当前 Windows 用户 —— 同机其它用户读不出，拷到别的机器也解不开；
- 🔒 不写明文文件、不进对话记录、不落日志（只回报字段名是否存在，**永不回显值**）；
- 🔒 在技能目录之外，升级 / 重装 / 打包都不会带上它；
- 🔑 **本文件是全系列唯一的金蝶凭据写入者**：分析类技能、报销助手都读它，谁都不另存一份。
  发票云密钥不在这里（在 `piazzone.bin`，由报销助手自己管），所以两边不会互相覆盖。

**不用要求用户先装 Python 或 tkinter** —— 向导自己找路，全程零安装：

| 层 | 行为 |
|---|---|
| L0 | 当前解释器带 tkinter → 弹窗 |
| L1 | 没带 → 找本机**已装的、带 tkinter 的另一个 Python**，由它弹窗（不改系统 PATH） |
| L2 | 还是没有 → **原生 Windows 表单**（`win32_form.py`，纯 ctypes 画标准控件，任何 Windows 都有） |
| L3 | 表单也起不来 → 独立控制台里的文字向导（密码走那个窗口自己的 stdin） |

> 🚫 **禁止静默安装**任何运行时。tkinter 不是 pip 包，装它等于替换用户的 Python；
> UAC / 企业策略 / 离线 / 安全软件任一环节都能让它失败，并留下半装状态。

只看状态不开窗：`python setup_credentials.py --check`；清除已保存凭据：`--delete`；
改密码（要求输两次，避免打错撞锁号）：`python setup_credentials.py --change-key`。

**退出码（按码判断，不要看输出文字）**：`0` 已保存 ｜ `10` 用户取消/关窗/空闲超时（**没改成，别盲目重跑**）
｜ `12` 已有一个配置窗口开着 ｜ `2` 环境不支持 ｜ `3` 保存失败。

**从旧版明文迁移**：若本机已有明文 `~/.workbuddy/kingdee/config.json`，跑一次向导即可 ——
它会读入旧值、加密保存、**默认勾选删除该明文文件**，并提示**到金蝶后台修改一次密码**。

**方式二：写用户级配置文件**（旧版写法，兼容保留，**不推荐**——密码是明文）

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

**方式三：环境变量**（**可选**，不设也能用；适合 CI / 无人值守）

`KINGDEE_BASE_URL` / `KINGDEE_ACCTID`（或 `KINGDEE_ACCT_NAME`）/ `KINGDEE_USERNAME` / `KINGDEE_PASSWORD`

> ⚠️ **别把"环境变量更安全"理解成"本机保密"**：环境变量的好处是**不会被误提交进 git /
> 被顺手打包带走**；但它在本地**并不保密** —— 同一 Windows 用户下其它进程可读，还会随
> 子进程继承、进崩溃转储与日志。本机保密请用方式一（DPAPI）。

**方式四：技能目录内 `config.py`**（早期写法，继续兼容）

复制 `config.example.py` 为 `config.py` 并填写。⚠️ 该文件含明文凭据，**禁止**提交到任何仓库或打进分享包。

**读取优先级：环境变量 > 系统加密凭据 > 明文 `config.json` > 技能目录 `config.py`。**

> ⛔ **明文会被强制阻断**：只要本机还存在**含密码的明文** `~/.workbuddy/kingdee/config.json`，
> 本技能会**直接阻断、拒绝取数**，并打印迁移 3 步（改密码 → 跑 `python setup_credentials.py`
> 录新密码 → 向导自动删除明文文件）。软提示等于没有 —— 明文还能用就永远不会有人去迁移。
> 过渡期确有自动化必须沿用明文的，可显式设 `KINGDEE_ALLOW_PLAINTEXT=1`（会打印告警）。

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
4. 不确定组织编码时，先运行 `--list-orgs`（缺组织机构权限时会明确告知，此时改用 `--org <编码>`）。
5. 不确定单据或报表名称时，先运行 `--show-config`；内置清单之外的，用 `--list-objects` 找 FormId。
6. 数据量可能较大时，优先使用 `--org` 和 `--only` 缩小范围。
7. 拿到一个陌生 FormId，先 `--test-form` 体检再取数，不要直接导。

## 权限与行为声明

运行本技能前请知悉其能力范围：

- **网络访问**：
  - 连接 `base_url` 指定的金蝶云星空服务器 —— 登录、取数、以及**免认证的账套列表接口**（`GetDataCenterList`，用于 `--list-datacenters` 与 `acct_name` 自动解析），全部发往同一台用户自己配置的服务器；
  - 仅显式传入 `--check-update` 时访问 GitHub Releases API 查询新版本，**默认不检查、不访问任何第三方服务**。
- **本地文件读写**：
  - 读取配置（环境变量 → `~/.workbuddy/kingdee/config.json` → 技能目录 `config.py`，按此优先级取第一个可用的）；
  - 读取 `field-docs/` 目录（字段中文名 ↔ 字段标识对照表，28 个对象）；
  - 默认在当前目录写入导出的 Excel，可用 `--output-dir` 指定；`--inspect-fields --json-out` / `--list-objects --json-out` 时写入指定的 JSON；
  - 追加一行**审计记录**到 `~/.workbuddy/kingdee/audit.log`（见下）。
- **审计日志**：每次导出/失败/登录失败追加一行 JSON，只记**时间、动作、对象 FormId、组织、行数、版本、成功与否**。
  不记业务数据内容、不记账号密码。目的是事后能回答「这批数据是什么时候、导了哪个对象、多少行、成功与否」。
  （**不记录账号名**——按本技能的原则，真实账号不进任何日志；需要追人请结合操作系统的登录审计。）
  关闭方式：`KINGDEE_AUDIT=0`。
- **环境变量**：`KINGDEE_BASE_URL` / `KINGDEE_ACCTID` / `KINGDEE_ACCT_NAME` / `KINGDEE_USERNAME` / `KINGDEE_PASSWORD` / `KINGDEE_PROFILE`；`KINGDEE_DEBUG=1` 打印完整异常堆栈；`KINGDEE_AUDIT=0` 关闭审计；
  `KINGDEE_INSECURE_SSL=1` 关闭 HTTPS 证书校验（**仅**用于自建内网自签证书，默认关闭且会打印告警）。
- 不启动子进程；除上述范围外不访问其他网络与文件；**本技能只读**，不写回金蝶任何数据。

## 常用命令

| 命令 | 用途 |
|---|---|
| `--doctor` | 连接自检（环境依赖→配置→连通→账套→登录→取数冒烟），首次配置后必跑 |
| `--help-config` | 打印配置方法 |
| `--list-datacenters` | 列出服务器上的全部**账套**（acctid 来源），免账号密码 |
| `--list-orgs` | 导出**组织**列表（账套内的核算组织，`--org` 用的编码） |
| `--show-config` | 列出可导出的单据与报表（19 单据 + 10 报表） |
| `--list-subsystems` | 列出账套内的**子系统（模块）编号**，如 GL / AR / STK |
| `--list-objects` | 列出**业务对象与 FormId**（可用 `--object-sub` / `--object-kw` 收窄） |
| `--test-form <FormId>` | **体检**某个对象：元数据能否读、取数是否通 |
| `--inspect-fields <FormId>` | 列出某业务对象的实体与字段全清单（核对字段/排障） |
| `--form-id <FormId>` | 通用取数：导出**任意**业务对象，不限于内置清单 |
| `--list-schemes [表单]` | 列出金蝶里**已保存的过滤方案**（给表单看明细，不给则按对象汇总） |
| `--scheme <方案名>` | **按已保存的方案导出**：条件 + 显示列 + 排序全套复用；不带 `--form-id` 时按方案名自动定位表单 |
| `--scheme-index <n>` | 同名方案有多个时选第几个（序号见 `--list-schemes`） |
| `--preview-fields <对象>` | 不联网预览某对象的本地字段清单（填凭据前即可看，如 `--preview-fields SAL_OUTSTOCK` 或 `--preview-fields 销售出库单`） |
| `--check-update` | 检查新版本（**唯一**会访问 GitHub 的选项） |
| `--version` | 打印当前版本与构建日期 |

### 查询模板（每月重复取数别再复述参数）

财务每月结账的取数条件（组织、期间、单据类型）几乎不变，把这套组合存成命名模板，
下次直接 `--query <名字>` 调，也不用每个月把参数重新说一遍。模板只存「取什么 / 给谁」，**不存凭据**。

```bash
# 保存当前参数组合为模板（period 用相对期间，模板才能长期有效）
python data_exporter.py --only SAL_OUTSTOCK --org 101 --period last-month --output-dir D:/月结 --save-query 月结销售出库

# 下个月直接调用，期间自动往前滚一个月
python data_exporter.py --query 月结销售出库

# 查看已保存的模板
python data_exporter.py --list-queries
```

- `--save-query <名字>`：把本次的 `--org` / `--only` / `--form-id` / `--fields` / `--filter-string` / `--output-dir` / `--period`（或 `--start`+`--end`）存下来。
- `--query <名字>`：加载模板，参数回填到本次运行（命令行显式给的值优先于模板）。
- `--period` 支持：`last-month` / `this-month` / `last-quarter` / `this-quarter` / `last-year` / `this-year` / `YYYY-MM`（该月整月）。
  **务必用相对期间，别存固定日期** —— 固定日期的模板第二个月就失效了。
- 模板文件在 `~/.workbuddy/kingdee/queries.json`，可手改、可进 git 与同事共享，不影响凭据。
- 模板里若写了 `form_id`，则走通用取数模式（`--form-id`），`period` 会拼成 `FDate` 过滤条件自动套用。

## 对象探查：不知道 FormId 时怎么办

内置清单之外的对象（凭证、资产卡片、即时库存、二开单据…）要取数，必须知道 FormId。
以前只能靠猜或翻文档，现在按这个顺序走，一条链下来：

```bash
# ① 先看这台服务器上有哪些模块（编号 + 名称 + 对象数）
python data_exporter.py --list-subsystems

# ② 钻进某个模块，看它下面有哪些业务对象（显示 FormId）
python data_exporter.py --list-objects --object-sub GL

# ③ 只知道名字不知道 FormId，就按关键字搜（跨模块）
python data_exporter.py --list-objects --object-kw 凭证

# ④ 选定后先体检：元数据能不能读、取数能不能通
python data_exporter.py --test-form GL_Voucher

# ⑤ 体检通过再取数
python data_exporter.py --form-id GL_Voucher --filter-string "FDate>='2026-09-01'"
```

**一个必须知道的坑**：**不要按 FormId 前缀猜模块归属**。
BOS 设计器动态建模生成的对象，FormId 是纯数字码或 GUID（形如 `0ebcf871-cecc-4e2e-...`），
不带任何模块前缀，按 `GL%` / `AR%` 这类前缀去筛会漏掉一大片。
按子系统筛（`--object-sub`）才是全的 —— 子系统归属存在注册表的 `FSubSystemId` 字段里。

**「在册」不等于「能取数」**：注册表里有的对象，可能是单据转换规则、打印模板、迁移方案，
它们根本不是表单类对象，`--form-id` 一定失败。所以第 ④ 步的体检不能省。
`--test-form` 会分开报「元数据」和「取数」两关，哪一关断了一眼看得出。

完整清单可以落盘（`--json-out`），便于后续脚本化：

```bash
python data_exporter.py --list-objects --object-sub AR --json-out ar_objects.json
```

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

`field-docs/` 下每个对象一个文件（按 **FormId** 命名，如 `AR_receivable.txt`），
内容是「中文字段名: 字段标识」的对照表。用 `--fields` 追加默认未导出的字段：

```bash
python data_exporter.py --only AR_receivable --fields "AR_receivable:FNOINVOICEAMOUNT"
```

也能直接写中文名（对照表里有的字段）：

```bash
python data_exporter.py --only 应收单 --fields "应收单:价税合计"
```

- 同一中文名在表头和明细里重复时（如「价税合计」），取**文档中首次出现**的那条（表头字段）；
  要明细字段就用英文标识，最准。
- 文件名用 FormId 而不是中文名，是为了跨系统解压/压缩包传递时不会变成乱码
  （2.3.x 及更早用的是 `官方字段说明/<中文名>.txt`，代码仍能回退读取，不影响老目录）。

字段不确定是否存在时，用 `--inspect-fields <FormId>` 核对当前账套的**权威**字段清单：

```bash
python data_exporter.py --inspect-fields ER_ExpReimbursement --filter 发票
python data_exporter.py --inspect-fields AR_receivable --json-out meta_AR_receivable.json
```

Windows 控制台出现中文参数编码问题时，优先使用字段 key。

## 通用取数：任意业务对象

内置清单之外的业务对象（凭证 `GL_Voucher`、资产卡片 `FA_Card`、即时库存 `STK_Inventory` 等），
用 `--form-id` 直接取，**不需要改代码**——下游分析类 Skill 靠它复用本技能，不必各自实现取数逻辑：

```bash
# 取全字段（自动读取该对象的完整字段清单）
python data_exporter.py --form-id GL_Voucher --filter-string "FDate>='2026-09-01' and FDate<='2026-09-30'"

# 只取指定字段（先用 --inspect-fields 核对标识）
python data_exporter.py --form-id FA_Card --fields "FNumber,FName,FAssetOrgID"

# 不带过滤条件 = 导出该对象全部数据（注意数据量）
python data_exporter.py --form-id STK_Inventory
```

- 输出仍是 Excel，工作表名自动取该对象的中文名。
- 日期等过滤条件直接写金蝶 `FilterString`，用 `--filter-string` 传入。
- ⚠️ **报表类对象不支持**（如 `GL_RPT_AccountBalance`、`AR_SumReport`）——
  它们不是业务对象，走的是报表接口，请用 `--only` 从内置清单取。

## 按已保存的方案导出（不用再重复写过滤条件）

金蝶列表页里【过滤】→ 设好条件 →【保存方案】存下来的方案，可以**原样拿来取数**：

```bash
# ① 先看这个对象下有哪些方案（中文表单名也认）
python data_exporter.py --list-schemes 应收单
python data_exporter.py --list-schemes AR_receivable

# ② 按方案导出：条件、显示列、排序全部照搬方案里的设置
python data_exporter.py --form-id AR_receivable --scheme "日报表" --output-dir D:/取数

# ③ 方案名全账套唯一时，连 --form-id 都可以省（自动定位表单）
python data_exporter.py --scheme "日报表" --output-dir D:/取数

# ④ 只想要方案的条件、列自己指定
python data_exporter.py --form-id AR_receivable --scheme "日报表" --fields FBILLNO,FDATE,FCUSTOMERID.FName
```

`--list-schemes` 不给表单时按对象汇总，用来找"我那个方案到底存哪了"：

```text
FormId                      方案数  示例方案
AR_receivable               20      待审核应收单、待处理开票核销、本月
AR_RECEIVEBILL              21      本周、快速核销默认方案、交行收款单
SAL_OUTSTOCK                24      Default Scheme、本月待确认应收的出库单
```

**它和 `--query` 模板的区别**：`--query` 是**本工具自己**存的参数组合（在 `~/.workbuddy/kingdee/queries.json`）；
`--scheme` 读的是**金蝶里**的方案，财务在金蝶界面改一次，下次取数立刻生效，不用两边维护。

### 实现口径（为什么不会错数）

- 金蝶的方案存在基础对象 `BOS_FilterScheme`（字段 `FScheme`），里面是
  `<FilterSetting>` / `<ColumnSetting>` / `<SortSetting>` 三段 JSON。
- 其中 `<FilterSetting>` 的结构（`Left/FieldName/Compare/Value/Right/Logic`）
  **就是**取数接口 `FilterString` 的原生结构，所以**原样透传**给接口 ——
  不去翻译 `63/92/105/106` 这类比较符编码。翻译表一旦猜错，就是"静默错数"，比报错更糟。
- 列设置里 `FCUSTOMERID_FName` 这种取数列写法会转成接口的 `FCUSTOMERID.FName`；
  个别列在本账套取不到（被删的自定义字段）会跳过并在输出里提示，不会整单失败。
- 唯一的变形：同一字段的多选状态（比较符 106 = 属于）会合并成一次 `IN`。
  金蝶预设方案「待审核应收单」存的是 `属于C` + `属于Z` 两行，接口按 AND 解释会得到 0 行，合并后与界面一致。

### 四条边界，先说清楚

1. **只对表单类（单据）对象有效**。报表类（`GL_RPT_AccountBalance`、`AR_SumReport` 等）的方案是**版式方案**，
   不能当列表过滤方案用，请走 `--only` 从内置清单取；代码会提前拦下并提示，不会瞎试。
2. **行数是"分录行"还是"单据行"取决于方案里的列**。方案里勾了物料/数量这类单据体字段，
   导出就是每个分录一行（与列表页一致）；只勾单据头字段才是单据粒度。同一方案两种列组合，行数会不一样。
3. **0 行不一定出错**。方案里若带「本月/本期」这类相对日期条件，当期没有单据就是 0 行；
   预设方案的"多状态"口径也可能与你预期不同 —— 到列表页选同一方案核对一下即可。
4. **看不到某个方案，先看账套对不对**。取数接口读的是**整个账套**的方案表 —— 实测能看到其他同事建的、
   甚至标了「未共享」的方案（`FIsShare=False` 照样读得到）。所以真正常见的原因是：
   ① 连的**不是同一个账套**（或多账套环境连错了）；② 方案名写错（中文全/半角、多余空格）；
   ③ 少数版本对 `BOS_FilterScheme` 的读取权限收得更紧 —— 这时才需要让创建人在「管理查询」里共享给取数账号。

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
| **引用字段能不能当过滤条件，要看具体字段** | 实测 `AR_receivable` 的 `FCustomerID.FName` / `FCreatorId.FName` **可以**（返回行数正确）；`SAL_OUTSTOCK.FCustId.FName` 会报「数据库执行异常」。报错时改用内码，或改用按已保存方案取数（方案里的条件原样透传，不走字符串解析） |
| **本技能只读** | 不做单据提交、审核、下推等写操作；写操作见 `kingdee-expense-flow` |
| **报表类对象不走通用取数** | `--form-id` 查的是业务对象；报表（`GL_RPT_AccountBalance`、`AR_SumReport` 等）走另一个接口，请用 `--only` 从内置清单取 |
| **报表的「方案」不能当列表方案用** | 报表在 `BOS_FilterScheme` 里也有方案记录，但它是**版式方案**（列 + 分组），不含列表过滤条件。`--scheme` 对报表对象无效，会提前拦下提示 |
| **按方案导出的行数取决于方案里勾的列** | 勾了单据体字段（物料、数量）→ 每个分录一行；只勾单据头 → 单据粒度。与列表页同一方案看到的一致 |
| **注册表里有 ≠ 能取数** | `--list-objects` 列的是业务对象注册表，其中混有单据转换规则、打印模板、迁移方案等**非表单类对象**，`--form-id` 必然失败。取数前先 `--test-form` 体检 |
| **动态建模对象的 FormId 不带模块前缀** | 形如纯数字码或 GUID，按 `GL%` 前缀筛会漏。用 `--object-sub <子系统编号>` 按子系统归属筛才完整 |
| **导全组织需要「组织机构」查看权限** | 缺该权限时 `--org all` 与 `--list-orgs` 都不可用。此时改用 `--org <组织编码>` 直接指定即可绕开 |
| **组织对象 FormId 因环境而异** | 默认按 `ORG_Organizations` → `BD_Organization` 兜底；两者都不通时按报错分流（权限问题 / 对象不存在），不会统一报「字段错」 |

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
| 「您没有组织机构的查看权限」 | 账号缺组织机构权限 | 让管理员在 系统管理 → 用户管理 → 权限 授予；或改用 `--org <组织编码>` 绕开组织列表 |
| 「无法将类型为 ConvertMetaData 的对象强制转换」 | 该 FormId 不是表单类对象（转换规则/打印模板/迁移方案） | 用 `--list-objects --object-kw <关键字>` 另选真正的单据对象 |
| 元数据能读、`--form-id` 报错 | 对象不允许 WebAPI 查询，或子系统许可未买全 | 跑 `--test-form <FormId>` 分辨是元数据关还是取数关 |
| 装依赖时报找不到 pandas | 环境缺依赖或 Python 版本过低 | `--doctor` 第 0 步会先报依赖；按提示 `pip install -r requirements.txt`，国内加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `--list-schemes` 里没有我保存的方案 | 多数是**账套连错**或方案名不一致；共享状态一般不影响（实测未共享的方案也能读到） | 先 `--show-config` / 配置里的 `base_url`+`acct_name` 确认账套；再核对方案名（中文全半角、空格）。少数版本权限收紧时，让创建人在列表页「管理查询」里共享 |
| 按方案导出 **0 行** | 方案里带「本月/本期」等相对日期条件，当期确实没单据；或预设方案的多状态口径与预期不同 | 到列表页选同一方案核对行数；`--list-schemes` 可先看方案里的条件 |
| 按方案导出提示"报表类对象" | 报表的方案是**版式方案**，不是列表过滤方案 | 报表用 `--only <报表名>` 从内置清单取，别用 `--scheme` |
| 提示 `skillhub：未找到命令`，或看到文档要求 `export PATH="$HOME/.local/bin:$PATH"` | 那是 **SkillHub 命令行工具**的安装目录不在 PATH 里，与取数无关，也不是本 Skill 的环境变量 | 本 Skill **不需要任何环境变量**：凭据在向导里填、DPAPI 加密存 `~/.workbuddy/kingdee/`。只有手工装过 SkillHub CLI 才需要把 `~/.local/bin` 加进 PATH（写进 `~/.bashrc` 可永久生效） |

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
| 「凭证/资产卡片/即时库存怎么导」 | `--list-objects --object-kw 凭证` 拿 FormId → `--test-form` 体检 → `--form-id` 取数 |
| 「这个对象能不能导」 | `--test-form <FormId>`，分「元数据」「取数」两关报结果 |
| 「以前导过什么数据」 | 读 `~/.workbuddy/kingdee/audit.log`（每行一条 JSON，只含时间/对象/行数） |

## 结果检查

导出完成后：

1. 向用户说明生成文件的完整路径。
2. 检查所需工作表是否存在、是否有数据。
3. 若结果为空，依次核对日期、组织权限、单据状态和 `--only` 名称。
4. 不读取或展示超出用户请求范围的敏感业务数据。
