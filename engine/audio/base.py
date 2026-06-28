from abc import ABC, abstractmethod


class AudioBackend(ABC):

    @abstractmethod
    def initialize(self):
        pass

    @abstractmethod
    def load_sound(self, path: str):
        pass

    @abstractmethod
    def shutdown(self):
        pass