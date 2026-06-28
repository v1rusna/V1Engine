"""
resize_console.py — безопасное изменение размера окна терминала Windows.
Совместимость: Python 3.12, Windows x64.
"""

import sys
import ctypes
import time
from ctypes import wintypes

# ── Проверка платформы на уровне импорта ────────────────────────────────────
if sys.platform != "win32":
    raise OSError("Этот модуль работает только на Windows.")

# ── Настройка сигнатур WinAPI (критично для x64 — без этого HWND усекается) ─
_kernel32 = ctypes.windll.kernel32
_user32   = ctypes.windll.user32

# SetConsoleTitleW(lpConsoleTitle: LPCWSTR) -> BOOL
_kernel32.SetConsoleTitleW.argtypes = [wintypes.LPCWSTR]
_kernel32.SetConsoleTitleW.restype  = wintypes.BOOL

# GetConsoleWindow() -> HWND
_kernel32.GetConsoleWindow.argtypes = []
_kernel32.GetConsoleWindow.restype  = wintypes.HWND

# FindWindowW(lpClassName, lpWindowName) -> HWND
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype  = wintypes.HWND

# ShowWindow(hWnd, nCmdShow) -> BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype  = wintypes.BOOL

# GetWindowRect(hWnd, lpRect) -> BOOL
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype  = wintypes.BOOL

# MoveWindow(hWnd, X, Y, nWidth, nHeight, bRepaint) -> BOOL
_user32.MoveWindow.argtypes = [
    wintypes.HWND,
    ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int,
    wintypes.BOOL,
]
_user32.MoveWindow.restype = wintypes.BOOL

_SW_RESTORE        = 9
_FIND_RETRIES      = 100
_FIND_RETRY_SLEEP  = 0.002   # сек
_TITLE_SETTLE_SLEEP = 0.05   # сек


class ConsoleWindowError(RuntimeError):
    """Ошибка при работе с окном консоли."""


def resize_true_console_window(
    width_px: int,
    height_px: int,
    *,
    restore_title: str = "",
    max_dimension: int = 10_000,
) -> None:
    """
    Изменяет физический размер окна терминала Windows в пикселях.

    Parameters
    ----------
    width_px, height_px : int
        Желаемые размеры окна в пикселях (> 0, ≤ max_dimension).
    restore_title : str
        Заголовок, который будет восстановлен после изменения размера.
        По умолчанию — пустая строка (заголовок не меняется).
    max_dimension : int
        Верхняя граница допустимого значения (защита от аномальных значений).

    Raises
    ------
    TypeError
        Если переданы не целые числа.
    ValueError
        Если размеры вне допустимого диапазона.
    ConsoleWindowError
        Если не удалось найти или изменить окно.
    """
    # ── Валидация входных данных ─────────────────────────────────────────────
    if not isinstance(width_px, int) or not isinstance(height_px, int):
        raise TypeError("width_px и height_px должны быть целыми числами (int).")
    if width_px <= 0 or height_px <= 0:
        raise ValueError("Размеры должны быть положительными.")
    if width_px > max_dimension or height_px > max_dimension:
        raise ValueError(
            f"Размеры превышают допустимый максимум {max_dimension}x{max_dimension}."
        )

    # ── Сохраняем исходный заголовок для восстановления при ошибке ──────────
    original_title_buf = ctypes.create_unicode_buffer(512)
    _kernel32.GetConsoleTitleW(original_title_buf, 512)
    original_title = original_title_buf.value

    # Финальный заголовок: явно переданный или исходный
    final_title = restore_title if restore_title else original_title

    unique_title = f"_resize_{time.time_ns()}"

    try:
        # ── 1. Устанавливаем уникальный заголовок ───────────────────────────
        if not _kernel32.SetConsoleTitleW(unique_title):
            raise ConsoleWindowError("SetConsoleTitleW завершился с ошибкой.")

        time.sleep(_TITLE_SETTLE_SLEEP)

        # ── 2. Ищем окно по уникальному заголовку ───────────────────────────
        hwnd: wintypes.HWND = wintypes.HWND(0)
        for _ in range(_FIND_RETRIES):
            hwnd = _user32.FindWindowW(None, unique_title)
            if hwnd:
                break
            time.sleep(_FIND_RETRY_SLEEP)

        # Fallback: стандартный дескриптор консоли
        if not hwnd:
            hwnd = _kernel32.GetConsoleWindow()

        if not hwnd:
            raise ConsoleWindowError(
                "Не удалось получить дескриптор окна терминала. "
                "Убедитесь, что программа запущена в консольном окне."
            )

        # ── 3. Снимаем «развёрнуто на весь экран», если активно ─────────────
        _user32.ShowWindow(hwnd, _SW_RESTORE)

        # ── 4. Получаем текущую позицию окна ────────────────────────────────
        rect = wintypes.RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise ConsoleWindowError(
                f"GetWindowRect завершился с ошибкой: "
                f"код {ctypes.GetLastError()}."
            )

        # ── 5. Изменяем размер окна ──────────────────────────────────────────
        if not _user32.MoveWindow(
            hwnd,
            rect.left,
            rect.top,
            width_px,
            height_px,
            True,
        ):
            raise ConsoleWindowError(
                f"MoveWindow завершился с ошибкой: "
                f"код {ctypes.GetLastError()}."
            )

    finally:
        # ── 6. Всегда восстанавливаем заголовок (даже при исключении) ────────
        _kernel32.SetConsoleTitleW(final_title)


if __name__ == "__main__":
    resize_true_console_window(800, 600, restore_title="Моя программа")
    print("Размер окна изменён!")
    input("Нажмите Enter для выхода...")