from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────
#  Color
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class Color:
    """Immutable 24-bit foreground color with lazy ANSI generation."""

    r: int | None = None
    g: int | None = None
    b: int | None = None
    _reset: bool = field(default=False, compare=False)

    # Singleton reset instance — создаётся один раз
    _RESET_INSTANCE: "Color | None" = field(
        default=None, init=False, repr=False, compare=False
    )
    # Cache for the computed ANSI sequence (filled in __post_init__)
    _ansi_cache: str | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._reset:
            return

        for name, value in (("r", self.r), ("g", self.g), ("b", self.b)):
            if value is None:
                raise ValueError(f"'{name}' is required unless _reset=True")
            if not isinstance(value, int):
                raise TypeError(f"'{name}' must be int, got {type(value).__name__}")
            if not 0 <= value <= 255:
                raise ValueError(f"'{name}' must be 0–255, got {value}")
        # Cache the ANSI escape sequence to avoid reallocating strings on every render
        ansi_str = f"\033[38;2;{self.r};{self.g};{self.b}m"
        object.__setattr__(self, "_ansi_cache", ansi_str)

    @property
    def ansi(self) -> str:
        if self._reset:
            return "\033[0m"
        if self._ansi_cache is not None:
            return self._ansi_cache
        return f"\033[38;2;{self.r};{self.g};{self.b}m"

    @classmethod
    def from_hex(cls, value: str) -> "Color":
        """Parse '#RRGGBB' or 'RRGGBB'."""
        value = value.lstrip("#")
        if len(value) != 6:
            raise ValueError(f"Expected RRGGBB hex string, got {value!r}")
        try:
            return cls(
                int(value[0:2], 16),
                int(value[2:4], 16),
                int(value[4:6], 16),
            )
        except ValueError:
            raise ValueError(f"Invalid hex color: {value!r}")

    @staticmethod
    def reset() -> "Color":
        """Return the shared reset singleton (no heap allocation on repeated calls)."""
        return _RESET_COLOR


# Singleton — создаётся один раз после определения класса
_RESET_COLOR = Color(_reset=True)


# ─────────────────────────────────────────────
#  Pixel alias
# ─────────────────────────────────────────────

type Pixel = tuple[str, Color]

_RESET_PIXEL: Pixel = (" ", _RESET_COLOR)  # Шаблон фонового пикселя


# ─────────────────────────────────────────────
#  ConsoleRenderer
# ─────────────────────────────────────────────

