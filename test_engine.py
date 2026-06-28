"""
test_engine.py — Тесты и бенчмарки для компонентов мини-движка.

Запуск:
    python test_engine.py              # все тесты + бенчмарки
    python test_engine.py unit         # только юнит-тесты
    python test_engine.py bench        # только бенчмарки
    python test_engine.py fps          # только тест FPSController
"""
from __future__ import annotations

import io
import math
import sys
import time
import unittest
from contextlib import redirect_stdout
from typing import Callable

# ── Импорт компонентов движка ─────────────────────────────────────────────────
from engine import Color, ConsoleRenderer, FPSController
from engine.core.console_renderer import _RESET_COLOR


# ══════════════════════════════════════════════════════════════════════════════
#  Утилиты для тестов
# ══════════════════════════════════════════════════════════════════════════════

PASS  = "\033[32m✓\033[0m"
FAIL  = "\033[31m✗\033[0m"
BENCH = "\033[36m⏱\033[0m"
HEAD  = "\033[1;33m"
RESET = "\033[0m"


def section(title: str) -> None:
    width = 60
    print(f"\n{HEAD}{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}{RESET}")


def bench(label: str, fn: Callable, iterations: int = 10_000) -> float:
    """Запускает fn() iterations раз, возвращает среднее время в микросекундах."""
    # Прогрев
    for _ in range(min(100, iterations // 10)):
        fn()

    t0 = time.perf_counter()
    for _ in range(iterations):
        fn()
    elapsed = time.perf_counter() - t0

    avg_us = (elapsed / iterations) * 1_000_000
    total_ms = elapsed * 1000
    print(f"  {BENCH} {label:<45} {avg_us:>8.2f} µs/iter  ({total_ms:.1f} ms total, {iterations:,} iters)")
    return avg_us


# ══════════════════════════════════════════════════════════════════════════════
#  ЮНИТ-ТЕСТЫ: Color
# ══════════════════════════════════════════════════════════════════════════════

class TestColor(unittest.TestCase):

    # ── Конструктор ───────────────────────────

    def test_valid_rgb(self):
        c = Color(255, 128, 0)
        self.assertEqual(c.r, 255)
        self.assertEqual(c.g, 128)
        self.assertEqual(c.b, 0)

    def test_boundary_values(self):
        Color(0, 0, 0)
        Color(255, 255, 255)

    def test_missing_channel_raises(self):
        with self.assertRaises(ValueError):
            Color(255, 128)         # b отсутствует

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            Color(256, 0, 0)
        with self.assertRaises(ValueError):
            Color(-1, 0, 0)

    def test_wrong_type_raises(self):
        with self.assertRaises(TypeError):
            Color(1.0, 0, 0)        # float вместо int
        with self.assertRaises(TypeError):
            Color("ff", 0, 0)       # str

    # ── ANSI ──────────────────────────────────

    def test_ansi_format(self):
        c = Color(10, 20, 30)
        self.assertEqual(c.ansi, "\033[38;2;10;20;30m")

    def test_reset_ansi(self):
        self.assertEqual(Color.reset().ansi, "\033[0m")

    # ── Singleton reset ───────────────────────

    def test_reset_singleton(self):
        self.assertIs(Color.reset(), Color.reset())
        self.assertIs(Color.reset(), _RESET_COLOR)

    # ── from_hex ──────────────────────────────

    def test_from_hex_with_hash(self):
        c = Color.from_hex("#ff8000")
        self.assertEqual((c.r, c.g, c.b), (255, 128, 0))

    def test_from_hex_without_hash(self):
        c = Color.from_hex("0a141e")
        self.assertEqual((c.r, c.g, c.b), (10, 20, 30))

    def test_from_hex_uppercase(self):
        c = Color.from_hex("#FF8000")
        self.assertEqual((c.r, c.g, c.b), (255, 128, 0))

    def test_from_hex_invalid_length(self):
        with self.assertRaises(ValueError):
            Color.from_hex("#FFF")
        with self.assertRaises(ValueError):
            Color.from_hex("12345")

    def test_from_hex_invalid_chars(self):
        with self.assertRaises(ValueError):
            Color.from_hex("GGHHII")

    # ── Иммутабельность ───────────────────────

    def test_frozen(self):
        c = Color(1, 2, 3)
        with self.assertRaises((AttributeError, TypeError)):
            c.r = 10    # type: ignore

    def test_hashable(self):
        c1, c2 = Color(1, 2, 3), Color(1, 2, 3)
        self.assertEqual(hash(c1), hash(c2))
        s = {c1, c2}
        self.assertEqual(len(s), 1)

    # ── _reset с RGB не ломает __post_init__ ──

    def test_reset_flag_skips_rgb_validation(self):
        # _reset=True должен пропускать валидацию r/g/b
        c = Color(_reset=True)
        self.assertEqual(c.ansi, "\033[0m")


# ══════════════════════════════════════════════════════════════════════════════
#  ЮНИТ-ТЕСТЫ: ConsoleRenderer
# ══════════════════════════════════════════════════════════════════════════════

class TestConsoleRenderer(unittest.TestCase):

    def setUp(self):
        self.r = ConsoleRenderer(20, 10)

    # ── Конструктор ───────────────────────────

    def test_default_buffer_size(self):
        self.assertEqual(len(self.r.buffer), 10)
        self.assertEqual(len(self.r.buffer[0]), 20)

    def test_invalid_width_raises(self):
        with self.assertRaises(ValueError):
            ConsoleRenderer(0, 10)
        with self.assertRaises(ValueError):
            ConsoleRenderer(-1, 10)

    def test_invalid_height_raises(self):
        with self.assertRaises(ValueError):
            ConsoleRenderer(10, 0)

    def test_invalid_bg_char_raises(self):
        with self.assertRaises(ValueError):
            ConsoleRenderer(10, 10, "ab")
        with self.assertRaises(ValueError):
            ConsoleRenderer(10, 10, "")

    def test_bg_char_custom(self):
        r = ConsoleRenderer(5, 3, ".")
        char, _ = r.buffer[0][0]
        self.assertEqual(char, ".")

    # ── draw_pixel ────────────────────────────

    def test_draw_pixel_basic(self):
        c = Color(255, 0, 0)
        self.r.draw_pixel(5, 3, "X", c)
        char, color = self.r.buffer[3][5]
        self.assertEqual(char, "X")
        self.assertIs(color, c)

    def test_draw_pixel_no_color_uses_reset(self):
        self.r.draw_pixel(0, 0, "A")
        _, color = self.r.buffer[0][0]
        self.assertIs(color, _RESET_COLOR)

    def test_draw_pixel_out_of_bounds_ignored(self):
        # Не должно бросать исключение, просто игнорируется
        self.r.draw_pixel(100, 100, "X")
        self.r.draw_pixel(-1, 0, "X")

    def test_draw_pixel_invalid_char_raises(self):
        with self.assertRaises(ValueError):
            self.r.draw_pixel(0, 0, "AB")
        with self.assertRaises(ValueError):
            self.r.draw_pixel(0, 0, "")

    def test_draw_pixel_invalid_color_raises(self):
        with self.assertRaises(TypeError):
            self.r.draw_pixel(0, 0, "X", color="red")  # type: ignore

    # ── get_pixel ─────────────────────────────

    def test_get_pixel_returns_correct(self):
        c = Color(0, 255, 0)
        self.r.draw_pixel(2, 2, "Z", c)
        pixel = self.r.get_pixel(2, 2)
        self.assertIsNotNone(pixel)
        self.assertEqual(pixel[0], "Z")

    def test_get_pixel_out_of_bounds_returns_none(self):
        self.assertIsNone(self.r.get_pixel(-1, 0))
        self.assertIsNone(self.r.get_pixel(0, 100))

    # ── draw_string ───────────────────────────

    def test_draw_string_left_anchor(self):
        self.r.draw_string(0, 0, "Hi", length_into_account=False)
        self.assertEqual(self.r.buffer[0][0][0], "H")
        self.assertEqual(self.r.buffer[0][1][0], "i")

    def test_draw_string_center_anchor(self):
        # Текст "AB" (len=2), offset=1 → start_x = x - 1
        self.r.draw_string(5, 0, "AB", length_into_account=True)
        self.assertEqual(self.r.buffer[0][4][0], "A")
        self.assertEqual(self.r.buffer[0][5][0], "B")

    def test_draw_string_right_anchor(self):
        # "AB" (len=2), offset=2 → chars at x-2, x-1
        self.r.draw_string(5, 0, "AB", length_into_account=">")
        self.assertEqual(self.r.buffer[0][3][0], "A")
        self.assertEqual(self.r.buffer[0][4][0], "B")

    def test_draw_string_clips_left(self):
        # Часть строки за левой границей — не должно падать
        self.r.draw_string(0, 0, "Hello", length_into_account=True)

    def test_draw_string_clips_right(self):
        self.r.draw_string(18, 0, "Hello")  # Часть уйдёт за правый край

    def test_draw_string_empty_noop(self):
        self.r.draw_string(5, 5, "")  # Не должно бросать

    def test_draw_string_invalid_align_raises(self):
        with self.assertRaises(ValueError):
            self.r.draw_string(5, 5, "Hi", length_into_account="?")

    # ── draw_box ──────────────────────────────

    def test_draw_box_corners(self):
        self.r.draw_box(0, 0, 5, 4)
        # Все 4 угла должны быть заполнены
        for corner in [(0,0), (4,0), (0,3), (4,3)]:
            char, _ = self.r.buffer[corner[1]][corner[0]]
            self.assertNotEqual(char, self.r.bg_char)

    def test_draw_box_too_small_raises(self):
        with self.assertRaises(ValueError):
            self.r.draw_box(0, 0, 1, 5)
        with self.assertRaises(ValueError):
            self.r.draw_box(0, 0, 5, 1)

    def test_draw_box_interior_untouched(self):
        self.r.draw_box(0, 0, 5, 4)
        # Внутренность (1,1) должна остаться фоном
        char, _ = self.r.buffer[1][1]
        self.assertEqual(char, self.r.bg_char)

    # ── clear_buffer ──────────────────────────

    def test_clear_buffer_resets_all(self):
        self.r.draw_pixel(5, 5, "X", Color(255, 0, 0))
        self.r.clear_buffer()
        char, color = self.r.buffer[5][5]
        self.assertEqual(char, self.r.bg_char)
        self.assertIs(color, _RESET_COLOR)

    def test_clear_buffer_reuses_lists(self):
        row_ids_before = [id(row) for row in self.r.buffer]
        self.r.clear_buffer()
        row_ids_after = [id(row) for row in self.r.buffer]
        self.assertEqual(row_ids_before, row_ids_after)  # Те же объекты списков

    # ── resize_buffer ─────────────────────────

    def test_resize_buffer_width(self):
        self.r.resize_buffer(width=30)
        self.assertEqual(self.r.width, 30)
        self.assertEqual(len(self.r.buffer[0]), 30)

    def test_resize_buffer_height(self):
        self.r.resize_buffer(height=5)
        self.assertEqual(self.r.height, 5)
        self.assertEqual(len(self.r.buffer), 5)

    def test_resize_buffer_invalid_raises(self):
        with self.assertRaises(ValueError):
            self.r.resize_buffer(width=0)
        with self.assertRaises(ValueError):
            self.r.resize_buffer(height=-1)

    def test_resize_buffer_none_noop(self):
        self.r.resize_buffer()  # Ничего не передано — не должно падать

    # ── display (не пишем в реальный stdout) ──

    def test_display_output_not_empty(self):
        self.r.draw_pixel(0, 0, "X", Color(255, 0, 0))
        buf = io.StringIO()
        with redirect_stdout(buf):
            # display() пишет напрямую в sys.stdout — подменяем
            original = sys.stdout
            sys.stdout = buf
            try:
                self.r.display()
            finally:
                sys.stdout = original
        output = buf.getvalue()
        self.assertIn("X", output)
        self.assertIn("\033[", output)  # ANSI-коды присутствуют

    def test_display_resets_color_at_end(self):
        buf = io.StringIO()
        original = sys.stdout
        sys.stdout = buf
        try:
            self.r.display()
        finally:
            sys.stdout = original
        self.assertTrue(buf.getvalue().endswith("\033[0m"))

    # ── Context manager ───────────────────────

    def test_context_manager_calls_cleanup(self):
        """__exit__ должен вернуть курсор."""
        buf = io.StringIO()
        r = ConsoleRenderer(5, 5)
        original = sys.stdout
        sys.stdout = buf
        try:
            r.setup()
            r.cleanup()
        finally:
            sys.stdout = original
        out = buf.getvalue()
        self.assertIn("\033[?25h", out)  # Курсор восстановлен


# ══════════════════════════════════════════════════════════════════════════════
#  ЮНИТ-ТЕСТЫ: FPSController
# ══════════════════════════════════════════════════════════════════════════════

class TestFPSController(unittest.TestCase):

    def test_invalid_fps_raises(self):
        with self.assertRaises(ValueError):
            FPSController(0)
        with self.assertRaises(ValueError):
            FPSController(-10)
        with self.assertRaises(ValueError):
            FPSController("60")  # type: ignore

    def test_set_fps_invalid_raises(self):
        f = FPSController(30)
        with self.assertRaises(ValueError):
            f.set_fps(0)

    def test_target_fps_property(self):
        f = FPSController(60)
        self.assertAlmostEqual(f.target_fps, 60.0)

    def test_set_fps_updates_target(self):
        f = FPSController(30)
        f.set_fps(60)
        self.assertAlmostEqual(f.target_fps, 60.0)

    def test_dt_positive_after_tick(self):
        f = FPSController(120)
        f.tick()
        self.assertGreater(f.dt, 0)

    def test_dt_reasonable(self):
        """dt не должен быть абсурдным (< 1 секунды для любого fps >= 1)."""
        f = FPSController(60)
        f.tick()
        self.assertLess(f.dt, 1.0)

    def test_reset_clears_state(self):
        f = FPSController(30)
        f.tick()
        f.reset()
        self.assertEqual(f.dt, 0.0)
        self.assertEqual(f.current_fps, 0.0)

    def test_repr_contains_fps(self):
        f = FPSController(30)
        r = repr(f)
        self.assertIn("30", r)
        self.assertIn("fps", r)

    def test_tick_returns_dt(self):
        f = FPSController(120)
        result = f.tick()
        self.assertEqual(result, f.dt)


# ══════════════════════════════════════════════════════════════════════════════
#  БЕНЧМАРКИ
# ══════════════════════════════════════════════════════════════════════════════

def run_benchmarks() -> None:
    section("БЕНЧМАРКИ")

    RED   = Color(255, 50, 50)
    GREEN = Color(50, 255, 100)

    # ── Color ─────────────────────────────────
    print("\n  Color")
    bench("Color(255, 128, 0) — создание",   lambda: Color(255, 128, 0))
    bench("Color.from_hex('#ff8000')",        lambda: Color.from_hex("#ff8000"))
    bench("Color.reset() — singleton",        lambda: Color.reset())
    bench("Color(10,20,30).ansi — property",  lambda: Color(10, 20, 30).ansi)

    # ── ConsoleRenderer — малый буфер ─────────
    print("\n  ConsoleRenderer 40×20")
    r_small = ConsoleRenderer(40, 20)

    bench("draw_pixel (центр)",               lambda: r_small.draw_pixel(20, 10, "X", RED))
    bench("draw_pixel (out of bounds)",       lambda: r_small.draw_pixel(999, 999, "X", RED))
    bench("draw_string len=10 (no align)",    lambda: r_small.draw_string(0, 0, "Hello World"))
    bench("draw_string len=10 (center)",      lambda: r_small.draw_string(20, 10, "Hello World", length_into_account=True))
    bench("draw_box 10×5",                    lambda: r_small.draw_box(5, 5, 10, 5, color=GREEN))
    bench("get_pixel",                        lambda: r_small.get_pixel(10, 5))
    bench("clear_buffer 40×20",               lambda: r_small.clear_buffer(), iterations=5_000)

    # display() пишет в stdout — перехватываем
    _null = open(os.devnull, "w") if hasattr(sys, "_is_test") else io.StringIO()

    def _display_small():
        orig = sys.stdout
        sys.stdout = _null
        r_small.display()
        sys.stdout = orig

    bench("display() 40×20 (captured)",      _display_small, iterations=2_000)

    # ── ConsoleRenderer — большой буфер ───────
    print("\n  ConsoleRenderer 200×50")
    r_large = ConsoleRenderer(200, 50)

    bench("clear_buffer 200×50",             lambda: r_large.clear_buffer(), iterations=2_000)

    def _display_large():
        orig = sys.stdout
        sys.stdout = _null
        r_large.display()
        sys.stdout = orig

    bench("display() 200×50 (captured)",    _display_large, iterations=500)
    bench("draw_string len=20 (centered)",  lambda: r_large.draw_string(100, 25, "Hello from the engine!", length_into_account=True))

    # ── FPSController ─────────────────────────
    print("\n  FPSController")
    bench("FPSController(60) — создание",   lambda: FPSController(60), iterations=1_000)

    f = FPSController(60)
    bench("target_fps property",            lambda: f.target_fps)
    bench("set_fps(60)",                    lambda: f.set_fps(60))
    bench("reset()",                        lambda: f.reset())

    _null.close() if hasattr(_null, "close") else None


# ══════════════════════════════════════════════════════════════════════════════
#  FPS-ТОЧНОСТЬ — отдельный живой тест
# ══════════════════════════════════════════════════════════════════════════════

def run_fps_accuracy_test(target: int = 60, duration: float = 2.0) -> None:
    section(f"FPS ТОЧНОСТЬ — цель {target} fps, {duration:.0f} сек")

    f = FPSController(target, precise=True)
    target_dt = 1.0 / target

    samples: list[float] = []
    t_end = time.perf_counter() + duration

    while time.perf_counter() < t_end:
        f.tick()
        samples.append(f.dt)

    if not samples:
        print("  Нет данных")
        return

    mean_dt  = sum(samples) / len(samples)
    mean_fps = 1.0 / mean_dt
    variance = sum((x - mean_dt) ** 2 for x in samples) / len(samples)
    std_ms   = math.sqrt(variance) * 1000
    min_fps  = 1.0 / max(samples)
    max_fps  = 1.0 / min(samples)
    jitter   = (max(samples) - min(samples)) * 1000

    error_pct = abs(mean_fps - target) / target * 100

    status = PASS if error_pct < 2.0 else FAIL

    print(f"  Кадров:        {len(samples)}")
    print(f"  Среднее:       {mean_fps:.2f} fps  (цель {target})  {status}")
    print(f"  Ошибка:        {error_pct:.2f}%")
    print(f"  Мин/Макс:      {min_fps:.1f} / {max_fps:.1f} fps")
    print(f"  Среднее dt:    {mean_dt*1000:.3f} ms  (цель {target_dt*1000:.3f} ms)")
    print(f"  Jitter:        {jitter:.3f} ms  (max-min)")
    print(f"  StdDev dt:     {std_ms:.3f} ms")

    if error_pct >= 2.0:
        print(f"  {FAIL}  Ошибка > 2% — планировщик ОС нестабилен или система перегружена")


# ══════════════════════════════════════════════════════════════════════════════
#  ВИЗУАЛЬНЫЙ SMOKE-TEST рендерера
# ══════════════════════════════════════════════════════════════════════════════

def run_render_smoke_test() -> None:
    section("RENDER SMOKE TEST (stdout)")

    r = ConsoleRenderer(50, 12)

    r.draw_box(0, 0, 50, 12, "─", "│", Color(100, 100, 100))
    r.draw_box(0, 0, 50, 12, "+", "+", Color(100, 100, 100))  # Углы
    r.draw_pixel(0, 0, "┌", Color(100, 100, 100))
    r.draw_pixel(49, 0, "┐", Color(100, 100, 100))
    r.draw_pixel(0, 11, "└", Color(100, 100, 100))
    r.draw_pixel(49, 11, "┘", Color(100, 100, 100))

    r.draw_string(25, 2, "MINI ENGINE v1.0", Color(255, 220, 50), length_into_account=True)
    r.draw_string(25, 4, "ConsoleRenderer", Color(100, 200, 255), length_into_account=True)
    r.draw_string(25, 5, "FPSController", Color(100, 255, 150), length_into_account=True)
    r.draw_string(25, 6, "ConsoleInput", Color(255, 150, 100), length_into_account=True)
    r.draw_string(25, 9, "All systems operational", Color(180, 180, 180), length_into_account=True)

    # Цветной градиент снизу
    for x in range(50):
        t = x / 49
        color = Color(int(255 * t), int(100 * (1 - t)), int(255 * (1 - t)))
        r.draw_pixel(x, 10, "▄", color)

    # Вывод напрямую (smoke test — смотрим глазами)
    print()
    original = sys.stdout
    # display() использует ANSI — выводим как есть
    r.display()
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  RUNNER
# ══════════════════════════════════════════════════════════════════════════════

import os

def run_unit_tests() -> bool:
    section("ЮНИТ-ТЕСТЫ")
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestColor))
    suite.addTests(loader.loadTestsFromTestCase(TestConsoleRenderer))
    suite.addTests(loader.loadTestsFromTestCase(TestFPSController))

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    print(f"\n{HEAD}{'═' * 60}")
    print(f"  MINI ENGINE — TEST SUITE")
    print(f"  Python {sys.version.split()[0]}  |  mode: {mode}")
    print(f"{'═' * 60}{RESET}")

    success = True

    if mode in ("all", "unit"):
        success = run_unit_tests() and success

    if mode in ("all", "bench"):
        run_benchmarks()

    if mode in ("all", "fps"):
        run_fps_accuracy_test(999)
        run_fps_accuracy_test(240)
        run_fps_accuracy_test(120)
        run_fps_accuracy_test(60)
        if mode == "all":
            run_fps_accuracy_test(30)

    if mode in ("all", "smoke"):
        run_render_smoke_test()

    if mode == "all":
        run_render_smoke_test()

    print(f"\n{HEAD}{'═' * 60}{RESET}")
    status_str = f"{PASS} Все тесты прошли" if success else f"{FAIL} Есть упавшие тесты"
    print(f"  {status_str}\n")
    sys.exit(0 if success else 1)


