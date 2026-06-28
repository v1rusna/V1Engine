"""Quick Start Example for the Engine project.

Запуск: python quick_start.py

Демонстрирует: рендер простых строк, использование `Interface` и обработку клавиш.
"""
import time

from engine import Color
import engine
from engine.ui import Interface, Button, Position, Text

_COLOR_LOG = Color(10, 255, 255)

def main():
    fps = engine.create_clock(240)
    renderer = engine.create_renderer(178, 50)
    keyboard = engine.create_keyboard()

    # Настраиваем интерфейс с двумя кнопками
    ui = Interface(renderer, footer="Quick Start Example")
    test = Button(f"test button", Position(0.5, 0.45), color=Color(0, 255, 0), action=lambda: "exit", selected_color=Color(0, 0, 230))
    ui.add(test).add(Text("Test text", Position(0.5, 0.35)))

    for j in range(100):
        for i in range(100):
            b = Button(f"button {j}:{i}", Position(j / 100, i / 100), color=Color(255, 0, 0), action=lambda: "exit", selected_color=Color(0, 0, 230))
            b.static = True
            ui.add(b)

    def all_el(el): return True
    ui.cache_static()
    _last_pressed = None


    keyboard.start()
    try:
        with renderer:
            # Простой начальный кадр
            renderer.draw_string(0, 0, "Engine Quick Start", _COLOR_LOG)
            renderer.draw_string(0, 1, "Use W/S or Up/Down to navigate, Enter to activate, Esc to quit.")
            renderer.display()

            time.sleep(0)

            running = True
            while running:
                keyboard.update()
                dt = fps.tick()

                key = keyboard.get_key()
                _last_pressed = keyboard.pressed_keys
                result = ui.handle_key(key)

                if result == "exit" or result is None and key == "esc":
                    break

                if keyboard.is_pressed("h"):
                    test.set_position(test.position.x - 0.01, test.position.y)
                if keyboard.is_pressed("k"):
                    test.set_position(test.position.x + 0.01, test.position.y)
                if keyboard.is_pressed("u"):
                    test.set_position(test.position.x, test.position.y - 0.01)
                if keyboard.is_pressed("j"):
                    test.set_position(test.position.x, test.position.y + 0.01)

                # Перерисовываем экран каждую итерацию
                renderer.clear_buffer()
                ui.show()
                renderer.draw_string(1, 1, "FPS: %s" % fps.current_fps, _COLOR_LOG)
                renderer.draw_string(1, 2, "dt: %s" % dt , _COLOR_LOG)
                renderer.draw_string(1, 3, "key: %s" % key , _COLOR_LOG)
                renderer.draw_string(1, 4, "last_pressed: %s" % _last_pressed , _COLOR_LOG)
                renderer.display()

    finally:
        keyboard.stop()


if __name__ == "__main__":
    main()
