"""Blackboard primitives. Each engine owns a fresh board for each request."""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Blackboard:
    inputs: dict
    facts: dict = field(default_factory=dict)
    candidates: list = field(default_factory=list)
    trace: list = field(default_factory=list)


@dataclass(frozen=True)
class KnowledgeSource:
    name: str
    execute: Callable
    applicable: Callable = lambda board: True


class ControlComponent:
    def run(self, board, sources):
        for source in sources:
            if source.applicable(board):
                source.execute(board)
                board.trace.append(source.name)
        return board


class ResultGenerator:
    def generate(self, board):
        return {"candidates": board.candidates, "facts": board.facts, "trace": board.trace}
