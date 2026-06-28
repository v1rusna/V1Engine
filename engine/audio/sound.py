class Sound:

    def __init__(self, backend_sound):
        self._sound = backend_sound

    def play(self):
        ...

    def stop(self):
        ...

    def pause(self):
        ...