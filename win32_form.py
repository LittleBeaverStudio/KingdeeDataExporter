# -*- coding: utf-8 -*-
"""原生 Windows 表单（**纯 ctypes，零依赖**）。

为什么不用 tkinter
──────────────────
WorkBuddy 自带的托管 Python 3.13 **不带 tkinter**，而财务人员的办公电脑上多半也没有
自己装过带 tkinter 的 Python。凭据录入这种事不能押在"用户机器上恰好有某个 Python"上，
所以这里直接调 user32/gdi32 画一个普通 Windows 窗口：

  · 只用 `ctypes` + 系统 DLL，**本技能依旧零第三方依赖**；
  · 任何 Windows 都能跑，不需要装运行时、不改 PATH；
  · 有真正的输入框、密码框、复选框、按钮 —— 和用户平时见的窗口一致；
  · 密码框用 `ES_PASSWORD`，勾「显示密码」才明文显示。

边界（刻意如此）
────────────────
· 只做**金蝶连接**那几个字段。发票云的多组织动态卡片仍交给文字向导 ——
  在原生控件里做动态增删 + 滚动会把这段代码从 300 行推到 800 行，不值当。
· 不做自定义绘制/皮肤，保持系统原生外观（用户认得、信得过）。
· 本模块**不碰凭据存储**：只把用户填的内容以 dict 返回，保存由调用方做。

调用约定
────────
    run_form(change_key=False, prefill={...}) -> dict | None
      返回 {"base_url","acct_name","username","password","want_piazzone"}
      用户取消 / 直接关窗 → None（调用方据此按"没改成"处理）

⚠️ 实现注意（踩过的坑）
──────────────────────
· WNDPROC 的回调对象**必须持有强引用**，否则被 GC 后窗口过程变成野指针 → 窗口一创建就崩。
· 64 位下 WPARAM/LPARAM 是 8 字节：`c_size_t` / `c_ssize_t`，写成 c_int 会在 64 位下截断。
· 中文输入法里回车是"确认候选词"：若在消息循环里无条件拦 VK_RETURN，中文输入第一个字就被提交了。
  所以拦截前先用 imm32 查一次是否正在组词（`_ime_composing`）。
· 高 DPI 不处理会整体糊成一片，且 150% 缩放下窗口小得没法看 —— 先声明 per-monitor v2，再按 DPI 缩放。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

CLASS_NAME = "KingdeeCredFormW"
TITLE_NORMAL = "金蝶云星空 · 凭据配置"
TITLE_CHANGE = "金蝶云星空 · 修改密钥"

# ── 控件 ID ──
ID_BASE_URL = 1001
ID_ACCT_NAME = 1002
ID_USERNAME = 1003
ID_PASSWORD = 1004
ID_PASSWORD2 = 1005
ID_SHOW_PWD = 1006
ID_WANT_PZ = 1007
ID_SAVE = 1008
ID_CANCEL = 1009

# ── 样式常量 ──
WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
ES_AUTOHSCROLL = 0x0080
ES_PASSWORD = 0x0020
BS_DEFPUSHBUTTON = 0x0001
BS_AUTOCHECKBOX = 0x0003
SS_RIGHT = 0x00000002
SS_LEFT = 0x00000000
SW_SHOW = 5
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
WM_CREATE = 0x0001
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_SETFONT = 0x0030
WM_KEYDOWN = 0x0100
WM_COMMAND = 0x0111
WM_GETDLGCODE = 0x0087
WM_DRAWITEM = 0x002B
WM_CTLCOLOREDIT = 0x0133
WM_CTLCOLORBTN = 0x0135
WM_CTLCOLORSTATIC = 0x0138
BS_OWNERDRAW = 0x0000000B
ODS_SELECTED = 0x0001
ODS_DISABLED = 0x0004
ODS_FOCUS = 0x0010
DT_LEFT = 0x0000
DT_CENTER = 0x0001
DT_VCENTER = 0x0004
DT_SINGLELINE = 0x0020
BK_TRANSPARENT = 1
PS_SOLID = 0
ID_SUBTITLE = 2001
ID_HINT = 2002
EM_SETPASSWORDCHAR = 0x00CC
BM_SETCHECK = 0x00F1
BM_GETCHECK = 0x00F0
BST_CHECKED = 1
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
MB_OK = 0x00000000
MB_ICONWARNING = 0x00000030
MB_ICONINFORMATION = 0x00000040
MB_TOPMOST = 0x00040000
DEFAULT_CHARSET = 1
CLEARTYPE_QUALITY = 5
FW_NORMAL = 400
FW_BOLD = 700
GCS_COMPSTR = 0x0008
SM_CXSCREEN = 0
SM_CYSCREEN = 1
LOGPIXELSX = 88

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_void_p, ctypes.c_uint,
                             ctypes.c_size_t, ctypes.c_ssize_t)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", ctypes.c_void_p),
                ("hIcon", ctypes.c_void_p),
                ("hCursor", ctypes.c_void_p),
                ("hbrBackground", ctypes.c_void_p),
                ("lpszMenuName", ctypes.c_wchar_p),
                ("lpszClassName", ctypes.c_wchar_p)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p),
                ("message", ctypes.c_uint),
                ("wParam", ctypes.c_size_t),
                ("lParam", ctypes.c_ssize_t),
                ("time", ctypes.c_uint),
                ("pt", POINT)]


class DRAWITEMSTRUCT(ctypes.Structure):
    _fields_ = [("CtlType", ctypes.c_uint),
                ("CtlID", ctypes.c_uint),
                ("itemID", ctypes.c_uint),
                ("itemAction", ctypes.c_uint),
                ("itemState", ctypes.c_uint),
                ("hwndItem", ctypes.c_void_p),
                ("hDC", ctypes.c_void_p),
                ("rcItem", RECT),
                ("itemData", ctypes.c_size_t)]


def available() -> bool:
    """原生表单能不能用（只在 Windows 上可用）。"""
    return sys.platform == "win32"


# ─────────────────────────── DLL 绑定 ───────────────────────────

def _bind():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = ctypes.c_ushort
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    user32.CreateWindowExW.restype = ctypes.c_void_p
    user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                      ctypes.c_size_t, ctypes.c_ssize_t]
    user32.DefWindowProcW.restype = LRESULT
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                    ctypes.c_size_t, ctypes.c_ssize_t]
    user32.SendMessageW.restype = LRESULT
    user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.c_void_p,
                                   ctypes.c_uint, ctypes.c_uint]
    user32.GetMessageW.restype = ctypes.c_int
    user32.IsDialogMessageW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MSG)]
    user32.IsDialogMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.SetWindowTextW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    user32.DestroyWindow.argtypes = [ctypes.c_void_p]
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.UpdateWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetFocus.argtypes = [ctypes.c_void_p]
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.AdjustWindowRectEx.argtypes = [ctypes.POINTER(RECT), wintypes.DWORD,
                                          wintypes.BOOL, wintypes.DWORD]
    user32.MessageBoxW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   ctypes.c_uint]
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.LoadCursorW.restype = ctypes.c_void_p
    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.InvalidateRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL]
    user32.GetDlgCtrlID.argtypes = [ctypes.c_void_p]
    user32.GetDlgCtrlID.restype = ctypes.c_int
    user32.FillRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT), ctypes.c_void_p]
    user32.DrawTextW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_int,
                                 ctypes.POINTER(RECT), ctypes.c_uint]
    user32.GetSysColorBrush.argtypes = [ctypes.c_int]
    user32.GetSysColorBrush.restype = ctypes.c_void_p

    gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
    gdi32.CreateSolidBrush.restype = ctypes.c_void_p
    gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi32.CreatePen.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.SetTextColor.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    gdi32.SetBkColor.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    gdi32.SetBkMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
    gdi32.MoveToEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    gdi32.LineTo.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdi32.Rectangle.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int]
    gdi32.GetStockObject.argtypes = [ctypes.c_int]
    gdi32.GetStockObject.restype = ctypes.c_void_p

    gdi32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD, wintypes.DWORD,
                                                       wintypes.DWORD, wintypes.DWORD,
                                                       wintypes.DWORD, wintypes.DWORD,
                                                       wintypes.DWORD, wintypes.DWORD,
                                                       wintypes.LPCWSTR]
    gdi32.CreateFontW.restype = ctypes.c_void_p
    gdi32.GetDeviceCaps.argtypes = [ctypes.c_void_p, ctypes.c_int]
    gdi32.GetDeviceCaps.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]

    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p

    try:
        imm32 = ctypes.WinDLL("imm32")
        imm32.ImmGetContext.argtypes = [ctypes.c_void_p]
        imm32.ImmGetContext.restype = ctypes.c_void_p
        imm32.ImmGetCompositionStringW.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                                                   ctypes.c_void_p, wintypes.DWORD]
        imm32.ImmGetCompositionStringW.restype = ctypes.c_long
        imm32.ImmReleaseContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    except OSError:
        imm32 = None

    return user32, gdi32, kernel32, imm32


_USER32, _GDI32, _KERNEL32, _IMM32 = (_bind() if sys.platform == "win32"
                                      else (None, None, None, None))


def _dpi_scale() -> tuple[float, int]:
    """声明 DPI 感知并返回 (缩放系数, dpi)。不处理的话 150% 缩放下窗口小到没法看。"""
    dpi = 96
    try:                                   # per-monitor v2（Win10 1703+）
        fn = _USER32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = wintypes.BOOL
        fn(ctypes.c_void_p(-4))
    except Exception:  # noqa: BLE001
        try:
            _USER32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass
    try:
        _USER32.GetDpiForSystem.argtypes = []
        _USER32.GetDpiForSystem.restype = ctypes.c_uint
        dpi = int(_USER32.GetDpiForSystem()) or 96
    except Exception:  # noqa: BLE001
        try:
            hdc = _USER32.GetDC(None)
            dpi = _GDI32.GetDeviceCaps(ctypes.c_void_p(hdc), LOGPIXELSX) or 96
            _USER32.ReleaseDC(None, ctypes.c_void_p(hdc))
        except Exception:  # noqa: BLE001
            dpi = 96
    return max(dpi / 96.0, 1.0), dpi


def _ime_composing(hwnd) -> bool:
    """输入法是否正在组词 —— 组词中的回车要留给输入法。"""
    if not _IMM32 or not hwnd:
        return False
    try:
        ctx = _IMM32.ImmGetContext(ctypes.c_void_p(hwnd))
        if not ctx:
            return False
        try:
            return _IMM32.ImmGetCompositionStringW(
                ctypes.c_void_p(ctx), GCS_COMPSTR, None, 0) > 0
        finally:
            _IMM32.ImmReleaseContext(ctypes.c_void_p(hwnd), ctypes.c_void_p(ctx))
    except Exception:  # noqa: BLE001
        return False


def _text(hwnd) -> str:
    n = _USER32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    _USER32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, n + 1)
    return buf.value


# ─────────────────────────── 配色（跟系统深浅色） ───────────────────────────

_DARK = {"bg": (32, 33, 36), "text": (233, 233, 233), "muted": (150, 156, 165),
         "edit_bg": (45, 47, 51), "edit_text": (240, 240, 240),
         "line": (95, 100, 108), "btn": (56, 58, 62), "btn_hot": (72, 75, 80),
         "btn_down": (40, 42, 45), "btn_text": (236, 236, 236),
         "accent": (78, 161, 255)}
# 浅色不用自定义：直接借系统 COLOR_BTNFACE / COLOR_WINDOW，才是原生观感
_LIGHT = {"bg": None, "text": (0, 0, 0), "muted": (110, 110, 110),
          "edit_bg": (255, 255, 255), "edit_text": (0, 0, 0),
          "line": (172, 172, 172), "btn": None, "btn_hot": None,
          "btn_down": None, "btn_text": (0, 0, 0), "accent": (0, 102, 204)}


def _is_dark_mode() -> bool:
    """跟随系统「应用模式」（Win10 1809+ 的个性化设置）。取不到就当浅色。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes"
                            r"\Personalize") as key:
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(val) == 0
    except Exception:  # noqa: BLE001
        return False


