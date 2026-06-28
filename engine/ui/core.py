"""
ui.py — UI-система для мини-движка.

Иерархия:
    Interface
    ├── UIElement (ABC)
    │   ├── Text       — статический текст
    │   └── Button     — кнопка с action и опциональным выделением
    └── _draw_border / _draw_cursor — внутренние хелперы

Координаты элементов задаются в нормализованном пространстве [0.0 .. 1.0],
что позволяет переиспользовать интерфейс при любом размере терминала.

Пример:
    renderer = ConsoleRenderer(80, 24)
    ui = (
        Interface(renderer)
        .add(Text("MAIN MENU", Position(0.5, 0.15), color=Color(255, 220, 50)))
        .add(Button("Start",  Position(0.5, 0.4), action=lambda: "start"))
        .add(Button("Options",Position(0.5, 0.5), action=lambda: "options"))
        .add(Button("Quit",   Position(0.5, 0.6), action=lambda: UIStatus.EXIT))
    )
    while True:
        renderer.clear_buffer()
        ui.show()
        renderer.display()
        key = inp.get_key()
        result = ui.handle_key(key)
        if result == UIStatus.EXIT:
            break
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Optional
from engine.core.console_renderer import _RESET_COLOR


# ══════════════════════════════════════════════════════════════════════════════
#  Протокол рендерера (структурная типизация вместо ABC-зависимости)
# ══════════════════════════════════════════════════════════════════════════════

class IColor(Protocol):
    r: int
    g: int
    b: int

class IRenderer(ABC):
    """
    Минимальный интерфейс, который UIElement ожидает от рендерера.
    ConsoleRenderer совместим автоматически (duck typing).
    """
    @abstractmethod
    def draw_pixel(self, x: int, y: int, char: str, color: IColor | None = None) -> None: ...
    @abstractmethod
    def draw_string(self, x: int, y: int, text: str,
                    color: IColor | None = None,
                    length_into_account: bool | str = False) -> None: ...
    @abstractmethod
    def draw_box(self, x: int, y: int, w: int, h: int,
                 border_char_h: str = "█", border_char_v: str = "█",
                 color: IColor | None = None) -> None: ...
    @property
    @abstractmethod
    def width(self) -> int: ...
    @property
    @abstractmethod
    def height(self) -> int: ...

# ══════════════════════════════════════════════════════════════════════════════
#  Перечисления
# ══════════════════════════════════════════════════════════════════════════════

class UIStatus(enum.Enum):
    """Сигналы управления потоком, возвращаемые из handle_key."""
    BACK = enum.auto()   # Вернуться на предыдущий экран
    EXIT = enum.auto()   # Закрыть приложение
    NONE = enum.auto()   # Ничего не произошло


class Anchor(enum.Enum):
    """Горизонтальное выравнивание текста относительно позиции якоря."""
    LEFT   = enum.auto()
    CENTER = enum.auto()
    RIGHT  = enum.auto()


# ══════════════════════════════════════════════════════════════════════════════
#  Позиция
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(slots=True, frozen=True)
class Position:
    """Нормализованная позиция [0.0 .. 1.0] × [0.0 .. 1.0]."""
    x: float
    y: float

    def __post_init__(self) -> None:
        for name, v in (("x", self.x), ("y", self.y)):
            if not isinstance(v, (int, float)):
                raise TypeError(f"Position.{name} must be numeric, got {type(v).__name__}")
            # Не клипаем жёстко — элементы могут намеренно выходить за экран
            # (например, анимация), но предупреждаем о явно неверных значениях.

    def to_screen(self, renderer: IRenderer) -> tuple[int, int]:
        """Преобразует нормализованную позицию в пиксельные координаты."""
        return (
            int(renderer.width  * self.x),
            int(renderer.height * self.y),
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Базовый UIElement
# ══════════════════════════════════════════════════════════════════════════════

class UIElement(ABC):
    """Базовый класс всех UI-элементов."""

    position: Position

    @abstractmethod
    def draw(self, renderer: IRenderer) -> None: ...

    def set_position(self, x: float, y: float) -> None:
        self.position = Position(x, y)


# ══════════════════════════════════════════════════════════════════════════════
#  TextElement — общая база для Text и Button
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class TextElement(UIElement):
    """
    Элемент с текстом, позицией, цветом и выравниванием.

    Атрибуты:
        text:     Отображаемая строка.
        position: Нормализованная позиция якоря.
        color:    Цвет текста (None = цвет терминала по умолчанию).
        anchor:   Выравнивание LEFT / CENTER / RIGHT.
    """
    text:     str
    position: Position
    color:    IColor | None = None
    anchor:   Anchor       = Anchor.CENTER
    static:   bool         = True

    def __post_init__(self) -> None:
        if not isinstance(self.position, Position):
            raise TypeError(f"position must be Position, got {type(self.position).__name__}")
        #if self.color is not None and not isinstance(self.color, IColor):
        #    raise TypeError(f"color must be Color | None, got {type(self.color).__name__}")

    def screen_x(self, renderer: IRenderer) -> int:
        """Вычисляет экранный X с учётом выравнивания."""
        x, _ = self.position.to_screen(renderer)
        match self.anchor:
            case Anchor.CENTER: return x - len(self.text) // 2
            case Anchor.RIGHT:  return x - len(self.text)
            case _:             return x

    def screen_xy(self, renderer: IRenderer) -> tuple[int, int]:
        _, y = self.position.to_screen(renderer)
        return self.screen_x(renderer), y

    def draw(self, renderer: IRenderer) -> None:
        x, y = self.screen_xy(renderer)
        renderer.draw_string(x, y, self.text, self.color)


# ══════════════════════════════════════════════════════════════════════════════
#  Конкретные элементы
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class Text(TextElement):
    """Статический текстовый лейбл."""
    pass


@dataclass(slots=True)
class Button(TextElement):
    """
    Кнопка с действием и опциональным цветом при выделении.

    Атрибуты:
        action:         Вызывается при нажатии Enter/E/F.
                        Может вернуть UIStatus или любое пользовательское значение.
        selected_color: Цвет текста когда кнопка выбрана курсором
                        (None = тот же что color).
    """
    action:         Callable[[], Any] = field(default=lambda: None)
    selected_color: IColor | None      = field(default=None)

    def __post_init__(self) -> None:
        # TextElement.__post_init__ validates position; reuse it.
        try:
            super().__post_init__()
        except Exception:
            pass
        # Кнопки по умолчанию не статичны — избегаем попадания в кэш по умолчанию
        self.static = False

    def activate(self) -> Any:
        return self.action()


# ══════════════════════════════════════════════════════════════════════════════
#  Таблицы навигации (вынесены на уровень модуля — один экземпляр)
# ══════════════════════════════════════════════════════════════════════════════

# Клавиши навигации → направление (−1 вверх, +1 вниз)
_NAV: dict[str, int] = {"w": -1, "s": 1, "up": -1, "down": 1}
# Клавиши активации кнопки
_ACT: frozenset[str] = frozenset({"enter", "e", "f"})
# Клавиши «назад»
_BACK: frozenset[str] = frozenset({"q", "backspace"})


# ══════════════════════════════════════════════════════════════════════════════
#  Interface
# ══════════════════════════════════════════════════════════════════════════════

class Interface:
    """
    Контейнер UI-элементов с навигацией курсором и обработкой ввода.

    Параметры:
        renderer:      Экземпляр ConsoleRenderer (или любой IRenderer).
        border:        Строка символов рамки: horiz, vert, TL, BL, TR, BR.
                       "" — рамка не рисуется.
        footer:        Текст в нижней части рамки (None — не рисуется).
        cursor_char:   Символ курсора рядом с выбранной кнопкой.
        border_color:  Цвет рамки (None = терминальный цвет по умолчанию).
        footer_color:  Цвет footer-текста.
        wrap_cursor:   Если True — курсор перепрыгивает через края списка.
    """

    __slots__ = (
        "renderer", "border", "footer", "cursor_char",
        "border_color", "footer_color", "wrap_cursor",
        "_elements", "_buttons", "_cursor",
        "_static_buffer", "_static_selector",
    )

    def __init__(
        self,
        renderer:     IRenderer,
        border:       str        = "─│╭╰╮╯",
        footer:       str | None = None,
        cursor_char:  str        = "▶",
        border_color: IColor | None = None,
        footer_color: IColor | None = None,
        wrap_cursor:  bool         = True,
    ) -> None:
        if not border and border is not None:
            border = ""
        if len(cursor_char) != 1:
            raise ValueError(f"cursor_char must be exactly 1 character, got {cursor_char!r}")

        self.renderer     = renderer
        self.border       = border
        self.footer       = footer
        self.cursor_char  = cursor_char
        self.border_color = border_color
        self.footer_color = footer_color
        self.wrap_cursor  = wrap_cursor

        self._elements: list[UIElement] = []
        self._buttons:  list[Button]    = []
        self._cursor:   int             = 0
        self._static_buffer: list[list[tuple[str, IColor] | None]] | None = None
        self._static_selector: Optional[Callable[[UIElement], bool]] = None

    # ── Построение ────────────────────────────────────────────────────────────

    def add(self, element: UIElement) -> "Interface":
        """Добавляет элемент. Кнопки автоматически попадают в список навигации."""
        if not isinstance(element, UIElement):
            raise TypeError(f"Expected UIElement, got {type(element).__name__}")
        self._elements.append(element)
        if isinstance(element, Button):
            self._buttons.append(element)
        # Инвалидируем кэш предрендера при изменении набора элементов
        self._static_buffer = None
        self._static_selector = None
        return self

    def add_many(self, elements: list[UIElement]) -> "Interface":
        for el in elements:
            self.add(el)
        return self

    def clear(self) -> "Interface":
        """Удаляет все элементы и сбрасывает курсор."""
        self._elements.clear()
        self._buttons.clear()
        self._cursor = 0
        self._static_buffer = None
        self._static_selector = None
        return self

    # ── Рендеринг ─────────────────────────────────────────────────────────────

    def show(self) -> None:
        """
        Рисует все элементы, рамку и курсор в буфер рендерера.
        Не вызывает renderer.display() — это задача игрового цикла.
        """
        r = self.renderer

        # Если есть кэш предрендера и он совпадает по размеру — блитнем его
        sb = self._static_buffer
        if sb is not None and len(sb) == r.height and (len(sb[0]) if sb else 0) == r.width:
            # Копируем только заполненные пиксели
            buf = r.buffer
            for y, row in enumerate(sb):
                dst_row = buf[y]
                for x, pix in enumerate(row):
                    if pix is not None:
                        dst_row[x] = pix

            # Рисуем динамические элементы (те, что не попали в кэш)
            selector = self._static_selector
            for el in self._elements:
                if selector is not None and selector(el):
                    continue
                el.draw(r)
        else:
            # Без кэша — обычный полный рендер
            self._draw_border()
            for el in self._elements:
                el.draw(r)

        self._draw_cursor(self.cursor_char)

    def cache_static(self, selector: Optional[Callable[[UIElement], bool]] = None) -> None:
        """Вычислить и сохранить предрендер (кэш) для статичных элементов.

        `selector` — функция, принимающая элемент и возвращающая True,
        если элемент считается статичным и должен попасть в кэш.
        По умолчанию в кэш попадают все элементы, кроме `Button`.
        """
        if selector is None:
            # По умолчанию кэшируем только элементы, помеченные как static
            selector = lambda el: getattr(el, "static", False)

        r = self.renderer
        w, h = r.width, r.height

        # Временный локальный буфер: None = пусто, иначе Pixel
        tmp: list[list[tuple[str, IColor] | None]] = [[None] * w for _ in range(h)]

        class _LocalRenderer:
            def __init__(self, buf, width, height):
                self._buf = buf
                self.width = width
                self.height = height

            def draw_pixel(self, x: int, y: int, char: str, color: IColor | None = None) -> None:
                if 0 <= x < self.width and 0 <= y < self.height:
                    self._buf[y][x] = (char, color if color is not None else _RESET_COLOR)

            def draw_string(self, x: int, y: int, text: str, color: IColor | None = None, length_into_account: bool | str = False) -> None:
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
                        raise ValueError("invalid length_into_account")
                for i, ch in enumerate(text):
                    px = x + i - offset
                    if 0 <= px < self.width and 0 <= y < self.height:
                        self._buf[y][px] = (ch, color if color is not None else _RESET_COLOR)

            def draw_box(self, x: int, y: int, w: int, h: int, border_char_h: str = "█", border_char_v: str = "█", color: IColor | None = None) -> None:
                if w < 2 or h < 2:
                    return
                for i in range(w):
                    self.draw_pixel(x + i, y, border_char_h, color)
                    self.draw_pixel(x + i, y + h - 1, border_char_h, color)
                for i in range(1, h - 1):
                    self.draw_pixel(x, y + i, border_char_v, color)
                    self.draw_pixel(x + w - 1, y + i, border_char_v, color)

        local = _LocalRenderer(tmp, w, h)

        # Временно подменим renderer чтобы переиспользовать _draw_border
        orig = self.renderer
        try:
            self.renderer = local  # type: ignore
            # Рисуем рамку и footer в локальный буфер
            self._draw_border()
            # Рисуем выбранные статичные элементы
            for el in self._elements:
                if selector(el):
                    el.draw(local)
        finally:
            self.renderer = orig

        self._static_buffer = tmp
        self._static_selector = selector

    def invalidate_static(self) -> None:
        """Инвалидирует кэш предрендера."""
        self._static_buffer = None
        self._static_selector = None

    def _draw_border(self) -> None:
        b = self.border
        if not b:
            return

        r    = self.renderer
        w, h = r.width, r.height
        n    = len(b)
        bc   = self.border_color

        # Рисуем основную рамку (горизонталь + вертикаль)
        horiz = b[0]
        vert  = b[1] if n > 1 else b[0]
        r.draw_box(0, 0, w, h, horiz, vert, bc)

        # Угловые символы
        corners: tuple[str | None, str | None, str | None, str | None]
        if n >= 6:
            corners = (b[2], b[3], b[4], b[5])   # TL, BL, TR, BR
        elif n >= 3:
            c = b[2]
            corners = (c, c, c, c)
        else:
            corners = (None, None, None, None)

        tl, bl, tr, br = corners
        if tl: r.draw_pixel(0,     0,     tl, bc)
        if tr: r.draw_pixel(w - 1, 0,     tr, bc)
        if bl: r.draw_pixel(0,     h - 1, bl, bc)
        if br: r.draw_pixel(w - 1, h - 1, br, bc)

        # Footer
        if self.footer:
            r.draw_string(w // 2, h - 1, self.footer,
                          self.footer_color, length_into_account=True)

    def _draw_cursor(self, symbol: str) -> None:
        """Рисует символ курсора левее текущей выбранной кнопки."""
        if not self._buttons:
            return
        button = self._buttons[self._cursor]
        x, y   = button.screen_xy(self.renderer)

        # Если у кнопки задан selected_color — перерисовываем текст кнопки тоже
        sc = button.selected_color
        if sc is not None:
            self.renderer.draw_string(x, y, button.text, sc)

        self.renderer.draw_pixel(x - 2, y, symbol)

    def _erase_cursor(self) -> None:
        """Убирает курсор и восстанавливает обычный цвет кнопки."""
        if not self._buttons:
            return
        button = self._buttons[self._cursor]
        x, y   = button.screen_xy(self.renderer)

        # Стираем символ курсора
        self.renderer.draw_pixel(x - 2, y, " ")

        # Восстанавливаем нормальный цвет текста кнопки
        if button.selected_color is not None:
            self.renderer.draw_string(x, y, button.text, button.color)

    # ── Ввод ──────────────────────────────────────────────────────────────────

    def handle_key(self, key: str | None) -> UIStatus | Any:
        """
        Обрабатывает одно нажатие клавиши.

        Returns:
            UIStatus.EXIT  — завершить приложение.
            UIStatus.BACK  — вернуться на предыдущий экран.
            UIStatus.NONE  — ничего не произошло.
            Any            — значение, возвращённое action() активированной кнопки.
        """
        if key is None:
            return UIStatus.NONE

        key = key.lower()

        if key in _NAV and self._buttons:
            self._move_cursor(_NAV[key])

        elif key in _ACT and self._buttons:
            result = self._buttons[self._cursor].activate()
            # Если action вернул None — считаем это «ничего не произошло»
            return result if result is not None else UIStatus.NONE

        elif key == "esc":
            return UIStatus.EXIT

        elif key in _BACK:
            return UIStatus.BACK

        return UIStatus.NONE

    def _move_cursor(self, delta: int) -> None:
        n = len(self._buttons)
        if n < 2:
            return

        self._erase_cursor()

        if self.wrap_cursor:
            self._cursor = (self._cursor + delta) % n
        else:
            self._cursor = max(0, min(n - 1, self._cursor + delta))

        self._draw_cursor(self.cursor_char)

    # ── Свойства ──────────────────────────────────────────────────────────────

    @property
    def current_button(self) -> Button | None:
        """Кнопка под курсором, или None если кнопок нет."""
        return self._buttons[self._cursor] if self._buttons else None

    @property
    def cursor(self) -> int:
        return self._cursor

    def set_cursor(self, index: int) -> None:
        """Программно переместить курсор на кнопку с индексом index."""
        n = len(self._buttons)
        if n == 0:
            return
        if not 0 <= index < n:
            raise IndexError(f"Button index {index} out of range [0, {n})")
        self._erase_cursor()
        self._cursor = index
        self._draw_cursor(self.cursor_char)

    def __repr__(self) -> str:
        return (
            f"Interface("
            f"elements={len(self._elements)}, "
            f"buttons={len(self._buttons)}, "
            f"cursor={self._cursor})"
        )