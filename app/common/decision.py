"""Blackboard primitives. Each engine owns a fresh board for each request."""
from dataclasses import dataclass, field
from decimal import Decimal
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


@dataclass(frozen=True)
class Criterion:
    """One TOPSIS criterion. benefit=True: larger is better; False: smaller is better."""
    key: str
    label: str
    weight: Decimal
    benefit: bool = True


def topsis(alternatives, criteria):
    """TOPSIS (Hwang & Yoon, 1981): closeness to the ideal solution in [0, 1].

    alternatives: list of dicts holding a Decimal value for each criterion key.
    Returns one closeness value per alternative, in the same order.
    Vector normalisation, weights rescaled to sum to 1. Zero-weight criteria are ignored.
    """
    total = sum((c.weight for c in criteria), Decimal(0))
    if total <= 0:
        raise ValueError('at least one criterion needs a positive weight')
    weighted = [dict() for _ in alternatives]
    ideal, anti = {}, {}
    for c in criteria:
        if c.weight == 0:
            continue
        norm = sum((a[c.key] ** 2 for a in alternatives), Decimal(0)).sqrt()
        column = [(a[c.key] / norm if norm else Decimal(0)) * c.weight / total for a in alternatives]
        for row, value in zip(weighted, column):
            row[c.key] = value
        ideal[c.key] = max(column) if c.benefit else min(column)
        anti[c.key] = min(column) if c.benefit else max(column)
    closeness = []
    for row in weighted:
        best = sum(((row[k] - ideal[k]) ** 2 for k in ideal), Decimal(0)).sqrt()
        worst = sum(((row[k] - anti[k]) ** 2 for k in anti), Decimal(0)).sqrt()
        # Identical alternatives are equally close to both reference points.
        closeness.append(worst / (best + worst) if best + worst else Decimal('0.5'))
    return closeness
