from __future__ import annotations

import time

type Seconds = float


class FPSController:
    """
    Точный контроллер частоты кадров.

    Поддерживает два режима ожидания:

    ``precise=True`` (по умолчанию) — три уровня ожидания:
        1. time.sleep(bulk)   — отдаём процессор ОС на большую часть времени
        2. time.sleep(small)  — досыпаем мелкими порциями (< MIN_BUSY_WAIT_S)
        3. busy-wait          — крутимся вхолостую последние ~200 мкс для точности

    ``precise=False`` — один обычный time.sleep() до дедлайна, без busy-wait.
        Не нагружает ядро CPU вхолостую, но кадр может занять на 1-15 мс
        больше целевого (точность зависит от планировщика ОС). Подходит
        для фоновых/нечувствительных к джиттеру сценариев (например,
        серверный тик, не-интерактивный рендер, экономия батареи).

    Использование:
        fps = FPSController(60)
        while True:
            fps.tick()          # ждём до следующего кадра
            update(fps.dt)      # игровая логика
            render()
            # fps.current_fps доступен в любой момент

        # Переключение режима на лету:
        fps.precise = False
    """

    # Порог перехода от sleep к busy-wait (секунды).
    # 0.0002 = 200 мкс — достаточно для большинства ОС.
    MIN_BUSY_WAIT_S: Seconds = 0.0002

    # Запас перед sleep, чтобы не проспать дедлайн (секунды).
    SLEEP_MARGIN_S: Seconds = 0.001

    # Шаг мелких sleep-ов на уровне 2 (секунды).
    SMALL_SLEEP_STEP_S: Seconds = 0.0005

    # Размер окна усреднения для current_fps (секунды).
    FPS_WINDOW_S: Seconds = 1.0

    __slots__ = (
        "_target_frame_time",
        "_frame_start",
        "_fps_window_start",
        "_fps_frame_count",
        "_precise",
        "dt",
        "current_fps",
    )

    def __init__(self, target_fps: int = 30, *, precise: bool = True) -> None:
        if not isinstance(target_fps, int) or target_fps < 1:
            raise ValueError(f"target_fps must be a positive int, got {target_fps!r}")

        now = time.perf_counter()

        self._target_frame_time: Seconds = 1.0 / target_fps
        self._frame_start: Seconds = now
        self._fps_window_start: Seconds = now
        self._fps_frame_count: int = 0
        self._precise: bool = precise

        self.dt: Seconds = 0.0           # Реальное время последнего кадра (секунды)
        self.current_fps: float = 0.0    # Средний FPS за последнее окно

    # ── Настройка ─────────────────────────────

    def set_fps(self, target_fps: int) -> None:
        """Изменить целевой FPS на лету."""
        if not isinstance(target_fps, int) or target_fps < 1:
            raise ValueError(f"target_fps must be a positive int, got {target_fps!r}")
        self._target_frame_time = 1.0 / target_fps

    @property
    def target_fps(self) -> float:
        return 1.0 / self._target_frame_time

    @property
    def precise(self) -> bool:
        """Включён ли режим высокой точности (busy-wait в хвосте кадра)."""
        return self._precise

    @precise.setter
    def precise(self, value: bool) -> None:
        self._precise = bool(value)

    # ── Основной метод ─────────────────────────

    def tick(self) -> Seconds:
        """
        Ждёт до следующего дедлайна кадра, затем обновляет dt и current_fps.

        Returns:
            dt: реальное время кадра в секундах (удобно для цепочек).

        Вызывать один раз в начале (или конце) игрового цикла.
        """
        perf_counter = time.perf_counter  # локальная ссылка — быстрее в горячем цикле
        deadline = self._frame_start + self._target_frame_time

        now = perf_counter()
        if self._precise:
            sleep = time.sleep
            min_busy = self.MIN_BUSY_WAIT_S
            margin = self.SLEEP_MARGIN_S
            step = self.SMALL_SLEEP_STEP_S

            # ── Уровень 1: крупный sleep ──────────
            remaining = deadline - now
            if remaining > margin + min_busy:
                sleep(remaining - margin - min_busy)

            # ── Уровень 2: мелкие sleep-и ─────────
            remaining = deadline - perf_counter()
            while remaining > min_busy:
                sleep(step if remaining - min_busy > step else remaining - min_busy)
                remaining = deadline - perf_counter()

            # ── Уровень 3: busy-wait ─────────────
            while perf_counter() < deadline:
                pass

            now = perf_counter()
        else:
            # ── Быстрый режим: один sleep без busy-wait ──
            remaining = deadline - now
            if remaining > 0:
                time.sleep(remaining)
                now = perf_counter()

        # ── Фиксируем метки ───────────────────
        self.dt = now - self._frame_start
        self._frame_start = now

        # ── Обновляем счётчик FPS ─────────────
        self._fps_frame_count += 1
        window = now - self._fps_window_start
        if window >= self.FPS_WINDOW_S:
            self.current_fps = self._fps_frame_count / window
            self._fps_frame_count = 0
            self._fps_window_start = now

        return self.dt

    # ── Утилиты ───────────────────────────────

    def reset(self) -> None:
        """Сбросить таймер (например, после долгой паузы/загрузки)."""
        now = time.perf_counter()
        self._frame_start = now
        self._fps_window_start = now
        self._fps_frame_count = 0
        self.dt = 0.0
        self.current_fps = 0.0

    def __repr__(self) -> str:
        mode = "precise" if self._precise else "fast"
        return (
            f"FPSController("
            f"target={self.target_fps:.0f}fps, "
            f"current={self.current_fps:.1f}fps, "
            f"dt={self.dt * 1000:.2f}ms, "
            f"mode={mode})"
        )