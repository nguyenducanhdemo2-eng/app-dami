from __future__ import annotations

import secrets
from pathlib import Path

from cryptography.fernet import Fernet


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
EXAMPLE_FILE = ROOT / ".env.example"


def replace_value(content: str, key: str, value: str) -> str:
    lines = content.splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            current = line.split("=", 1)[1]
            if not current or current == "CHANGE_ME":
                lines[index] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def main() -> None:
    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
    else:
        content = EXAMPLE_FILE.read_text(encoding="utf-8")

    admin_password = secrets.token_urlsafe(14)
    content = replace_value(content, "APP_ADMIN_PASSWORD", admin_password)
    content = replace_value(content, "SESSION_SECRET", secrets.token_urlsafe(48))
    content = replace_value(content, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    ENV_FILE.write_text(content, encoding="utf-8")

    print("Đã tạo/cập nhật tệp .env")
    print(f"Mật khẩu quản trị mới (hãy lưu lại): {admin_password}")
    print("Tiếp theo: mở .env và điền APP_BASE_URL, META_APP_ID, META_APP_SECRET.")


if __name__ == "__main__":
    main()

