from abc import ABC, abstractmethod

class ComputerUseBaseAgent(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def reset(self):
        pass

    # @abstractmethod
    # def evaluate(self):
    #     pass

    @abstractmethod
    def predict(self):
        pass
