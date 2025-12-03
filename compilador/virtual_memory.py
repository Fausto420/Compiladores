from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional

from semantics import (
    FunctionDirectory,
    VariableInfo,
    TypeName,
    INT,
    FLOAT,
    BOOL,
)

# Rangos de direcciones virtuales
GLOBAL_INT_START = 1000
GLOBAL_FLOAT_START = 2000
GLOBAL_BOOL_START = 3000

LOCAL_INT_START = 4000
LOCAL_FLOAT_START = 5000
LOCAL_BOOL_START = 6000

TEMP_INT_START = 7000
TEMP_FLOAT_START = 8000
TEMP_BOOL_START = 9000

CONST_INT_START = 10000
CONST_FLOAT_START = 11000
CONST_STRING_START = 12000


@dataclass
class MemoryCounters:
    global_int: int = GLOBAL_INT_START
    global_float: int = GLOBAL_FLOAT_START
    global_bool: int = GLOBAL_BOOL_START

    local_int: int = LOCAL_INT_START
    local_float: int = LOCAL_FLOAT_START
    local_bool: int = LOCAL_BOOL_START

    temp_int: int = TEMP_INT_START
    temp_float: int = TEMP_FLOAT_START
    temp_bool: int = TEMP_BOOL_START

    const_int: int = CONST_INT_START
    const_float: int = CONST_FLOAT_START
    const_string: int = CONST_STRING_START


@dataclass
class ConstantTable:
    """
    Tabla de constantes: (valor como cadena, tipo) -> dirección virtual.
    """
    _table: Dict[Tuple[str, TypeName], int] = field(default_factory=dict)

    def get_or_create(self,literal_value: str, const_type: TypeName, counters: MemoryCounters,) -> int:
        """
        Regresa la dirección asociada al literal. Si no existe, la crea.
        """
        key = (literal_value, const_type)
        if key in self._table:
            return self._table[key]

        # Asigar una nueva dirección según el tipo de constante
        if const_type == INT:
            address = counters.const_int
            counters.const_int += 1
        elif const_type == FLOAT:
            address = counters.const_float
            counters.const_float += 1
        else:
            # Cualquier otro tipo de constante va al segmento de strings
            address = counters.const_string
            counters.const_string += 1

        self._table[key] = address
        return address
    
    # Se usa para imprimir la tabla de constantes
    def to_dict(self) -> Dict[Tuple[str, TypeName], int]:
        return dict(self._table)


@dataclass
class VirtualMemory:
    counters: MemoryCounters = field(default_factory=MemoryCounters)
    constant_table: ConstantTable = field(default_factory=ConstantTable)

    # Asignación de variables
    def _allocate_from_segment(self, segment_name: str) -> int:
        """
        Helper interno: toma el valor actual del segmento, lo regresa y avanza el contador
        """
        value = getattr(self.counters, segment_name)
        setattr(self.counters, segment_name, value + 1)
        return value

    def allocate_global(self, variable_type: TypeName) -> int:
        """
        Asigna una dirección virtual para una variable GLOBAL según su tipo.
        """
        if variable_type == INT:
            return self._allocate_from_segment("global_int")
        if variable_type == FLOAT:
            return self._allocate_from_segment("global_float")
        if variable_type == BOOL:
            return self._allocate_from_segment("global_bool")
        raise ValueError(f"Tipo no soportado para variable global: {variable_type}")

    def allocate_local(self, variable_type: TypeName) -> int:
        """
        Asigna una dirección virtual para una variable LOCAL según su tipo.
        """
        if variable_type == INT:
            return self._allocate_from_segment("local_int")
        if variable_type == FLOAT:
            return self._allocate_from_segment("local_float")
        if variable_type == BOOL:
            return self._allocate_from_segment("local_bool")
        raise ValueError(f"Tipo no soportado para variable local: {variable_type}")

    def allocate_temporary(self, temp_type: TypeName) -> int:
        """
        Asigna una dirección virtual para un TEMPORAL según su tipo.
        """
        if temp_type == INT:
            return self._allocate_from_segment("temp_int")
        if temp_type == FLOAT:
            return self._allocate_from_segment("temp_float")
        if temp_type == BOOL:
            return self._allocate_from_segment("temp_bool")
        raise ValueError(f"Tipo no soportado para temporal: {temp_type}")

    # Asignación de constantes
    def allocate_constant(self, literal_value: str, const_type: TypeName) -> int:
        """
        Regresa la dirección virtual asociada al literal (creándola si hace falta).
        """
        return self.constant_table.get_or_create(literal_value, const_type, self.counters)

# Asignación de direcciones a variables ya declaradas en FunctionDirectory
def assign_variable_addresses( function_directory: FunctionDirectory, virtual_memory: VirtualMemory,) -> None:
    """
    Recorre el FunctionDirectory y asigna direcciones virtuales a todas las
    variables globales y locales (incluyendo parámetros).
    """

    # 1) Variables globales
    for variable_info in function_directory.global_variables.variables.values():
        if variable_info.virtual_address is None:
            variable_info.virtual_address = virtual_memory.allocate_global(variable_info.var_type)

    # 2) Variables y parámetros de cada función
    for function_info in function_directory.functions.values():
        # Primero todas las variables locales (incluye parámetros)
        for variable_info in function_info.local_variables.variables.values():
            if variable_info.virtual_address is None:
                variable_info.virtual_address = virtual_memory.allocate_local(variable_info.var_type)

        # Sincronizar los objetos de parameter_list con los de local_variables
        for parameter in function_info.parameter_list:
            local_copy: Optional[VariableInfo] = function_info.local_variables.variables.get(parameter.name)
            if local_copy is not None:
                parameter.virtual_address = local_copy.virtual_address
