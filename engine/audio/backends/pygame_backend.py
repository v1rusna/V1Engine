import pygame

class PygameBackend:

    def initialize(self):
        pygame.mixer.init()

    def load_sound(self, path):
        return pygame.mixer.Sound(path)

    def shutdown(self):
        pygame.mixer.quit()