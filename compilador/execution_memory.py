from typing import Dict, Tuple, Any, List, Optional
from semantics import TypeName, INT, FLOAT
from virtual_memory import (
    GLOBAL_INT_START, GLOBAL_FLOAT_START, GLOBAL_BOOL_START,
    LOCAL_INT_START, LOCAL_FLOAT_START, LOCAL_BOOL_START,
    TEMP_INT_START, TEMP_FLOAT_START, TEMP_BOOL_START,
    CONST_INT_START, CONST_FLOAT_START, CONST_STRING_START,
)


# Mapeo de tipos a sufijos de listas de almacenamiento y valores por defecto
TYPE_STORAGE_MAP = {
    "int": ("ints", 0),
    "float": ("floats", 0.0),
    "bool": ("bools", False),
    "string": ("strings", "")
}

class ActivationRecord:
    """
    Registro de activación (call frame) para una función.
    Almacena las variables locales y temporales de una llamada a función.
    """

    def __init__(self, function_name: str, local_base: int = None, temp_base: int = None):
        """
        Crea un nuevo activation record.

        Args:
            function_name: Nombre de la función
            local_base: Primera dirección virtual LOCAL de esta función (e.g., 4001)
            temp_base: Primera dirección virtual TEMP de esta función (e.g., 7000)
        """
        self.function_name = function_name
        self.local_base = local_base
        self.temp_base = temp_base

        # Almacenamiento real para esta función
        self.local_ints: List[int] = []
        self.local_floats: List[float] = []
        self.local_bools: List[bool] = []

        self.temp_ints: List[int] = []
        self.temp_floats: List[float] = []
        self.temp_bools: List[bool] = []

    def __repr__(self) -> str:
        return (
            f"ActivationRecord({self.function_name}, "
            f"locals={len(self.local_ints)}+{len(self.local_floats)}+{len(self.local_bools)}, "
            f"temps={len(self.temp_ints)}+{len(self.temp_floats)}+{len(self.temp_bools)})"
        )


