#!/usr/bin/env python3
"""Cria um usuário de teste no Firebase Authentication."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]

load_dotenv(ROOT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")

FIREBASE_API_KEY = os.getenv(
    "FIREBASE_WEB_API_KEY",
    "AIzaSyDgjwin-zXFzl-J-E7dlxvjmEGe6C_xhMU",
)
IDENTITY_URL = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
)
UPDATE_URL = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={FIREBASE_API_KEY}"
)

DEFAULT_EMAIL = os.getenv("TEST_USER_EMAIL", "teste@thora.local")
DEFAULT_PASSWORD = os.getenv("TEST_USER_PASSWORD", "Teste@123456")
DEFAULT_NAME = os.getenv("TEST_USER_NAME", "Usuário Teste")


def _firebase_error_message(payload: dict) -> str:
    error = payload.get("error", {})
    return error.get("message", json.dumps(payload, ensure_ascii=False))


def create_test_user(
    email: str,
    password: str,
    display_name: str,
) -> dict[str, str]:
    """Cadastra usuário no Firebase Auth e define o nome de exibição."""
    with httpx.Client(timeout=30.0) as client:
        signup = client.post(
            IDENTITY_URL,
            json={
                "email": email,
                "password": password,
                "returnSecureToken": True,
            },
        )
        data = signup.json()

        if signup.status_code != 200:
            message = _firebase_error_message(data)
            if message == "EMAIL_EXISTS":
                raise RuntimeError(
                    f"O e-mail {email} já está cadastrado. Use outro e-mail ou faça login."
                )
            raise RuntimeError(f"Falha ao criar usuário: {message}")

        id_token = data["idToken"]
        local_id = data["localId"]

        profile = client.post(
            UPDATE_URL,
            json={
                "idToken": id_token,
                "displayName": display_name,
                "returnSecureToken": True,
            },
        )
        profile_data = profile.json()
        if profile.status_code != 200:
            raise RuntimeError(
                f"Usuário criado ({local_id}), mas falhou ao definir nome: "
                f"{_firebase_error_message(profile_data)}"
            )

        return {
            "uid": local_id,
            "email": email,
            "password": password,
            "displayName": display_name,
        }


def main() -> int:
    email = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMAIL
    password = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PASSWORD
    display_name = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_NAME

    try:
        user = create_test_user(email, password, display_name)
    except Exception as exc:
        print(f"[erro] {exc}", file=sys.stderr)
        return 1

    print("Usuário de teste criado no Firebase Authentication:")
    print(f"  Nome:   {user['displayName']}")
    print(f"  E-mail: {user['email']}")
    print(f"  Senha:  {user['password']}")
    print(f"  UID:    {user['uid']}")
    print()
    print("Use essas credenciais na tela de login do app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
