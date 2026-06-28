class AudioManager:

    def __init__(self, backend):
        self.backend = backend

    def load(self, path: str):
        ...

    def shutdown(self):
        ...