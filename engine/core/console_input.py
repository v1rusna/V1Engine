from __future__ import annotations

import os
import sys
import time
from collections import deque

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty


class ConsoleInput:
    """
    Кроссплатформенный неблокирующий ввод с клавиатуры.

    Возвращаемые имена клавиш
    ─────────────────────────
    Печатаемые символы   → сам символ ('a', 'Z', '5', …)
    enter                → 'enter'
    backspace            → 'backspace'
    esc                  → 'esc'
    tab                  → 'tab'
    Стрелки              → 'up' / 'down' / 'left' / 'right'
    Home / End           → 'home' / 'end'
    Page Up / Down       → 'pageup' / 'pagedown'
    Insert / Delete      → 'insert' / 'delete'
    F1–F12               → 'f1' … 'f12'
    Ctrl+буква           → 'ctrl+a' … 'ctrl+z'
    Shift+буква          → передаётся регистром символа ('w' vs 'W')
    Нераспознанные       → None

    Два режима использования
    ─────────────────────────
    1) Дискретные события (меню, текстовый ввод):

        with ConsoleInput() as inp:
            key = inp.get_key()       # None если очередь пуста

    2) Непрерывное состояние (движение, в т.ч. диагональное W+D):

        with ConsoleInput() as inp:
            while running:
                inp.update()                     # раз в кадр
                if inp.is_pressed('w'): ...
                if inp.is_pressed('d'): ...       # оба True → диагональ

    is_pressed()/pressed_keys — ЭВРИСТИКА, не точное состояние клавиатуры.
    Подробности и границы применимости — в докстринге is_pressed().
    """

    # ── Таблицы escape-последовательностей ──────────────────────────

    _ANSI_SEQUENCES: dict[str, str] = {
        "[A": "up",    "[B": "down",  "[C": "right", "[D": "left",
        "[H": "home",  "[F": "end",
        "[1~": "home", "[2~": "insert", "[3~": "delete", "[4~": "end",
        "[5~": "pageup", "[6~": "pagedown",
        "OP": "f1",  "OQ": "f2",  "OR": "f3",  "OS": "f4",
        "[15~": "f5",  "[17~": "f6",  "[18~": "f7",  "[19~": "f8",
        "[20~": "f9",  "[21~": "f10", "[23~": "f11", "[24~": "f12",
    }

    _WIN_SCANCODES: dict[bytes, str] = {
        b"H": "up",    b"P": "down",  b"M": "right", b"K": "left",
        b"G": "home",  b"O": "end",
        b"I": "pageup", b"Q": "pagedown",
        b"R": "insert", b"S": "delete",
        b";": "f1",  b"<": "f2",  b"=": "f3",  b">": "f4",
        b"?": "f5",  b"@": "f6",  b"A": "f7",  b"B": "f8",
        b"C": "f9",  b"D": "f10",
        b"\x85": "f11", b"\x86": "f12",
    }

    _WIN_PREFIXES = {b"\x00", b"\xe0"}

    _SIMPLE_KEYS: dict[str, str] = {
        "\r": "enter", "\n": "enter",
        "\x7f": "backspace", "\x08": "backspace",
        "\x1b": "esc",
        "\t": "tab",
    }

    # Ctrl+буква: control-байты 0x01–0x1A одинаковы на Unix и Windows
    # (унаследовано ещё от DOS/ANSI). Коды, уже занятые в _SIMPLE_KEYS
    # (backspace/tab/enter), пропускаем — это сохраняет однозначность.
    _CTRL_LETTERS: dict[str, str] = {
        chr(code): f"ctrl+{chr(ord('a') + code - 1)}"
        for code in range(1, 27)
        if chr(code) not in ("\x08", "\t", "\n", "\r")
    }

    def __init__(self, esc_timeout: float = 0.02, hold_timeout: float = 0.5) -> None:
        """
        Args:
            esc_timeout: Сколько секунд ждать продолжения escape-последовательности
                         на Linux/Mac. 0.02 = 20 мс — достаточно для любого терминала.
            hold_timeout: Сколько секунд клавиша считается «удерживаемой» после
                         последнего появления в потоке ввода. Используется только
                         is_pressed()/pressed_keys — см. их докстринг про границы
                         применимости этой эвристики.
        """
        self._esc_timeout = esc_timeout
        self._hold_timeout = hold_timeout
        self._is_windows = os.name == "nt"
        self._active = False
        self._old_settings = None
        self._pending: deque[str] = deque()
        self._last_seen: dict[str, float] = {}

    # ── Lifecycle ─────────────────────────────

    def start(self) -> None:
        """Переводит терминал в режим немедленного чтения."""
        if self._active:
            return
        if not self._is_windows:
            fd = sys.stdin.fileno()
            if not os.isatty(fd):
                raise OSError("stdin is not a TTY — cannot set raw mode")
            self._old_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        self._pending.clear()
        self._last_seen.clear()
        self._active = True

    def stop(self) -> None:
        """Восстанавливает исходные настройки терминала."""
        if not self._active:
            return
        if not self._is_windows and self._old_settings is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_settings)
            self._old_settings = None
        self._pending.clear()
        self._last_seen.clear()
        self._active = False

    def __enter__(self) -> "ConsoleInput":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.stop()

    def _ensure_active(self) -> None:
        if not self._active:
            raise RuntimeError("ConsoleInput is not started — call start() or use 'with'")

    # ── Публичный API: дискретные события ────────────────────────────

    def get_key(self) -> str | None:
        """
        Неблокирующая проверка нажатия. Возвращает по одной клавише за вызов
        из внутренней очереди (FIFO); если очередь пуста — опрашивает ввод.

        Returns:
            Имя клавиши (строка) или None если ничего не нажато.
        """
        self._ensure_active()
        if not self._pending:
            self.update()
        return self._pending.popleft() if self._pending else None

    # ── Публичный API: непрерывное состояние ─────────────────────────

    def update(self) -> None:
        """
        Считывает ВСЕ байты, накопившиеся во входном потоке к этому моменту
        (а не один символ за вызов) — благодаря этому несколько клавиш,
        зарегистрированных за один кадр (например 'w' и 'd', нажатые почти
        одновременно), не теряются и не сдвигаются на следующий тик.

        Параллельно обновляет метки времени появления каждой клавиши, на
        которых основана эвристика is_pressed()/pressed_keys.

        Вызывайте один раз за кадр игрового цикла, до get_key()/is_pressed().
        """
        self._ensure_active()
        if self._is_windows:
            self._poll_windows()
        else:
            self._poll_unix()

    def is_pressed(self, key: str) -> bool:
        """
        Эвристическая проверка «удержания» клавиши.

        ВАЖНО: это НЕ реальное состояние клавиатуры. Ни termios/tty на Unix,
        ни msvcrt на Windows не сообщают событие KeyUp — терминал отдаёт
        только поток "что было введено", а не "что сейчас физически зажато".
        Клавиша считается «нажатой», если её символ появлялся в потоке не
        позже hold_timeout секунд назад — это использует тот факт, что ОС
        сама генерирует повторяющиеся символы, пока клавиша зажата
        (автоповтор).

        Ограничения (присущи самому подходу, не реализации):
          • Между физическим нажатием и первым автоповтором есть пауза
            (обычно 250–650 мс, зависит от ОС/терминала) — в этот
            промежуток is_pressed() может ошибочно вернуть False.
          • После реального отпускания клавиша ещё до hold_timeout секунд
            будет считаться «нажатой» (ghost hold).
          • Не подходит для жанров, требовательных к точному таймингу
            (платформер, файтинг, шутер) — там нужен настоящий keyboard
            state API.

        Args:
            key: имя клавиши в формате get_key() (например 'w', 'W', 'up').
        """
        last = self._last_seen.get(key)
        return last is not None and (time.monotonic() - last) <= self._hold_timeout

    @property
    def pressed_keys(self) -> frozenset[str]:
        """Снимок клавиш, которые по эвристике is_pressed() сейчас «нажаты»."""
        now = time.monotonic()
        return frozenset(
            key for key, ts in self._last_seen.items()
            if now - ts <= self._hold_timeout
        )

    # ── Внутренний опрос: вычитывает всё, что доступно прямо сейчас ──

    def _poll_unix(self) -> None:
        while select.select([sys.stdin], [], [], 0)[0]:
            key = self._decode_unix_event()
            if key is not None:
                now = time.monotonic()
                self._pending.append(key)
                self._last_seen[key] = now
            # Нераспознанный байт уже вычитан из потока — пропускаем его,
            # цикл продолжает обработку остальных накопленных байт.

    def _poll_windows(self) -> None:
        while msvcrt.kbhit():
            key = self._decode_windows_event()
            if key is not None:
                now = time.monotonic()
                self._pending.append(key)
                self._last_seen[key] = now

    # ── Декодирование одного события ─────────────────────────────────

    def _decode_windows_event(self) -> str | None:
        try:
            raw = msvcrt.getch()
        except OSError:
            return None

        if raw in self._WIN_PREFIXES:
            try:
                scancode = msvcrt.getch()
            except OSError:
                return None
            return self._WIN_SCANCODES.get(scancode)

        try:
            char = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None

        if char in self._SIMPLE_KEYS:
            return self._SIMPLE_KEYS[char]
        if char in self._CTRL_LETTERS:
            return self._CTRL_LETTERS[char]
        return char if char.isprintable() else None

    def _decode_unix_event(self) -> str | None:
        try:
            char = sys.stdin.read(1)
        except OSError:
            return None
        if not char:
            return None

        if char != "\x1b":
            if char in self._SIMPLE_KEYS:
                return self._SIMPLE_KEYS[char]
            if char in self._CTRL_LETTERS:
                return self._CTRL_LETTERS[char]
            return char if char.isprintable() else None

        seq = self._read_escape_sequence()
        if not seq:
            return "esc"
        return self._ANSI_SEQUENCES.get(seq)

    def _read_escape_sequence(self) -> str:
        """Читает байты escape-последовательности до таймаута или терминатора."""
        seq = ""
        deadline_s = self._esc_timeout

        while True:
            ready = select.select([sys.stdin], [], [], deadline_s)[0]
            if not ready:
                break
            try:
                ch = sys.stdin.read(1)
            except OSError:
                break
            if not ch:
                break

            seq += ch
            deadline_s = 0.005

            if ch.isalpha() or ch == "~":
                break

        return seq