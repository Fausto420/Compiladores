from dataclasses import dataclass, field
from typing import Any, List, Optional
from semantics import TypeName


@dataclass
class Quadruple:
    """
    Representa un cuádruplo de la forma: (operador, operando_izq, operando_der, resultado)
    """
    operator: str
    left_operand: Optional[Any]
    right_operand: Optional[Any]
    result: Optional[Any]

    def __str__(self) -> str:
        """
        Regresa una representación amigable del cuádruplo.
        """
        return f"({self.operator}, {self.left_operand}, {self.right_operand}, {self.result})"


class Stack:
    """
    Implementación sencilla de una pila usando una lista de Python.
    Se usa para pila de operandos, pila de operadores y pila de tipos.
    Solo necesita operaciones básicas como push, pop, peek, is_empty.
    """

    def __init__(self, name: str = "stack") -> None:
        # name solo se usa para mensajes de error más claros.
        self.name: str = name
        # Lista interna donde se guardan los elementos de la pila.
        self._items: List[Any] = []

    def push(self, value: Any) -> None:
        self._items.append(value)

    def pop(self) -> Any:
        if not self._items:
            raise IndexError(f"No se puede hacer pop() en la pila vacía '{self.name}'")
        return self._items.pop()

    def peek(self) -> Optional[Any]:
        if not self._items:
            return None
        return self._items[-1]

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"{self.name}: {self._items}"


class QuadrupleQueue:
    """
    Representa la fila de cuádruplos.
    Internamente es una lista, pero expone métodos con nombres
    que reflejan su uso como cola: se agregan al final en orden de generación.
    """

    def __init__(self) -> None:
        # Lista de cuádruplos en el orden en que se van generando.
        self._items: List[Quadruple] = []

    def enqueue(self, quad: Quadruple) -> int:
        self._items.append(quad)
        return len(self._items) - 1

    def get(self, index: int) -> Quadruple:
        return self._items[index]

    def update_result(self, index: int, new_result: Any) -> None:
        self._items[index].result = new_result

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def pretty_print(self) -> None:
        for index, quad in enumerate(self._items):
            print(f"{index}: {quad}")


@dataclass
class IntermediateCodeContext:
    """
    Agrupa todas las estructuras de datos necesarias para generar el código intermedio de un programa.

    - operator_stack: PILA de operadores (PLUS, MINUS, ASSIGN, etc.).
    - operand_stack: PILA de operandos (direcciones virtuales de variables, temporales, constantes).
    - type_stack: PILA de tipos para cada operando (INT, FLOAT, BOOL).
    - quadruples: FILA de cuádruplos generados.
    """
    operator_stack: Stack = field(default_factory=lambda: Stack("OPERATORS"))
    operand_stack: Stack = field(default_factory=lambda: Stack("OPERANDS"))
    type_stack: Stack = field(default_factory=lambda: Stack("TYPES"))
    quadruples: QuadrupleQueue = field(default_factory=QuadrupleQueue)

    def push_operand(self, operand: Any, operand_type: TypeName) -> None:
        """
        Inserta un operando junto con su tipo en las pilas correspondientes.
        """
        self.operand_stack.push(operand)
        self.type_stack.push(operand_type)

    def push_operator(self, operator: str) -> None:
        """
        Inserta un operador en la pila de operadores.
        """
        self.operator_stack.push(operator)
