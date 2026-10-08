"""Persistência local em SQLite: configuração, tomadores, notas emitidas e numeração da DPS."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

ESQUEMA = """
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tomadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    documento TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    dados TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sequencias (
    ambiente INTEGER NOT NULL,
    serie TEXT NOT NULL,
    ultimo INTEGER NOT NULL,
    PRIMARY KEY (ambiente, serie)
);
CREATE TABLE IF NOT EXISTS notas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ambiente INTEGER NOT NULL,
    serie TEXT NOT NULL,
    numero_dps INTEGER NOT NULL,
    id_dps TEXT NOT NULL,
    status TEXT NOT NULL,
    chave_acesso TEXT,
    numero_nfse TEXT,
    tomador_documento TEXT,
    tomador_nome TEXT,
    descricao TEXT NOT NULL,
    valor TEXT NOT NULL,
    dps_xml TEXT,
    nfse_xml TEXT,
    mensagem TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    UNIQUE (ambiente, serie, numero_dps)
);
CREATE INDEX IF NOT EXISTS idx_notas_chave ON notas (chave_acesso);
"""


def pasta_dados() -> Path:
    pasta = Path(os.environ.get("EMISSOR_HOME") or Path.home() / ".emissor")
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Banco:
    def __init__(self, caminho: str | os.PathLike | None = None):
        self.caminho = str(caminho or pasta_dados() / "emissor.db")
        self._lock = threading.RLock()
        self._con = sqlite3.connect(self.caminho, check_same_thread=False, isolation_level=None)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.executescript(ESQUEMA)

    def fechar(self) -> None:
        self._con.close()

    # ---- configuração -------------------------------------------------
    def obter_config(self, chave: str, padrao: Any = None) -> Any:
        with self._lock:
            row = self._con.execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone()
        return json.loads(row["valor"]) if row else padrao

    def salvar_config(self, chave: str, valor: Any) -> None:
        with self._lock:
            self._con.execute(
                "INSERT INTO config (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (chave, json.dumps(valor, ensure_ascii=False)),
            )

    # ---- tomadores ----------------------------------------------------
    def salvar_tomador(self, dados: dict) -> dict:
        agora = _agora()
        with self._lock:
            self._con.execute(
                """INSERT INTO tomadores (documento, nome, dados, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(documento) DO UPDATE SET nome = excluded.nome, dados = excluded.dados,
                   atualizado_em = excluded.atualizado_em""",
                (dados["documento"], dados["nome"], json.dumps(dados, ensure_ascii=False), agora, agora),
            )
        return self.obter_tomador(dados["documento"])

    def obter_tomador(self, documento: str) -> dict | None:
        with self._lock:
            row = self._con.execute("SELECT * FROM tomadores WHERE documento = ?", (documento,)).fetchone()
        return self._tomador(row) if row else None

    def listar_tomadores(self, busca: str = "") -> list[dict]:
        with self._lock:
            rows = self._con.execute(
                "SELECT * FROM tomadores WHERE nome LIKE ? OR documento LIKE ? ORDER BY nome",
                (f"%{busca}%", f"%{busca}%"),
            ).fetchall()
        return [self._tomador(r) for r in rows]

    def excluir_tomador(self, documento: str) -> bool:
        with self._lock:
            cur = self._con.execute("DELETE FROM tomadores WHERE documento = ?", (documento,))
        return cur.rowcount > 0

    @staticmethod
    def _tomador(row: sqlite3.Row) -> dict:
        d = json.loads(row["dados"])
        d["id"] = row["id"]
        return d

    # ---- numeração ----------------------------------------------------
    def proximo_numero_dps(self, ambiente: int, serie: str) -> int:
        """Reserva atomicamente o próximo nDPS da série (lacunas são permitidas no Padrão Nacional)."""
        with self._lock:
            self._con.execute("BEGIN IMMEDIATE")
            try:
                row = self._con.execute(
                    "SELECT ultimo FROM sequencias WHERE ambiente = ? AND serie = ?", (ambiente, serie)
                ).fetchone()
                proximo = (row["ultimo"] if row else 0) + 1
                self._con.execute(
                    """INSERT INTO sequencias (ambiente, serie, ultimo) VALUES (?, ?, ?)
                       ON CONFLICT(ambiente, serie) DO UPDATE SET ultimo = excluded.ultimo""",
                    (ambiente, serie, proximo),
                )
                self._con.execute("COMMIT")
            except Exception:
                self._con.execute("ROLLBACK")
                raise
        return proximo

    def definir_ultimo_numero(self, ambiente: int, serie: str, ultimo: int) -> None:
        with self._lock:
            self._con.execute(
                """INSERT INTO sequencias (ambiente, serie, ultimo) VALUES (?, ?, ?)
                   ON CONFLICT(ambiente, serie) DO UPDATE SET ultimo = excluded.ultimo""",
                (ambiente, serie, ultimo),
            )

    def ultimo_numero(self, ambiente: int, serie: str) -> int:
        with self._lock:
            row = self._con.execute(
                "SELECT ultimo FROM sequencias WHERE ambiente = ? AND serie = ?", (ambiente, serie)
            ).fetchone()
        return row["ultimo"] if row else 0

    # ---- notas --------------------------------------------------------
    def criar_nota(self, **campos: Any) -> int:
        campos.setdefault("criado_em", _agora())
        campos.setdefault("atualizado_em", campos["criado_em"])
        colunas = ", ".join(campos)
        marcadores = ", ".join("?" for _ in campos)
        with self._lock:
            cur = self._con.execute(f"INSERT INTO notas ({colunas}) VALUES ({marcadores})", tuple(campos.values()))
        return cur.lastrowid

    def atualizar_nota(self, nota_id: int, **campos: Any) -> None:
        campos["atualizado_em"] = _agora()
        atribuicoes = ", ".join(f"{c} = ?" for c in campos)
        with self._lock:
            self._con.execute(f"UPDATE notas SET {atribuicoes} WHERE id = ?", (*campos.values(), nota_id))

    def obter_nota(self, nota_id: int | None = None, chave_acesso: str | None = None) -> dict | None:
        with self._lock:
            if nota_id is not None:
                row = self._con.execute("SELECT * FROM notas WHERE id = ?", (nota_id,)).fetchone()
            else:
                row = self._con.execute("SELECT * FROM notas WHERE chave_acesso = ?", (chave_acesso,)).fetchone()
        return dict(row) if row else None

    def listar_notas(self, *, status: str | None = None, busca: str = "", limite: int = 50, ambiente: int | None = None) -> list[dict]:
        sql = "SELECT id, ambiente, serie, numero_dps, id_dps, status, chave_acesso, numero_nfse, tomador_documento, tomador_nome, descricao, valor, mensagem, criado_em, atualizado_em FROM notas WHERE 1=1"
        args: list[Any] = []
        if status:
            sql += " AND status = ?"
            args.append(status)
        if ambiente:
            sql += " AND ambiente = ?"
            args.append(ambiente)
        if busca:
            sql += " AND (tomador_nome LIKE ? OR tomador_documento LIKE ? OR descricao LIKE ? OR chave_acesso LIKE ? OR numero_nfse LIKE ?)"
            args.extend([f"%{busca}%"] * 5)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(int(limite))
        with self._lock:
            return [dict(r) for r in self._con.execute(sql, args).fetchall()]
