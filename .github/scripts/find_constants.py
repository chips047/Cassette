import os
import re

IGNORE_DIRS = {
    "venv",
    ".venv",
    "env",
    ".env",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "build",
    "dist",
    ".pytest_cache",
    ".mypy_cache",
    "site-packages",
}


def find_constants(root_dir="."):
    pattern = re.compile(r"\b[A-ZА-ЯЁ][A-ZА-ЯЁ0-9]*(?:_[A-ZА-ЯЁ0-9]+)+\b")

    all_constants = set()

    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)

                try:
                    with open(
                        file_path, "r", encoding="utf-8", errors="ignore"
                    ) as f:
                        
                        content = f.read()
                        matches = pattern.findall(content)

                        if matches:
                            unique_in_file = set(matches)
                            print(f"\n📁 Файл: {file_path}")
                            for const in sorted(unique_in_file):
                                print(f"   └── {const}")

                            all_constants.update(unique_in_file)

                except Exception as e:
                    print(f"Ошибка при чтении файла {file_path}: {e}")

    print("\n" + "=" * 40)
    print(f"Всего уникальных констант найдено: {len(all_constants)}")
    print("=" * 40)

if __name__ == "__main__":
    target_folder = "."
    find_constants(target_folder)