class ConsoleRenderer:
    """
    Буферизованный ASCII/Unicode рендерер для терминала.

    Использование:
        with ConsoleRenderer(80, 24) as renderer:
            renderer.draw_string(40, 12, "Hello", color=Color(255, 200, 0), length_into_account=True)
            renderer.display()
    """

    MAX_WIDTH = 1200
    MAX_HEIGHT = 300

    __slots__ = ("width", "height", "bg_char", "_bg_pixel", "buffer")

    def __init__(self, width: int = 40, height: int = 30, bg_char: str = " ") -> None:
        if not isinstance(width, int) or width < 1:
            raise ValueError(f"width must be a positive int, got {width!r}")
        if not isinstance(height, int) or height < 1:
            raise ValueError(f"height must be a positive int, got {height!r}")
        if width > self.MAX_WIDTH or height > self.MAX_HEIGHT:
            raise ValueError(f"the length and/or width exceeds the maximum limits: {self.MAX_WIDTH}:{self.MAX_HEIGHT}")
        if len(bg_char) != 1:
            raise ValueError(f"bg_char must be exactly 1 character, got {bg_char!r}")

        self.width = width
        self.height = height
        self.bg_char = bg_char
        self._bg_pixel: Pixel = (bg_char, _RESET_COLOR)
        self.buffer: list[list[Pixel]] = self._make_buffer(width, height)

    # ── Внутренние хелперы ────────────────────

    def _make_buffer(self, width: int, height: int) -> list[list[Pixel]]:
        """Создаёт буфер за O(w*h) без лишних аллокаций."""
        bg = self._bg_pixel
        return [[bg] * width for _ in range(height)]

    # ── Lifecycle ─────────────────────────────

    def setup(self) -> None:
        os.system("cls" if os.name == "nt" else "clear")
        sys.stdout.write("\033[?25l")   # Скрыть курсор
        sys.stdout.flush()

    def cleanup(self) -> None:
        sys.stdout.write("\033[?25h\033[0m\n")  # Показать курсор + сброс цвета
        sys.stdout.flush()

    def __enter__(self) -> "ConsoleRenderer":
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()

    # ── Буфер ─────────────────────────────────

    def clear_buffer(self) -> None:
        """Сброс всех пикселей к фоновому значению."""
        bg = self._bg_pixel
        for row in self.buffer:
            row[:] = [bg] * self.width   # Переиспользуем список вместо пересоздания

    def resize_buffer(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        *,
        auto_clear: bool = False,
    ) -> None:
        """
        Изменяет размеры буфера. Содержимое сбрасывается.

        Args:
            width: Новая ширина (None = оставить текущую).
            height: Новая высота (None = оставить текущую).
            auto_clear: Если True — очищает терминал перед изменением.
        """
        if width is not None and (not isinstance(width, int) or width < 1):
            raise ValueError(f"width must be a positive int, got {width!r}")
        if height is not None and (not isinstance(height, int) or height < 1):
            raise ValueError(f"height must be a positive int, got {height!r}")

        if auto_clear:
            os.system("cls" if os.name == "nt" else "clear")

        if width is not None:
            self.width = width
        if height is not None:
            self.height = height

        if width is not None or height is not None:
            self.buffer = self._make_buffer(self.width, self.height)

    # ── Примитивы рисования ───────────────────

    def get_pixel(self, x: int, y: int) -> Pixel | None:
        """Возвращает пиксель (char, Color) или None если за границей."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.buffer[y][x]
        return None

    def draw_pixel(
        self,
        x: int,
        y: int,
        char: str,
        color: Color | None = None,
    ) -> None:
        """
        Записывает один символ в буфер.

        Raises:
            TypeError: Если color не Color.
            ValueError: Если char — не ровно один символ.
        """
        if len(char) != 1:
            raise ValueError(f"char must be exactly 1 character, got {char!r}")
        if color is not None and not isinstance(color, Color):
            raise TypeError(f"color must be a Color instance, got {type(color).__name__}")
        if 0 <= x < self.width and 0 <= y < self.height:
            self.buffer[y][x] = (char, color if color is not None else _RESET_COLOR)

    def draw_string(
        self,
        x: int,
        y: int,
        text: str,
        color: Color | None = None,
        length_into_account: bool | str = False,
    ) -> None:
        """
        Выводит строку текста в буфер с опциональным выравниванием.

        Args:
            (x, y): Позиция якоря.
            text: Строка для вывода.
            color: Цвет текста.
            length_into_account:
                False / None — якорь слева (без смещения),
                True         — центрирование (якорь по центру),
                ">"          — якорь справа (текст заканчивается на x),
                "<"          — якорь слева с floor-смещением.
        """
        text_len = len(text)
        if text_len == 0:
            return

        match length_into_account:
            case False | None:
                offset = 0
            case True:
                offset = text_len // 2
            case ">":
                offset = text_len
            case "<":
                offset = 0
            case _:
                raise ValueError(
                    f"length_into_account must be False, True, '>' or '<', "
                    f"got {length_into_account!r}"
                )

        resolved_color = color if color is not None else _RESET_COLOR
        buf = self.buffer
        width = self.width
        height = self.height

        # Если Y вне экрана — ничего не делать
        if not (0 <= y < height):
            return

        # Записываем символы напрямую в буфер — избегаем вызова draw_pixel
        # в горячем цикле, чтобы снизить накладные расходы.
        row = buf[y]
        for i, char in enumerate(text):
            px = x + i - offset
            if 0 <= px < width:
                row[px] = (char, resolved_color)

    def draw_box(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        border_char_h: str = "█",
        border_char_v: str = "█",
        color: Color | None = None,
    ) -> None:
        """
        Рисует прямоугольную рамку.

        Args:
            border_char_h: Символ горизонтальных сторон.
            border_char_v: Символ вертикальных сторон.
        """
        if w < 2 or h < 2:
            raise ValueError(f"Box must be at least 2×2, got {w}×{h}")

        dp = self.draw_pixel

        # Горизонтальные стороны
        for i in range(w):
            dp(x + i, y, border_char_h, color)
            dp(x + i, y + h - 1, border_char_h, color)

        # Вертикальные стороны (углы уже нарисованы)
        for i in range(1, h - 1):
            dp(x, y + i, border_char_v, color)
            dp(x + w - 1, y + i, border_char_v, color)

    # ── Рендеринг ─────────────────────────────

    def display(self) -> None:
        """
        Выводит буфер в терминал.

        Использует io.StringIO вместо строковой конкатенации —
        O(n) по памяти и времени вместо O(n²).
        """
        out = io.StringIO()
        write = out.write

        # Перемещаем курсор в начало без очистки экрана
        write("\033[H")

        current_ansi = _RESET_COLOR.ansi
        write(current_ansi)

        for row in self.buffer:
            for char, color in row:
                ansi = color.ansi
                if ansi != current_ansi:
                    write(ansi)
                    current_ansi = ansi
                write(char)
            write("\n")

        write(_RESET_COLOR.ansi)

        sys.stdout.write(out.getvalue())
        sys.stdout.flush()