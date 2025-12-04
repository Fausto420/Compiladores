import sys
from pathlib import Path
from lark.exceptions import UnexpectedInput

# Import compiler components
from parse_and_scan import parse
from builder import build_symbol_tables
from semantics import SemanticError
from quadruple_pipeline import generate_quadruples
from virtual_memory import VirtualMemory
from execution_memory import ExecutionMemory
from virtual_machine import VirtualMachine
from intermediate_code_structures import IntermediateCodeContext


class CompilationError(Exception):
    """Base class for all compilation errors"""
    pass


class SyntaxError(CompilationError):
    """Raised when there's a syntax error in the source code"""
    pass


class PatitoCompiler:
    """
    Main Patito Compiler class.
    """

    def __init__(self, verbose: bool = False):
        """
        Initialize the compiler.

        Args:
            verbose: If True, print detailed compilation information
        """
        self.verbose = verbose
        self.source_code = ""
        self.parse_tree = None
        self.function_directory = None
        self.virtual_memory = None
        self.context = None
        self.quadruples = None

    def log(self, message: str, level: str = "INFO"):
        """Print log message if verbose mode is enabled."""
        if self.verbose:
            print(f"[{level}] {message}")

    def compile_file(self, file_path: str) -> bool:
        """
        Compile a Patito source file.

        Args:
            file_path: Path to the .patito source file

        Returns:
            True if compilation succeeds, False otherwise

        Raises:
            CompilationError: With detailed error message if compilation fails
        """
        # Step 0: Read source file
        try:
            source_path = Path(file_path)
            if not source_path.exists():
                raise CompilationError(f"❌ Archivo no encontrado: {file_path}")

            if not source_path.suffix == '.patito':
                print(f"⚠️  Advertencia: El archivo no tiene extensión .patito")

            self.source_code = source_path.read_text(encoding='utf-8')
            self.log(f"Código fuente cargado: {len(self.source_code)} caracteres")

        except UnicodeDecodeError as e:
            raise CompilationError(f"❌ Error de codificación: El archivo debe estar en UTF-8\n{e}")
        except Exception as e:
            raise CompilationError(f"❌ Error al leer archivo: {e}")

        # Step 1: Lexical and Syntax Analysis
        try:
            self.log("Fase 1: Análisis léxico y sintáctico...")
            self.parse_tree = parse(self.source_code)
            self.log("✓ Análisis sintáctico completado exitosamente")

        except UnexpectedInput as e:
            error_msg = self._format_syntax_error(e)
            raise CompilationError(f"❌ ERROR DE SINTAXIS:\n{error_msg}")
        except Exception as e:
            raise CompilationError(f"❌ Error inesperado durante el análisis sintáctico:\n{e}")

        # Step 2: Semantic Analysis
        try:
            self.log("Fase 2: Análisis semántico...")
            self.function_directory = build_symbol_tables(parse, self.source_code)
            self.log(f"✓ Directorio de funciones construido")
            self.log(f"  - Variables globales: {len(self.function_directory.global_variables.variables)}")
            self.log(f"  - Funciones declaradas: {len(self.function_directory.functions)}")

        except SemanticError as e:
            raise CompilationError(f"❌ ERROR SEMÁNTICO:\n{e}")
        except Exception as e:
            raise CompilationError(f"❌ Error inesperado durante el análisis semántico:\n{e}")

        # Step 3: Intermediate Code Generation
        try:
            self.log("Fase 3: Generación de código intermedio...")
            self.context = generate_quadruples(self.source_code)
            self.quadruples = list(self.context.quadruples)
            self.log(f"✓ Código intermedio generado")
            self.log(f"  - Cuádruplos generados: {len(self.quadruples)}")

        except SemanticError as e:
            raise CompilationError(f"❌ ERROR SEMÁNTICO EN GENERACIÓN DE CÓDIGO:\n{e}")
        except Exception as e:
            raise CompilationError(f"❌ Error durante la generación de código intermedio:\n{e}")

        print(f"✅ COMPILACIÓN EXITOSA")
        print(f"   Archivo: {file_path}")
        print(f"   Cuádruplos generados: {len(self.quadruples)}")

        return True

    def run(self) -> bool:
        """
        Execute the compiled program using the virtual machine.

        Returns:
            True if execution succeeds, False otherwise
        """
        if self.quadruples is None:
            print("❌ Error: El programa debe ser compilado antes de ejecutarse")
            return False

        try:
            self.log("\nFase 4: Ejecución en máquina virtual...")

            # Create execution memory and load constants
            memory = ExecutionMemory()

            # Recreate compilation to get virtual memory with constants
            from virtual_memory import VirtualMemory, assign_variable_addresses
            from expression_to_quads import ExpressionQuadrupleGenerator

            vm_memory = VirtualMemory()
            assign_variable_addresses(self.function_directory, vm_memory)

            # Generate code again to populate constant table
            context_temp = IntermediateCodeContext()
            generator = ExpressionQuadrupleGenerator(
                function_directory=self.function_directory,
                context=context_temp,
                virtual_memory=vm_memory
            )
            generator.generate_program(self.parse_tree)

            # Load constants from virtual memory
            memory.load_constants(vm_memory.constant_table)

            # Create and run virtual machine
            vm = VirtualMachine(self.quadruples, memory, self.function_directory)

            print("\n" + "="*50)
            print("SALIDA DEL PROGRAMA:")
            print("="*50)

            vm.run()

            print("="*50)
            self.log(f"✓ Ejecución completada exitosamente")

            return True

        except Exception as e:
            print(f"\n❌ ERROR EN TIEMPO DE EJECUCIÓN:")
            print(f"{e}")
            import traceback
            if self.verbose:
                traceback.print_exc()
            return False

    def _format_syntax_error(self, error: UnexpectedInput) -> str:
        """Format syntax error with helpful context."""
        lines = self.source_code.split('\n')
        error_line = error.line if hasattr(error, 'line') else 1
        error_column = error.column if hasattr(error, 'column') else 1

        msg = f"Error en línea {error_line}, columna {error_column}\n\n"

        # Show the problematic line
        if error_line <= len(lines):
            line = lines[error_line - 1]
            msg += f"  {error_line} | {line}\n"
            msg += f"      | {' ' * (error_column - 1)}^\n\n"

        msg += f"Descripción: {str(error)}\n"

        # Helpful hints
        if "PUNTO_COMA" in str(error):
            msg += "\n💡 Sugerencia: ¿Olvidaste un punto y coma (;)?"
        elif "LLAVE_DER" in str(error):
            msg += "\n💡 Sugerencia: ¿Falta una llave de cierre (}})?"
        elif "PAREN_DER" in str(error):
            msg += "\n💡 Sugerencia: ¿Falta un paréntesis de cierre ())?"

        return msg

    def show_quadruples(self):
        """Display generated quadruples."""
        if self.quadruples is None:
            print("❌ No hay cuádruplos para mostrar. Compila primero.")
            return

        print("\n" + "="*50)
        print("CUÁDRUPLOS GENERADOS:")
        print("="*50)

        for i, quad in enumerate(self.quadruples):
            print(f"{i:4d}: {quad}")

        print("="*50)