# ══════════════════════════════════════════════════════════════════════════════
#  ЮНИТ-ТЕСТЫ: ui_input
# ══════════════════════════════════════════════════════════════════════════════

from ui_input import InputStatus, InputTheme, TextField, NumberField, PasswordField, SelectField

class TestTextField(unittest.TestCase):

    def _make(self, **kw): return TextField(**kw)

    def test_type_chars(self):
        f = self._make()
        for ch in "Hello": f.handle_key(ch)
        self.assertEqual("".join(f._buf), "Hello")

    def test_backspace(self):
        f = self._make()
        for ch in "Hi": f.handle_key(ch)
        f.handle_key("backspace")
        self.assertEqual("".join(f._buf), "H")

    def test_backspace_empty_noop(self):
        f = self._make()
        f.handle_key("backspace")  # не падает

    def test_delete(self):
        f = self._make()
        for ch in "Hi": f.handle_key(ch)
        f.handle_key("home")
        f.handle_key("delete")
        self.assertEqual("".join(f._buf), "i")

    def test_navigation_left_right_home_end(self):
        f = self._make()
        for ch in "Hi": f.handle_key(ch)
        f.handle_key("left");  self.assertEqual(f._cur, 1)
        f.handle_key("right"); self.assertEqual(f._cur, 2)
        f.handle_key("home");  self.assertEqual(f._cur, 0)
        f.handle_key("end");   self.assertEqual(f._cur, 2)

    def test_max_length(self):
        f = self._make(max_length=3)
        for ch in "abcd": f.handle_key(ch)
        self.assertEqual(len(f._buf), 3)

    def test_allowed_chars(self):
        f = self._make(allowed_chars="abc")
        f.handle_key("a"); f.handle_key("z"); f.handle_key("b")
        self.assertEqual("".join(f._buf), "ab")

    def test_enter_returns_done(self):
        f = self._make()
        for ch in "ok": f.handle_key(ch)
        self.assertEqual(f.handle_key("enter"), InputStatus.DONE)
        self.assertEqual(f.value, "ok")

    def test_esc_returns_cancel(self):
        f = self._make()
        self.assertEqual(f.handle_key("esc"), InputStatus.CANCEL)
        self.assertIsNone(f.value)

    def test_none_key_noop(self):
        f = self._make()
        self.assertEqual(f.handle_key(None), InputStatus.ACTIVE)

    def test_draw_smoke(self):
        r = ConsoleRenderer(60, 20)
        f = self._make()
        f.draw(r)  # не должно падать


