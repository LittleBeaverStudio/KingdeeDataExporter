import os


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip()


# 将本文件复制为 config.py 后填写，或通过环境变量注入配置：
# - KINGDEE_BASE_URL
# - KINGDEE_ACCTID
# - KINGDEE_USERNAME
# - KINGDEE_PASSWORD
# - WECHAT_WEBHOOK（可选）
KINGDEE_CONFIG = {
    "base_url": _env("KINGDEE_BASE_URL", "https://your-k3cloud-host"),
    "acctid": _env("KINGDEE_ACCTID", ""),
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

WECHAT_CONFIG = {
    "webhook": _env("WECHAT_WEBHOOK", ""),
}