def main():
    """Main entry point for the compiler."""

    # Parse command line arguments
    if len(sys.argv) < 2:
        print("="*60)
        print("COMPILADOR PATITO")
        print("="*60)
        print("\nUso:")
        print(f"  {sys.argv[0]} <archivo.patito>")
        print(f"  {sys.argv[0]} <archivo.patito> --run")
        print(f"  {sys.argv[0]} <archivo.patito> --verbose")
        print(f"  {sys.argv[0]} <archivo.patito> --run --verbose")
        print(f"  {sys.argv[0]} <archivo.patito> --show-quads")
        print("\nOpciones:")
        print("  --run         Ejecuta el programa después de compilar")
        print("  --verbose     Muestra información detallada de compilación")
        print("  --show-quads  Muestra los cuádruplos generados")
        print("\nEjemplos:")
        print(f"  {sys.argv[0]} examples/demo.patito")
        print(f"  {sys.argv[0]} mi_programa.patito --run")
        print(f"  {sys.argv[0]} test.patito --run --verbose --show-quads")
        print("="*60)
        sys.exit(1)

    file_path = sys.argv[1]
    should_run = '--run' in sys.argv
    verbose = '--verbose' in sys.argv
    show_quads = '--show-quads' in sys.argv

    # Create compiler instance
    compiler = PatitoCompiler(verbose=verbose)

    # Compile the file
    try:
        success = compiler.compile_file(file_path)

        if not success:
            sys.exit(1)

        # Show quadruples if requested
        if show_quads:
            compiler.show_quadruples()

        # Run if requested
        if should_run:
            success = compiler.run()
            if not success:
                sys.exit(1)
        else:
            print("\n💡 Usa --run para ejecutar el programa")

        sys.exit(0)

    except CompilationError as e:
        print(f"\n{e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Compilación interrumpida por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO:")
        print(f"{e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
