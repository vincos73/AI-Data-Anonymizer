from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_project_file(relative_path: str) -> str:
    return "\n".join(
        (PROJECT_ROOT / relative_path).read_text(encoding="utf-8").splitlines()
    )


class WindowsPackagingTest(unittest.TestCase):
    def test_installer_is_per_user_and_keeps_portable_build(self) -> None:
        installer = read_project_file("scripts/omissis_installer.iss")
        build_script = read_project_file("scripts/build_windows_app.ps1")

        self.assertIn(r"DefaultDirName={localappdata}\Programs\{#AppName}", installer)
        self.assertIn("PrivilegesRequired=lowest", installer)
        self.assertIn(r'Name: "{autoprograms}\{#AppName}"', installer)
        self.assertIn('Description: "Avvia {#AppName}"', installer)
        self.assertIn("OMISSIS-Setup.exe", build_script)
        self.assertIn("OMISSIS-Windows.zip", build_script)

    def test_inno_setup_download_is_pinned_and_hash_verified(self) -> None:
        bootstrap = read_project_file("scripts/install_inno_setup.ps1")

        self.assertIn('$InnoVersion = "6.7.3"', bootstrap)
        self.assertIn("9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732", bootstrap)
        self.assertIn("Get-FileHash", bootstrap)
        self.assertIn("github.com/jrsoftware/issrc/releases/download/is-6_7_3", bootstrap)

    def test_ci_builds_and_smoke_installs_the_windows_installer(self) -> None:
        tests_workflow = read_project_file(".github/workflows/tests.yml")
        release_workflow = read_project_file(".github/workflows/release.yml")

        self.assertIn("package-windows-installer", tests_workflow)
        self.assertIn("Verifica installazione silenziosa", tests_workflow)
        self.assertIn("dist/OMISSIS-Setup.exe", release_workflow)
        self.assertIn("dist/OMISSIS-Windows.zip", release_workflow)


if __name__ == "__main__":
    unittest.main()