def _ref(rgb) -> int:
    """(r,g,b) → COLORREF（0x00BBGGRR）。"""
    r, g, b = rgb
    return r | (g << 8) | (b << 16)


def _apply_dark_caption(hwnd) -> None:
    """把标题栏也刷成深色（Win10 1809+ / Win11）。不支持的环境静默跳过。"""
    try:
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                              ctypes.c_void_p, ctypes.c_uint]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        flag = ctypes.c_int(1)
        for attr in (20, 19):            # DWMWA_USE_IMMERSIVE_DARK_MODE，旧版本编号是 19
            if dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attr,
                                         ctypes.byref(flag), ctypes.sizeof(flag)) == 0:
                break
        SWP_FRAMECHANGED = 0x0020        # 设完必须刷新非客户区，否则标题栏还是浅色
        _USER32.SetWindowPos(ctypes.c_void_p(hwnd), None, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    except Exception:  # noqa: BLE001
        pass


# ─────────────────────────── 表单 ───────────────────────────

def message(text: str, title: str = "提示", warning: bool = False) -> None:
    """原生提示框（原生表单没有 tkinter 的 messagebox，用它给用户反馈结果）。"""
    if not available():
        print(text)
        return
    flags = MB_OK | (MB_ICONWARNING if warning else MB_ICONINFORMATION) | MB_TOPMOST
    _USER32.MessageBoxW(None, text, title, flags)


def run_form(change_key: bool = False, prefill: dict | None = None,
             has_piazzone: bool = False, show_piazzone: bool = True) -> dict | None:
    """弹出原生表单。返回填写结果；取消返回 None。

    `show_piazzone=False` 用于导出技能那份向导（它不管发票云）。
    """
    if not available():
        raise OSError("原生表单仅支持 Windows")

    prefill = prefill or {}
    scale, dpi = _dpi_scale()

    def s(v: float) -> int:
        return int(round(v * scale))

    h_inst = _KERNEL32.GetModuleHandleW(None)
    font = _GDI32.CreateFontW(-s(13), 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET,
                              0, 0, CLEARTYPE_QUALITY, 0, "Microsoft YaHei UI")
    font_bold = _GDI32.CreateFontW(-s(14), 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET,
                                   0, 0, CLEARTYPE_QUALITY, 0, "Microsoft YaHei UI")

    dark = _is_dark_mode()
    pal = _DARK if dark else _LIGHT

    # 浅色借系统色（COLOR_BTNFACE=15 / COLOR_WINDOW=5），深色自建纯色刷
    brush_bg = (_GDI32.CreateSolidBrush(_ref(pal["bg"])) if dark
                else _USER32.GetSysColorBrush(15))
    brush_edit = (_GDI32.CreateSolidBrush(_ref(pal["edit_bg"])) if dark
                  else _USER32.GetSysColorBrush(5))

    state: dict = {"hwnd": None, "edits": {}, "checks": {}, "done": None,
                   "dialogproc": None, "check": {"show": False, "piazzone": False}}
    widgets: list = []

    # ── 布局（单位：未缩放的逻辑像素）──
    MARGIN, LABEL_W, GAP, EDIT_W, ROW_H, ROW_GAP = 20, 104, 10, 300, 28, 12
    rows = [("base_url", "服务器地址", str(prefill.get("base_url") or "")),
            ("acct_name", "公司名 / 账套", str(prefill.get("acct_name") or "")),
            ("username", "用户名", str(prefill.get("username") or "")),
            ("password", "新密码" if change_key else "密码", "")]
    if change_key:
        rows.append(("password2", "再输一次", ""))

    client_w = MARGIN * 2 + LABEL_W + GAP + EDIT_W
    y = MARGIN
    y += s(24) + s(18) + s(14)                      # 标题 + 副标题 + 间距
    top_rows = y
    y += len(rows) * s(ROW_H + ROW_GAP)
    y_show = y
    y += s(24) + s(12)
    y_pz = y
    if show_piazzone:
        y += s(24) + s(12)
    y_hint = y
    y += s(20) + s(10)
    y_btn = y
    y += s(30)
    client_h = y + MARGIN

    style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX

    def _draw_item(dis) -> None:
        """自绘按钮 / 复选框（深色模式下系统不给主题化，只能自己画）。"""
        hdc = ctypes.c_void_p(dis.hDC)
        rc = dis.rcItem
        old_font = _GDI32.SelectObject(hdc, font)
        try:
            if int(dis.CtlID) in (ID_SHOW_PWD, ID_WANT_PZ):
                key = "show" if int(dis.CtlID) == ID_SHOW_PWD else "piazzone"
                on = bool(state["check"][key])
                box = s(15)
                bx = rc.left + 1
                by = rc.top + (rc.bottom - rc.top - box) // 2

                fill = RECT(rc.left, rc.top, rc.right, rc.bottom)
                _USER32.FillRect(hdc, ctypes.byref(fill), brush_bg)

                pen = _GDI32.CreatePen(PS_SOLID, max(s(1), 1), _ref(pal["line"]))
                old_pen = _GDI32.SelectObject(hdc, pen)
                box_br = _GDI32.CreateSolidBrush(_ref(pal["edit_bg"]))
                old_br = _GDI32.SelectObject(hdc, box_br)
                _GDI32.Rectangle(hdc, bx, by, bx + box, by + box)
                _GDI32.SelectObject(hdc, old_br)
                _GDI32.DeleteObject(box_br)

                if on:
                    pen2 = _GDI32.CreatePen(PS_SOLID, max(s(2), 2), _ref(pal["accent"]))
                    _GDI32.SelectObject(hdc, pen2)
                    _GDI32.MoveToEx(hdc, bx + s(3), by + box // 2, None)
                    _GDI32.LineTo(hdc, bx + s(6), by + box - s(4))
                    _GDI32.LineTo(hdc, bx + box - s(3), by + s(4))
                    _GDI32.SelectObject(hdc, old_pen)
                    _GDI32.DeleteObject(pen2)
                else:
                    _GDI32.SelectObject(hdc, old_pen)
                _GDI32.DeleteObject(pen)

                trc = RECT(bx + box + s(8), rc.top, rc.right, rc.bottom)
                _GDI32.SetBkMode(hdc, BK_TRANSPARENT)
                _GDI32.SetTextColor(hdc, _ref(pal["text"]))
                _USER32.DrawTextW(hdc, _text(dis.hwndItem), -1, ctypes.byref(trc),
                                  DT_LEFT | DT_VCENTER | DT_SINGLELINE)
                return

            pressed = bool(int(dis.itemState) & ODS_SELECTED)
            cid = int(dis.CtlID)
            primary = cid == ID_SAVE
            if primary:
                bg = (28, 100, 190) if pressed else pal["accent"]
                fg = (255, 255, 255)
            else:
                bg = pal["btn_down"] if pressed else (pal["btn"] or (240, 240, 240))
                fg = pal["btn_text"]

            fill = RECT(rc.left, rc.top, rc.right, rc.bottom)
            br = _GDI32.CreateSolidBrush(_ref(bg))
            _USER32.FillRect(hdc, ctypes.byref(fill), br)
            _GDI32.DeleteObject(br)

            pen = _GDI32.CreatePen(PS_SOLID, max(s(1), 1),
                                   _ref(pal["accent"] if primary else pal["line"]))
            old_pen = _GDI32.SelectObject(hdc, pen)
            null_br = _GDI32.GetStockObject(5)          # NULL_BRUSH → 只画边框
            old_br = _GDI32.SelectObject(hdc, null_br)
            _GDI32.Rectangle(hdc, rc.left, rc.top, rc.right, rc.bottom)
            _GDI32.SelectObject(hdc, old_br)
            _GDI32.SelectObject(hdc, old_pen)
            _GDI32.DeleteObject(pen)

            trc = RECT(rc.left, rc.top, rc.right, rc.bottom)
            _GDI32.SetBkMode(hdc, BK_TRANSPARENT)
            _GDI32.SetTextColor(hdc, _ref(fg))
            _USER32.DrawTextW(hdc, _text(dis.hwndItem), -1, ctypes.byref(trc),
                              DT_CENTER | DT_VCENTER | DT_SINGLELINE)
        finally:
            _GDI32.SelectObject(hdc, old_font)

    def _wndproc(hwnd, msg, wparam, lparam):
        try:
            if msg == WM_COMMAND:
                cid = int(wparam) & 0xFFFF
                code = (int(wparam) >> 16) & 0xFFFF
                if code == 0:                      # BN_CLICKED
                    if cid == ID_SAVE:
                        _do_save(hwnd)
                    elif cid == ID_CANCEL:
                        state["done"] = None
                        _USER32.DestroyWindow(ctypes.c_void_p(hwnd))
                    elif cid == ID_SHOW_PWD:
                        state["check"]["show"] = not state["check"]["show"]
                        _apply_show()
                        _USER32.InvalidateRect(ctypes.c_void_p(state["checks"]["show"]),
                                               None, True)
                    elif cid == ID_WANT_PZ:
                        state["check"]["piazzone"] = not state["check"]["piazzone"]
                        _USER32.InvalidateRect(ctypes.c_void_p(state["checks"]["piazzone"]),
                                               None, True)
                return 0
            if msg == WM_CTLCOLORSTATIC:
                hdc = ctypes.c_void_p(wparam)
                _GDI32.SetBkMode(hdc, BK_TRANSPARENT)
                cid = _USER32.GetDlgCtrlID(ctypes.c_void_p(lparam))
                _GDI32.SetTextColor(hdc, _ref(pal["muted"] if cid in (ID_SUBTITLE, ID_HINT)
                                              else pal["text"]))
                return int(brush_bg or 0)
            if msg == WM_CTLCOLOREDIT:
                hdc = ctypes.c_void_p(wparam)
                _GDI32.SetBkColor(hdc, _ref(pal["edit_bg"]))
                _GDI32.SetTextColor(hdc, _ref(pal["edit_text"]))
                return int(brush_edit or 0)
            if msg == WM_DRAWITEM:
                dis = ctypes.cast(ctypes.c_void_p(lparam),
                                  ctypes.POINTER(DRAWITEMSTRUCT)).contents
                _draw_item(dis)
                return 1
            if msg == WM_CLOSE:
                state["done"] = None
                _USER32.DestroyWindow(ctypes.c_void_p(hwnd))
                return 0
            if msg == WM_DESTROY:
                _USER32.PostQuitMessage(0)
                return 0
        except Exception:  # noqa: BLE001  窗口过程里绝不能抛
            pass
        return _USER32.DefWindowProcW(ctypes.c_void_p(hwnd), msg, wparam, lparam)

    wndproc = WNDPROC(_wndproc)
    state["dialogproc"] = wndproc                   # ★ 必须持引用，否则回调被 GC

    wc = WNDCLASSW()
    wc.style = 0
    wc.lpfnWndProc = wndproc
    wc.cbClsExtra = 0
    wc.cbWndExtra = 0
    wc.hInstance = h_inst
    wc.hIcon = None
    wc.hCursor = _USER32.LoadCursorW(None, ctypes.c_void_p(32512))   # IDC_ARROW
    wc.hbrBackground = (brush_bg if brush_bg else ctypes.c_void_p(16))
    wc.lpszMenuName = None
    wc.lpszClassName = CLASS_NAME
    _USER32.RegisterClassW(ctypes.byref(wc))        # 已注册过会失败，忽略即可

    rect = RECT(0, 0, s(client_w), s(client_h))
    _USER32.AdjustWindowRectEx(ctypes.byref(rect), style, False, 0)
    win_w, win_h = rect.right - rect.left, rect.bottom - rect.top
    x = max((_USER32.GetSystemMetrics(SM_CXSCREEN) - win_w) // 2, 0)
    ypos = max(min((_USER32.GetSystemMetrics(SM_CYSCREEN) - win_h) // 3, 400), 0)

    hwnd = _USER32.CreateWindowExW(0, CLASS_NAME,
                                   TITLE_CHANGE if change_key else TITLE_NORMAL,
                                   style, x, ypos, win_w, win_h,
                                   None, None, h_inst, None)
    if not hwnd:
        raise OSError(ctypes.get_last_error(), "CreateWindowExW 失败")
    state["hwnd"] = hwnd

    if dark:      # 让标题栏也变深，否则白标题栏配深色内容很割裂
        _apply_dark_caption(hwnd)

    def add(cls, text, st, cx, cy, cw, ch, cid, fnt=None):
        h = _USER32.CreateWindowExW(0, cls, text, st, cx, cy, cw, ch,
                                    ctypes.c_void_p(hwnd), ctypes.c_void_p(cid),
                                    ctypes.c_void_p(h_inst), None)
        if h and fnt is not None:
            _USER32.SendMessageW(ctypes.c_void_p(h), WM_SETFONT, fnt, 1)
        widgets.append(h)
        return h

    # 标题 + 副标题
    add("STATIC", "金蝶云星空 · 敏感信息录入", WS_CHILD | WS_VISIBLE | SS_LEFT,
        s(MARGIN), s(MARGIN), s(client_w - MARGIN * 2), s(24), 0, font_bold)
    add("STATIC", "凭据在本机加密保存（DPAPI），不进对话记录、不写明文文件",
        WS_CHILD | WS_VISIBLE | SS_LEFT,
        s(MARGIN), s(MARGIN + 24), s(client_w - MARGIN * 2), s(18), ID_SUBTITLE, font)

    # 字段行
    for i, (key, label, val) in enumerate(rows):
        ry = top_rows + i * s(ROW_H + ROW_GAP)
        add("STATIC", label, WS_CHILD | WS_VISIBLE | SS_RIGHT,
            s(MARGIN), ry + s(6), s(LABEL_W), s(20), 0, font)
        st = WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL
        if key in ("password", "password2"):
            st |= ES_PASSWORD
        edit = add("EDIT", "", st, s(MARGIN + LABEL_W + GAP), ry, s(EDIT_W), s(ROW_H),
                   {"base_url": ID_BASE_URL, "acct_name": ID_ACCT_NAME,
                    "username": ID_USERNAME, "password": ID_PASSWORD,
                    "password2": ID_PASSWORD2}[key], font)
        if val:
            _USER32.SetWindowTextW(ctypes.c_void_p(edit), val)
        state["edits"][key] = edit

    # 显示密码（自绘复选框：状态自己维护，避免和原生 BM_GETCHECK 两套真值）
    chk_show = add("BUTTON", "显示密码", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW,
                   s(MARGIN + LABEL_W + GAP), y_show, s(120), s(24), ID_SHOW_PWD, font)
    state["checks"]["show"] = chk_show

    # 发票云（勾了才在保存后走文字向导维护；不勾 = 原样保留已存的配置）
    if show_piazzone:
        pz_label = ("同时维护发票云（已存的会保留，不改就别勾）" if has_piazzone
                    else "同时维护发票云（可选，仅验票/服务端上传需要）")
        chk_pz = add("BUTTON", pz_label,
                     WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW,
                     s(MARGIN), y_pz, s(client_w - MARGIN * 2), s(24), ID_WANT_PZ, font)
        state["checks"]["piazzone"] = chk_pz

    # 提示（长度要能塞进一行，否则会被窗口右边界切掉）
    add("STATIC", "密码连错 5 次会锁账号 —— 建议勾上「显示密码」先核对。",
        WS_CHILD | WS_VISIBLE | SS_LEFT,
        s(MARGIN), y_hint, s(client_w - MARGIN * 2), s(18), ID_HINT, font)

    # 按钮
    btn_style = WS_CHILD | WS_VISIBLE | WS_TABSTOP | (BS_OWNERDRAW if dark else 0)
    add("BUTTON", "保存", btn_style | (0 if dark else BS_DEFPUSHBUTTON),
        s(client_w - MARGIN - 200), y_btn, s(94), s(30), ID_SAVE, font)
    add("BUTTON", "取消", btn_style,
        s(client_w - MARGIN - 96), y_btn, s(94), s(30), ID_CANCEL, font)

    def _apply_show():
        """勾「显示密码」→ 取消掩码；去掉 → 恢复掩码（ES_PASSWORD 的掩码靠 EM_SETPASSWORDCHAR）。"""
        on = bool(state["check"]["show"])
        char = 0 if on else ord("●")
        for key in ("password", "password2"):
            h = state["edits"].get(key)
            if h:
                _USER32.SendMessageW(ctypes.c_void_p(h), EM_SETPASSWORDCHAR, char, 0)
                _USER32.InvalidateRect(ctypes.c_void_p(h), None, True)

    def _warn(text: str) -> None:
        _USER32.MessageBoxW(ctypes.c_void_p(state["hwnd"]), text, "还差一点",
                            MB_OK | MB_ICONWARNING | MB_TOPMOST)

    def _do_save(hwnd_):
        base_url = _text(state["edits"]["base_url"]).strip()
        acct_name = _text(state["edits"]["acct_name"]).strip()
        username = _text(state["edits"]["username"]).strip()
        password = _text(state["edits"]["password"])
        if not (username and password):
            _warn("用户名和密码是必填项。")
            return
        if change_key:
            again = _text(state["edits"]["password2"])
            if password != again:
                _warn("两次输入的密码不一样，请核对后再保存。")
                return
        if not (base_url or acct_name):
            _warn("请填服务器地址或公司名。")
            return
        state["done"] = {"base_url": base_url, "acct_name": acct_name,
                         "username": username, "password": password,
                         "want_piazzone": bool(state["check"].get("piazzone"))}
        _USER32.DestroyWindow(ctypes.c_void_p(hwnd_))

    _USER32.ShowWindow(ctypes.c_void_p(hwnd), SW_SHOW)
    _USER32.UpdateWindow(ctypes.c_void_p(hwnd))
    _USER32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_TOPMOST),
                         0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    _USER32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_NOTOPMOST),
                         0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    try:
        _USER32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        _USER32.SetFocus(ctypes.c_void_p(state["edits"]["base_url"]))
    except Exception:  # noqa: BLE001
        pass

    # ── 消息循环 ──
    msg = MSG()
    while True:
        ret = _USER32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if ret == 0 or ret == -1:
            break
        if msg.message == WM_KEYDOWN and int(msg.wParam) in (VK_RETURN, VK_ESCAPE):
            if not _ime_composing(msg.hwnd):        # 组词中的回车留给输入法
                if int(msg.wParam) == VK_ESCAPE:
                    state["done"] = None
                    _USER32.DestroyWindow(ctypes.c_void_p(hwnd))
                else:
                    _do_save(hwnd)
                continue
        if not _USER32.IsDialogMessageW(ctypes.c_void_p(hwnd), ctypes.byref(msg)):
            _USER32.TranslateMessage(ctypes.byref(msg))
            _USER32.DispatchMessageW(ctypes.byref(msg))

    for h in widgets:
        if h:
            try:
                _USER32.DestroyWindow(ctypes.c_void_p(h))
            except Exception:  # noqa: BLE001
                pass
    for f in (font, font_bold):
        if f:
            _GDI32.DeleteObject(ctypes.c_void_p(f))
    if dark:                       # 系统色刷不能删，自建的必须删
        for br in (brush_bg, brush_edit):
            if br:
                _GDI32.DeleteObject(ctypes.c_void_p(br))
    return state["done"]


if __name__ == "__main__":  # 手工自测：直接弹窗
    print(run_form(change_key="--change-key" in sys.argv))