class TestNumberField(unittest.TestCase):

    def test_initial_value(self):
        f = NumberField(initial=42)
        self.assertEqual(f._try_parse(), 42)

    def test_arrows_up_down(self):
        f = NumberField(initial=10, step=2)
        f.handle_key("up");   self.assertEqual(f._try_parse(), 12)
        f.handle_key("down"); self.assertEqual(f._try_parse(), 10)

    def test_clamp_min(self):
        f = NumberField(min_val=5, initial=5)
        f.handle_key("down")
        self.assertEqual(f._try_parse(), 5)

    def test_clamp_max(self):
        f = NumberField(max_val=10, initial=10)
        f.handle_key("up")
        self.assertEqual(f._try_parse(), 10)

    def test_only_digits(self):
        f = NumberField(initial=0)
        raw = f._raw_text()
        f.handle_key("a")
        self.assertEqual(f._raw_text(), raw)

    def test_negative_allowed(self):
        f = NumberField(allow_negative=True, initial=0)
        f._buf = []; f._cur = 0
        f.handle_key("-"); f.handle_key("5")
        self.assertEqual(f._try_parse(), -5)

    def test_negative_blocked(self):
        f = NumberField(allow_negative=False, initial=0)
        f._buf = []; f._cur = 0
        f.handle_key("-")
        self.assertNotIn("-", f._buf)

    def test_double_minus_blocked(self):
        f = NumberField(allow_negative=True, initial=0)
        f._buf = []; f._cur = 0
        f.handle_key("-"); f.handle_key("-")
        self.assertEqual(f._buf.count("-"), 1)

    def test_validation_below_min(self):
        f = NumberField(min_val=10, initial=5)
        self.assertEqual(f.handle_key("enter"), InputStatus.ACTIVE)
        self.assertNotEqual(f._error, "")

    def test_enter_valid(self):
        f = NumberField(min_val=0, max_val=100, initial=50)
        self.assertEqual(f.handle_key("enter"), InputStatus.DONE)
        self.assertEqual(f.value, 50)

    def test_esc_cancel(self):
        f = NumberField(initial=5)
        self.assertEqual(f.handle_key("esc"), InputStatus.CANCEL)
        self.assertIsNone(f.value)

    def test_draw_smoke(self):
        r = ConsoleRenderer(60, 20)
        NumberField(min_val=0, max_val=99, initial=50).draw(r)


