from typing import List, Optional, Any
from intermediate_code_structures import Quadruple
from execution_memory import ExecutionMemory, ActivationRecord

class VirtualMachine:
    """
    Máquina Virtual para ejecutar código intermedio (cuádruplos) del compilador Patito.
    """

    def __init__(self, quadruples: List[Quadruple], memory: ExecutionMemory, function_directory: Any = None):
        """
        Inicializa la Máquina Virtual.
        Args:
            quadruples: Lista de cuádruplos a ejecutar
            memory: Memoria de ejecución
            function_directory: Directorio de funciones para obtener información de direcciones
        """
        self.quadruples: List[Quadruple] = quadruples
        self.memory: ExecutionMemory = memory
        self.function_directory = function_directory

        # Instruction Pointer: índice del cuádruplo actual
        self.ip: int = 0

        # Lista para acumular las salidas de PRINT (para testing)
        self.output: List[str] = []

        # Flag para detener la ejecución
        self.halted: bool = False

        # Stack para direcciones de retorno (return addresses)
        self.return_address_stack: List[int] = []

        # Frame pendiente preparado por ERA, esperando ser activado por GOSUB
        self.pending_frame: Optional[ActivationRecord] = None

    def run(self) -> None:
        """
        Ejecuta el programa completo desde el cuádruplo 0 hasta el final.
        Se detiene cuando ip alcanza el final de la lista de cuádruplos
        o cuando se ejecuta un HALT/END.
        """
        self.ip = 0
        self.halted = False
        self.output.clear()

        while self.ip < len(self.quadruples) and not self.halted:
            self.execute_quadruple(self.quadruples[self.ip])

    def execute_quadruple(self, quad: Quadruple) -> None:
        """
        Ejecuta un solo cuádruplo y avanza el instruction pointer.
        """
        operator = quad.operator

        # Operaciones aritméticas
        if operator in ("MAS", "MENOS", "POR", "ENTRE"):
            self._execute_arithmetic(quad)

        # Operaciones relacionales
        elif operator in ("MAYOR", "MENOR", "IGUAL", "DIFERENTE"):
            self._execute_relational(quad)

        # Asignación
        elif operator == "ASSIGN":
            self._execute_assign(quad)

        # Impresión
        elif operator == "PRINT":
            self._execute_print(quad)

        # Control de flujo
        elif operator == "GOTO":
            self._execute_goto(quad)
        elif operator == "GOTOF":
            self._execute_gotof(quad)

        # Operadores unarios
        elif operator == "UMINUS":
            self._execute_uminus(quad)

        # Marcadores de función
        elif operator == "BEGINFUNC":
            self._execute_beginfunc(quad)
        elif operator == "ENDFUNC":
            self._execute_endfunc(quad)

        # Llamadas a función
        elif operator == "ERA":
            self._execute_era(quad)
        elif operator == "PARAM":
            self._execute_param(quad)
        elif operator == "GOSUB":
            self._execute_gosub(quad)

        else:
            raise ValueError(f"Operador no soportado: {operator}")

    def _execute_arithmetic(self, quad: Quadruple) -> None:
        """
        Ejecuta operaciones aritméticas: +, -, *, /
        """
        left_value = self.memory.read(quad.left_operand)
        right_value = self.memory.read(quad.right_operand)

        if quad.operator == "MAS":
            result = left_value + right_value
        elif quad.operator == "MENOS":
            result = left_value - right_value
        elif quad.operator == "POR":
            result = left_value * right_value
        elif quad.operator == "ENTRE":
            if right_value == 0:
                raise ZeroDivisionError("División entre cero")
            result = left_value / right_value
        else:
            raise ValueError(f"Operador aritmético no reconocido: {quad.operator}")

        self.memory.write(quad.result, result)
        self.ip += 1

    def _execute_relational(self, quad: Quadruple) -> None:
        """
        Ejecuta operaciones relacionales: >, <, ==, !=
        """
        left_value = self.memory.read(quad.left_operand)
        right_value = self.memory.read(quad.right_operand)

        if quad.operator == "MAYOR":
            result = left_value > right_value
        elif quad.operator == "MENOR":
            result = left_value < right_value
        elif quad.operator == "IGUAL":
            result = left_value == right_value
        elif quad.operator == "DIFERENTE":
            result = left_value != right_value
        else:
            raise ValueError(f"Operador relacional no reconocido: {quad.operator}")

        # Guarda el resultado como entero (1 o 0) para compatibilidad
        self.memory.write(quad.result, 1 if result else 0)
        self.ip += 1

    def _execute_assign(self, quad: Quadruple) -> None:
        """
        Ejecuta asignación: variable = expresion
        """
        value = self.memory.read(quad.left_operand)
        self.memory.write(quad.result, value)
        self.ip += 1

    def _execute_print(self, quad: Quadruple) -> None:
        """
        Ejecuta impresión de un valor.
        """
        value = self.memory.read(quad.left_operand)

        # Convierte el valor a string apropiadamente
        if isinstance(value, float):
            output_str = str(value)
        elif isinstance(value, bool) or (isinstance(value, int) and value in (0, 1)):
            # Si es booleano, lo imprime como tal
            output_str = str(value)
        else:
            output_str = str(value)

        # Imprime en consola y guarda en output para testing
        print(output_str)
        self.output.append(output_str)
        self.ip += 1

    def _execute_goto(self, quad: Quadruple) -> None:
        """
        Ejecuta salto incondicional.
        """
        self.ip = quad.result

    def _execute_gotof(self, quad: Quadruple) -> None:
        """
        Ejecuta salto condicional (si falso).
        """
        condition = self.memory.read(quad.left_operand)

        # Considera 0, 0.0, False como falso
        if not condition:
            self.ip = quad.result
        else:
            self.ip += 1

    def _execute_uminus(self, quad: Quadruple) -> None:
        """
        Ejecuta negación unaria.
        """
        value = self.memory.read(quad.left_operand)
        self.memory.write(quad.result, -value)
        self.ip += 1

    def _execute_beginfunc(self, quad: Quadruple) -> None:
        """
        Marca el inicio de una función.

        Si llega aquí vía GOSUB, el frame ya está activo y simplemente avanza.
        Si llega aquí por ejecución secuencial (al inicio del programa), debe
        saltar al ENDFUNC correspondiente para evitar ejecutar la función sin llamarla.

        Formato esperado: (BEGINFUNC, function_name, None, None)
        """
        # Si el call stack tiene más de 1 frame, significa que estamos dentro de una llamada
        if len(self.memory.call_stack) > 1:
            # Estamos dentro de una función llamada por GOSUB, avanzar normalmente
            self.ip += 1
        else:
            # Estamos en ejecución secuencial, saltar al ENDFUNC correspondiente
            function_name = quad.left_operand
            # Buscar el ENDFUNC correspondiente
            depth = 1
            next_ip = self.ip + 1
            while next_ip < len(self.quadruples) and depth > 0:
                next_quad = self.quadruples[next_ip]
                if next_quad.operator == "BEGINFUNC":
                    depth += 1
                elif next_quad.operator == "ENDFUNC" and next_quad.left_operand == function_name:
                    depth -= 1
                    if depth == 0:
                        # Saltar justo después del ENDFUNC
                        self.ip = next_ip + 1
                        return
                next_ip += 1

            raise RuntimeError(f"No se encontró ENDFUNC para función '{function_name}'")

    def _execute_endfunc(self, quad: Quadruple) -> None:
        """
        Marca el final de una función.
        Limpia el activation record y retorna al caller.
        """
        # Pop el activation record actual
        self.memory.pop_frame()

        # Pop la dirección de retorno y saltar de vuelta
        if not self.return_address_stack:
            # Si no hay dirección de retorno, es el final del programa
            self.halted = True
        else:
            return_address = self.return_address_stack.pop()
            self.ip = return_address

    def _compute_function_base_addresses(self, function_name: str) -> tuple[int, int]:
        """
        Calcula las direcciones base LOCAL y TEMP para una función.

        Retorna la primera dirección virtual LOCAL usada por la función
        (o 0 si no hay variables locales).
        """
        from virtual_memory import LOCAL_INT_START, TEMP_INT_START

        # Sin function_directory, usar 0 como base
        if not self.function_directory:
            return (0, 0)

        try:
            function_info = self.function_directory.get_function(function_name)

            # Encontrar la dirección LOCAL mínima
            local_addresses = [
                var.virtual_address
                for var in function_info.local_variables.variables.values()
                if hasattr(var, 'virtual_address')
                and var.virtual_address is not None
                and LOCAL_INT_START <= var.virtual_address < TEMP_INT_START
            ]

            local_base = min(local_addresses) if local_addresses else 0
            temp_base = 0  # Las temporales siempre empiezan en 0

            return (local_base, temp_base)

        except Exception:
            return (0, 0)

    def _execute_era(self, quad: Quadruple) -> None:
        """
        Prepara un activation record para llamada a función.
        Crea un nuevo frame pero NO lo activa todavía.
        """
        function_name = quad.left_operand

        # Calcular direcciones base para esta función
        local_base, temp_base = self._compute_function_base_addresses(function_name)

        # Crea un nuevo activation record para la función con las direcciones base
        self.pending_frame = self.memory.prepare_frame(function_name, local_base, temp_base)

        self.ip += 1

    def _execute_param(self, quad: Quadruple) -> None:
        """
        Pasa un parámetro a la función que se va a llamar.
        Copia el valor del argumento al slot de parámetro en el pending frame.
        """
        if self.pending_frame is None:
            raise RuntimeError("PARAM ejecutado sin un ERA previo")

        arg_address = quad.left_operand
        param_position = quad.result  # 1-based position

        # Lee el valor del argumento desde el contexto del caller
        arg_value = self.memory.read(arg_address)

        # Determinar el tipo del argumento basado en su dirección
        _, data_type, _ = self.memory.decode_address(arg_address)

        # Los parámetros se almacenan como variables locales en el frame
        param_offset = param_position - 1  # Convertir a 0-based

        # Escribir directamente en las listas de almacenamiento del pending frame
        if data_type == "INT":
            storage_list = self.pending_frame.local_ints
        elif data_type == "FLOAT":
            storage_list = self.pending_frame.local_floats
        elif data_type == "BOOL":
            storage_list = self.pending_frame.local_bools
        else:
            raise ValueError(f"Tipo de parámetro no soportado: {data_type}")

        # Asegurar capacidad en la lista
        while len(storage_list) <= param_offset:
            storage_list.append(0 if data_type == "INT" else (0.0 if data_type == "FLOAT" else False))

        # Escribir el valor del parámetro
        storage_list[param_offset] = arg_value

        self.ip += 1

    def _execute_gosub(self, quad: Quadruple) -> None:
        """
        Llama a una función.
        Activa el pending frame, guarda la dirección de retorno, y salta a la función.
        """
        if self.pending_frame is None:
            raise RuntimeError("GOSUB ejecutado sin un ERA previo")

        target_quad_index = quad.result

        # Guardar la dirección de retorno (siguiente cuádruplo después de GOSUB)
        return_address = self.ip + 1
        self.return_address_stack.append(return_address)

        # Activar el pending frame (push al call stack)
        self.memory.push_frame(self.pending_frame)
        self.pending_frame = None  # Limpiar pending frame

        # Saltar al inicio de la función
        self.ip = target_quad_index

    def get_output(self) -> List[str]:
        """
        Regresa la lista de strings que fueron impresos con PRINT.
        Útil para testing.
        """
        return self.output.copy()

    def __repr__(self) -> str:
        """Representación string para debugging"""
        return (
            f"VirtualMachine(\n"
            f"  quadruples: {len(self.quadruples)}\n"
            f"  ip: {self.ip}\n"
            f"  halted: {self.halted}\n"
            f"  output_lines: {len(self.output)}\n"
            f")"
        )
