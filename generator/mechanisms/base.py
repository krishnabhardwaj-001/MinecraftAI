from abc import ABC, abstractmethod
from typing import Any, List

from generator.models import DatapackResource


class BaseMechanismGenerator(ABC):
    """
    Abstract base class for deterministic datapack mechanism generators.
    Each mechanism generator transforms a high-level specification
    into one or more concrete DatapackResource objects.
    """

    @abstractmethod
    def generate(self, spec: Any) -> List[DatapackResource]:
        """
        Transforms the mechanism specification into concrete DatapackResource instances.
        """
        pass
