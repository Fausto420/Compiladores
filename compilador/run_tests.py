import sys
from pathlib import Path
from typing import List, Tuple
from patito_compiler import PatitoCompiler, CompilationError


class TestResult:
    """Stores the result of a single test case."""

    def __init__(self, name: str, passed: bool, message: str = ""):
        self.name = name
        self.passed = passed
        self.message = message

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        msg = f"  {self.message}" if self.message else ""
        return f"{status} - {self.name}{msg}"


class TestRunner:
    """Runs all test cases and generates a report."""

    def __init__(self, test_dir: Path):
        self.test_dir = test_dir
        self.valid_dir = test_dir / "valid"
        self.invalid_dir = test_dir / "invalid"
        self.results: List[TestResult] = []

    def run_all_tests(self) -> bool:
        """
        Run all test cases.

        Returns: True if all tests pass, False otherwise
        """
        print("="*70)
        print("EJECUTANDO TESTS DEL COMPILADOR PATITO")
        print("="*70)

        # Run valid test cases
        print("\nCASOS VÁLIDOS (Deben compilar exitosamente):")
        print("-"*70)
        valid_tests = self._run_valid_tests()

        # Run invalid test cases
        print("\nCASOS INVÁLIDOS (Deben fallar con error específico):")
        print("-"*70)
        invalid_tests = self._run_invalid_tests()

        # Print summary
        self._print_summary()

        # Return overall success
        all_passed = all(result.passed for result in self.results)
        return all_passed

    def _run_valid_tests(self) -> List[TestResult]:
        """Run all valid test cases."""
        if not self.valid_dir.exists():
            print(f"Directorio de tests válidos no encontrado: {self.valid_dir}")
            return []

        test_files = sorted(self.valid_dir.glob("*.patito"))

        if not test_files:
            print(f"No se encontraron archivos de test en: {self.valid_dir}")
            return []

        results = []
        for test_file in test_files:
            result = self._run_valid_test(test_file)
            results.append(result)
            print(result)

        return results

    def _run_valid_test(self, test_file: Path) -> TestResult:
        """Run a single valid test case."""
        compiler = PatitoCompiler(verbose=False)

        try:
            success = compiler.compile_file(str(test_file))

            if success:
                return TestResult(
                    name=test_file.name,
                    passed=True,
                    message=""
                )
            else:
                return TestResult(
                    name=test_file.name,
                    passed=False,
                    message=" (compilación falló inesperadamente)"
                )

        except CompilationError as e:
            return TestResult(
                name=test_file.name,
                passed=False,
                message=f"\n    Error: {str(e)[:100]}..."
            )
        except Exception as e:
            return TestResult(
                name=test_file.name,
                passed=False,
                message=f"\n    Error inesperado: {str(e)[:100]}..."
            )

    def _run_invalid_tests(self) -> List[TestResult]:
        """Run all invalid test cases."""
        if not self.invalid_dir.exists():
            print(f"Directorio de tests inválidos no encontrado: {self.invalid_dir}")
            return []

        test_files = sorted(self.invalid_dir.glob("*.patito"))

        if not test_files:
            print(f"No se encontraron archivos de test en: {self.invalid_dir}")
            return []

        results = []
        for test_file in test_files:
            result = self._run_invalid_test(test_file)
            results.append(result)
            print(result)

        return results

    def _run_invalid_test(self, test_file: Path) -> TestResult:
        """Run a single invalid test case."""
        compiler = PatitoCompiler(verbose=False)

        # Read expected error from comments in file
        expected_error = self._extract_expected_error(test_file)

        try:
            success = compiler.compile_file(str(test_file))

            # If it compiled successfully, that's wrong!
            if success:
                return TestResult(
                    name=test_file.name,
                    passed=False,
                    message=f"\n    Error: Se esperaba fallo, pero compiló exitosamente"
                )

        except CompilationError as e:
            error_message = str(e)

            # Check if error message contains expected keywords
            if expected_error:
                expected_keywords = expected_error.lower().split()
                error_lower = error_message.lower()

                # Check if any expected keyword is in the actual error
                found_match = any(keyword in error_lower for keyword in expected_keywords if len(keyword) > 3)  # Ignore short words

                if found_match:
                    return TestResult(
                        name=test_file.name,
                        passed=True,
                        message=f"\n    Esperado: {expected_error}"
                    )
                else:
                    return TestResult(
                        name=test_file.name,
                        passed=False,
                        message=f"\n    Esperado: {expected_error}\n    Recibido: {error_message[:100]}..."
                    )
            else:
                # No expected error specified, just check that it failed
                return TestResult(
                    name=test_file.name,
                    passed=True,
                    message=""
                )

        except Exception as e:
            return TestResult(
                name=test_file.name,
                passed=False,
                message=f"\n    Error inesperado: {str(e)[:100]}..."
            )

        return TestResult(
            name=test_file.name,
            passed=False,
            message=" (no se pudo ejecutar el test)"
        )

    def _extract_expected_error(self, test_file: Path) -> str:
        """Extract expected error from test file comments."""
        try:
            content = test_file.read_text(encoding='utf-8')
            lines = content.split('\n')

            for line in lines[:10]:  # Check first 10 lines
                if 'ERROR EXPECTED:' in line:
                    # Extract text after "ERROR EXPECTED:"
                    parts = line.split('ERROR EXPECTED:', 1)
                    if len(parts) > 1:
                        return parts[1].strip().replace('//', '').strip()

        except Exception:
            pass

        return ""

    def _print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("RESUMEN DE TESTS")
        print("="*70)

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        print(f"\nTotal de tests: {total}")
        print(f"Pasados:     {passed}")
        print(f"Fallados:    {failed}")

        if failed == 0:
            print("\n¡TODOS LOS TESTS PASARON! El compilador está listo para presentar.")
        else:
            print(f"\n{failed} test(s) fallaron. Revisa los errores arriba.")

        print("="*70)


def main():
    """Main entry point."""
    # Get test directory
    script_dir = Path(__file__).parent
    test_dir = script_dir / "test_programs"

    if not test_dir.exists():
        print(f"❌ Error: Directorio de tests no encontrado: {test_dir}")
        sys.exit(1)

    # Run tests
    runner = TestRunner(test_dir)
    all_passed = runner.run_all_tests()

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