class TestPasswordField(unittest.TestCase):

    def test_chars_stored(self):
        f = PasswordField()
        f.handle_key("a"); f.handle_key("b")
        self.assertEqual("".join(f._buf), "ab")

    def test_backspace(self):
        f = PasswordField()
        f.handle_key("x"); f.handle_key("backspace")
        self.assertEqual(f._buf, [])

    def test_min_length_enforced(self):
        f = PasswordField(min_length=4)
        for ch in "abc": f.handle_key(ch)
        self.assertEqual(f.handle_key("enter"), InputStatus.ACTIVE)
        self.assertNotEqual(f._error, "")

    def test_enter_after_min_length(self):
        f = PasswordField(min_length=2)
        f.handle_key("a"); f.handle_key("b")
        self.assertEqual(f.handle_key("enter"), InputStatus.DONE)
        self.assertEqual(f.value, "ab")

    def test_max_length(self):
        f = PasswordField(max_length=3)
        for ch in "abcd": f.handle_key(ch)
        self.assertEqual(len(f._buf), 3)

    def test_esc_cancel(self):
        f = PasswordField()
        self.assertEqual(f.handle_key("esc"), InputStatus.CANCEL)
        self.assertIsNone(f.value)

    def test_draw_smoke(self):
        r = ConsoleRenderer(60, 20)
        PasswordField().draw(r)