class ExecutionMemory:
    """
    Administra la memoria de ejecución del programa Patito usando direcciones virtuales.
    """

    def __init__(self):
        """
        Inicializa todos los segmentos de memoria como listas vacías.
        Cada segmento se organiza por tipo de dato.
        """
        # Segmento GLOBAL
        self.global_ints: List[int] = []
        self.global_floats: List[float] = []
        self.global_bools: List[bool] = []

        # Segmento CONSTANT
        self.const_ints: List[int] = []
        self.const_floats: List[float] = []
        self.const_strings: List[str] = []

        # Call stack para manejo de activation records
        self.call_stack: List[ActivationRecord] = []
        self._initialize_main_frame()

        # Mapas auxiliares para tracking de tamaños asignados
        self._segment_sizes: Dict[str, int] = {
            "global_ints": 0,
            "global_floats": 0,
            "global_bools": 0,
            "const_ints": 0,
            "const_floats": 0,
            "const_strings": 0,
        }

    def _initialize_main_frame(self):
        """
        Inicializa el activation record para el programa principal.
        """
        main_frame = ActivationRecord("__main__")
        self.call_stack.append(main_frame)

    def decode_address(self, virtual_address: int) -> Tuple[str, str, int]:
        """
        Decodifica una dirección virtual en sus componentes.
        """
        # GLOBAL segment
        if GLOBAL_INT_START <= virtual_address < GLOBAL_FLOAT_START:
            return ("GLOBAL", "INT", virtual_address - GLOBAL_INT_START)
        elif GLOBAL_FLOAT_START <= virtual_address < GLOBAL_BOOL_START:
            return ("GLOBAL", "FLOAT", virtual_address - GLOBAL_FLOAT_START)
        elif GLOBAL_BOOL_START <= virtual_address < LOCAL_INT_START:
            return ("GLOBAL", "BOOL", virtual_address - GLOBAL_BOOL_START)

        # LOCAL segment
        elif LOCAL_INT_START <= virtual_address < LOCAL_FLOAT_START:
            return ("LOCAL", "INT", virtual_address - LOCAL_INT_START)
        elif LOCAL_FLOAT_START <= virtual_address < LOCAL_BOOL_START:
            return ("LOCAL", "FLOAT", virtual_address - LOCAL_FLOAT_START)
        elif LOCAL_BOOL_START <= virtual_address < TEMP_INT_START:
            return ("LOCAL", "BOOL", virtual_address - LOCAL_BOOL_START)

        # TEMP segment
        elif TEMP_INT_START <= virtual_address < TEMP_FLOAT_START:
            return ("TEMP", "INT", virtual_address - TEMP_INT_START)
        elif TEMP_FLOAT_START <= virtual_address < TEMP_BOOL_START:
            return ("TEMP", "FLOAT", virtual_address - TEMP_FLOAT_START)
        elif TEMP_BOOL_START <= virtual_address < CONST_INT_START:
            return ("TEMP", "BOOL", virtual_address - TEMP_BOOL_START)

        # CONSTANT segment
        elif CONST_INT_START <= virtual_address < CONST_FLOAT_START:
            return ("CONSTANT", "INT", virtual_address - CONST_INT_START)
        elif CONST_FLOAT_START <= virtual_address < CONST_STRING_START:
            return ("CONSTANT", "FLOAT", virtual_address - CONST_FLOAT_START)
        elif CONST_STRING_START <= virtual_address < CONST_STRING_START + 1000:
            return ("CONSTANT", "STRING", virtual_address - CONST_STRING_START)

        else:
            raise ValueError(
                f"Dirección virtual {virtual_address} fuera de los rangos válidos"
            )

    def _get_storage_list_and_adjusted_offset(self, segment: str, data_type: str, original_offset: int) -> tuple[List[Any], int]:
        """
        Regresa la lista de almacenamiento y el offset ajustado para el segmento y tipo dados.

        Para GLOBAL y CONSTANT: usa el offset directamente
        Para LOCAL y TEMP: ajusta el offset usando la dirección base del frame actual
        """
        segment_lower = segment.lower()
        type_lower = data_type.lower()

        if type_lower not in TYPE_STORAGE_MAP:
            raise ValueError(f"Tipo de dato inválido: {data_type}")

        type_suffix = TYPE_STORAGE_MAP[type_lower][0]

        # GLOBAL: acceso directo
        if segment_lower == "global":
            storage_attr = f"global_{type_suffix}"
            return (getattr(self, storage_attr), original_offset)

        # CONSTANT: acceso directo
        if segment_lower == "constant":
            storage_attr = f"const_{type_suffix}"
            return (getattr(self, storage_attr), original_offset)

        # LOCAL y TEMP: requieren frame actual y ajuste de offset
        if segment_lower in ("local", "temp"):
            if not self.call_stack:
                raise RuntimeError("No hay activation record en el call stack")

            current_frame = self.call_stack[-1]

            # Obtener la lista de almacenamiento del frame
            storage_attr = f"{segment_lower}_{type_suffix}"
            storage_list = getattr(current_frame, storage_attr)

            # Ajustar offset usando la base del frame
            base_virtual_addr = current_frame.local_base if segment_lower == "local" else current_frame.temp_base

            if base_virtual_addr is None:
                adjusted_offset = original_offset
            else:
                # Convertir base de virtual address a offset desde el inicio del segmento
                segment_start = LOCAL_INT_START if segment_lower == "local" else TEMP_INT_START
                base_offset = base_virtual_addr - segment_start
                adjusted_offset = original_offset - base_offset

            return (storage_list, adjusted_offset)

        raise ValueError(f"Segmento inválido: {segment}")

    def _ensure_capacity(self, storage_list: List[Any], offset: int, default_value: Any = 0):
        """
        Asegura que la lista tenga capacidad suficiente para el índice dado.
        Expande la lista con valores por defecto si es necesario.
        """
        while len(storage_list) <= offset:
            storage_list.append(default_value)

    def read(self, virtual_address: int) -> Any:
        """
        Lee un valor de memoria usando una dirección virtual.
        """
        segment, data_type, offset = self.decode_address(virtual_address)
        storage_list, adjusted_offset = self._get_storage_list_and_adjusted_offset(segment, data_type, offset)

        if adjusted_offset < 0 or adjusted_offset >= len(storage_list):
            frame_info = ""
            if segment in ("LOCAL", "TEMP") and self.call_stack:
                frame = self.call_stack[-1]
                frame_info = f" (frame={frame.function_name}, local_base={frame.local_base}, temp_base={frame.temp_base})"

            raise IndexError(
                f"Intento de leer dirección {virtual_address} ({segment} {data_type} offset {offset}, adjusted {adjusted_offset}) "
                f"que no ha sido inicializada. Tamaño actual: {len(storage_list)}{frame_info}"
            )

        return storage_list[adjusted_offset]

    def write(self, virtual_address: int, value: Any) -> None:
        """
        Escribe un valor en memoria usando una dirección virtual.
        Expande automáticamente el almacenamiento si es necesario.
        """
        segment, data_type, offset = self.decode_address(virtual_address)
        storage_list, adjusted_offset = self._get_storage_list_and_adjusted_offset(segment, data_type, offset)

        # Obtener el valor por defecto del mapeo de tipos
        type_lower = data_type.lower()
        default_value = TYPE_STORAGE_MAP.get(type_lower, (None, None))[1]

        self._ensure_capacity(storage_list, adjusted_offset, default_value)

        storage_list[adjusted_offset] = value

    def load_constants(self, constant_table) -> None:
        """
        Carga la tabla de constantes en el segmento CONSTANT de la memoria.
        Debe llamarse antes de ejecutar el programa.
        """
        # Si constant_table es un objeto ConstantTable, acceder a su tabla interna
        table_dict = constant_table._table if hasattr(constant_table, '_table') else constant_table

        for (literal_value, const_type), virtual_address in table_dict.items():
            # Convierte el literal string al tipo apropiado
            if const_type == INT:
                value = int(literal_value)
            elif const_type == FLOAT:
                value = float(literal_value)
            else:
                # STRING u otro tipo: se guarda tal cual
                value = literal_value.strip('"')  # Remueve comillas si es string

            # Escribe en la dirección correspondiente
            self.write(virtual_address, value)

    def prepare_frame(self, function_name: str, local_base_address: int = 0, temp_base_address: int = 0) -> ActivationRecord:
        """
        Crea un nuevo activation record para una función, pero no lo activa todavía.
        Este método es llamado por ERA.

        Args:
            function_name: Nombre de la función para la cual crear el frame
            local_base_address: Dirección base LOCAL para esta función
            temp_base_address: Dirección base TEMP para esta función

        Returns:
            El nuevo ActivationRecord creado (aún no está en el call stack)
        """
        return ActivationRecord(function_name, local_base_address, temp_base_address)

    def push_frame(self, frame: ActivationRecord) -> None:
        """
        Activa un activation record poniéndolo en el tope del call stack.
        Este método es llamado por GOSUB.

        Args:
            frame: El ActivationRecord a activar
        """
        self.call_stack.append(frame)

    def pop_frame(self) -> ActivationRecord:
        """
        Remueve y regresa el activation record del tope del call stack.
        Este método es llamado por ENDFUNC o RETURN.

        Returns:
            El ActivationRecord que fue removido

        Raises:
            RuntimeError: Si se intenta hacer pop del frame principal
        """
        if len(self.call_stack) <= 1:
            raise RuntimeError("No se puede hacer pop del frame principal del programa")
        return self.call_stack.pop()

    def current_frame(self) -> ActivationRecord:
        """
        Regresa el activation record actual sin removerlo del stack.

        Returns:
            El ActivationRecord en el tope del call stack
        """
        if not self.call_stack:
            raise RuntimeError("No hay activation record en el call stack")
        return self.call_stack[-1]

    def reset_locals(self) -> None:
        """
        Limpia el segmento LOCAL del frame actual.
        """
        if self.call_stack:
            frame = self.call_stack[-1]
            frame.local_ints.clear()
            frame.local_floats.clear()
            frame.local_bools.clear()

    def reset_temps(self) -> None:
        """
        Limpia el segmento TEMPORARY del frame actual.
        """
        if self.call_stack:
            frame = self.call_stack[-1]
            frame.temp_ints.clear()
            frame.temp_floats.clear()
            frame.temp_bools.clear()

    def __repr__(self) -> str:
        """Representación string para debugging"""
        current = self.call_stack[-1] if self.call_stack else None
        frame_info = f" (current: {current.function_name})" if current else ""
        return (
            f"ExecutionMemory(\n"
            f"  globals: {len(self.global_ints)} ints, {len(self.global_floats)} floats, "
            f"{len(self.global_bools)} bools\n"
            f"  call_stack_depth: {len(self.call_stack)}{frame_info}\n"
            f"  constants: {len(self.const_ints)} ints, {len(self.const_floats)} floats, "
            f"{len(self.const_strings)} strings\n"
            f")"
        )
