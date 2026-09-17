# -*- coding: utf-8 -*-
"""
⚠️ 这是一个**模板文件**，会被分发给其他人 —— 请不要把真实账号密码填在这里。
   要填真实凭据，请复制本文件为 config.py（同目录），或使用下面推荐的用户级配置。

推荐（技能升级/重装不会覆盖，也不会被误打包分发）：
    写 ~/.workbuddy/kingdee/config.json（Windows：C:\\Users\\<你>\\.workbuddy\\kingdee\\config.json）

    {
      "base_url": "https://你的域名/k3cloud/",
      "acct_name": "账套名称",
      "username": "取数账号",
      "password": "密码"
    }

    · acct_name 填账套名称即可，acctid 会自动解析；也可以直接填 acctid。
    · 多账套用 {"default": "A", "profiles": {"A": {...}, "B": {...}}}，
      并用环境变量 KINGDEE_PROFILE 切换。

本文件（config.py）支持的环境变量（优先级高于本文件内容）：
    KINGDEE_BASE_URL / KINGDEE_ACCTID / KINGDEE_ACCT_NAME
    / KINGDEE_USERNAME / KINGDEE_PASSWORD

配置完成后先自检：
    python data_exporter.py --doctor
不确定怎么配：
    python data_exporter.py --help-config
"""

import os


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip()


# ⚠️ 本文件含明文凭据，禁止提交到任何仓库或打进分享包。
KINGDEE_CONFIG = {
    "base_url": _env("KINGDEE_BASE_URL", "https://your-k3cloud-host/k3cloud/"),
    "acctid": _env("KINGDEE_ACCTID", ""),
    # 也可以只填账套名称，脚本会通过免认证接口自动解析成 acctid
    "acct_name": _env("KINGDEE_ACCT_NAME", ""),
    "username": _env("KINGDEE_USERNAME", ""),
    "password": _env("KINGDEE_PASSWORD", ""),
    # 可选：科目余额表账簿编码。单组织可用 account_book_number；多组织可用 account_book_numbers。
    # "account_book_number": "",
    # "account_book_numbers": {"ORG001": "BOOK001"},
    # 可选：银行存款流水账按银行账号过滤。不填则按 --org 组织范围导出所有银行账号。
    # "bank_account_numbers": ["BANK_ACCOUNT_NO_1", "BANK_ACCOUNT_NO_2"],
    # 可选：财务报表参数。默认导出个别月报；如需季报/合并报表，可在本地覆盖。
    # "financial_report": {
    #     "ReportType": 1,
    #     "ReportNumber": "BBMB0001",
    #     "AcctSystemNumber": "KJHSTX01_SYS",
    #     "AcctPolicyNumber": "KJZC01_SYS",
    #     "CurrencyNumber": "PRE001",
    #     "CurrUnitNumber": "JEDW01_SYS",
    #     "CycleType": 4,
    # },
}