class TestSelectField(unittest.TestCase):

    OPTS = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]

    def test_initial_cursor(self):
        s = SelectField(self.OPTS, initial_index=2)
        self.assertEqual(s._cursor, 2)

    def test_initial_index_clamp(self):
        s = SelectField(self.OPTS, initial_index=999)
        self.assertEqual(s._cursor, 4)

    def test_navigation_down_up(self):
        s = SelectField(self.OPTS)
        s.handle_key("down"); self.assertEqual(s._cursor, 1)
        s.handle_key("up");   self.assertEqual(s._cursor, 0)

    def test_no_overflow_top(self):
        s = SelectField(self.OPTS)
        s.handle_key("up")
        self.assertEqual(s._cursor, 0)

    def test_no_overflow_bottom(self):
        s = SelectField(self.OPTS, initial_index=4)
        s.handle_key("down")
        self.assertEqual(s._cursor, 4)

    def test_scroll_follows_cursor(self):
        s = SelectField(self.OPTS, max_visible=3)
        for _ in range(3): s.handle_key("down")
        self.assertEqual(s._cursor, 3)
        self.assertEqual(s._scroll, 1)

    def test_home_end(self):
        s = SelectField(self.OPTS, initial_index=3)
        s.handle_key("home"); self.assertEqual(s._cursor, 0); self.assertEqual(s._scroll, 0)
        s.handle_key("end");  self.assertEqual(s._cursor, 4)

    def test_enter_returns_done(self):
        s = SelectField(self.OPTS, initial_index=2)
        self.assertEqual(s.handle_key("enter"), InputStatus.DONE)
        self.assertEqual(s.value, "Gamma")
        self.assertEqual(s.index, 2)

    def test_esc_cancel(self):
        s = SelectField(self.OPTS)
        self.assertEqual(s.handle_key("esc"), InputStatus.CANCEL)
        self.assertIsNone(s.value)

    def test_empty_options_raises(self):
        with self.assertRaises(ValueError):
            SelectField([])

    def test_draw_smoke(self):
        r = ConsoleRenderer(60, 20)
        SelectField(self.OPTS).draw(r)