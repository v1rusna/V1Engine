"""
Стресс тест
"""
from engine import Color
import engine
from engine.ui import Interface, Button, Position

def main():
    fps = engine.create_clock(240)
    renderer = engine.create_renderer(178, 50)
    keyboard = engine.create_keyboard()

    # Настраиваем интерфейс с двумя кнопками
    ui = Interface(renderer, footer="Quick Start Example")

    for j in range(100):
        for i in range(100):
            ui.add(
                Button(f"button {j}:{i}", Position(j / 100, i / 100), color=Color(255, 0, 0), action=lambda: "exit", selected_color=Color(0, 0, 230))
            )


    keyboard.start()
    try:
        with renderer:
            # Простой начальный кадр
            renderer.draw_string(0, 0, "Engine Quick Start", Color(10, 255, 255))
            renderer.draw_string(0, 1, "Use W/S or Up/Down to navigate, Enter to activate, Esc to quit.")
            ui.show()
            renderer.display()

            running = True
            while running:
                dt = fps.tick()

                key = keyboard.get_key()
                result = ui.handle_key(key)

                if result == "exit" or result is None and key == "esc":
                    break

                # Перерисовываем экран каждую итерацию
                renderer.clear_buffer()
                ui.show()
                renderer.draw_string(1, 1, "Engine Quick Start", Color(10, 255, 255))
                renderer.draw_string(1, 2, "FPS: %s" % fps.current_fps, Color(10, 255, 255))
                renderer.draw_string(1, 3, "dt: %s" % dt , Color(10, 255, 255))
                renderer.display()

    finally:
        keyboard.stop()


if __name__ == "__main__":
    main()
