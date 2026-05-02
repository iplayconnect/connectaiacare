"""CareLeadData — dataclass cumulativo dos dados do lead (vertical care).

Cada campo é Optional. `dados_confirmados[]` rastreia o que JÁ foi coletado
pra agent não repetir pergunta. `dados_pendentes[]` rastreia o que ainda
falta.

Schema espelha colunas do CSM (migration 062). Usado tanto pelo
DataExtractor (preencher) quanto pelo agent prompt (consultar via
`get_context_for_agent()`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Schema de referência — usado por testes e validações.
# Mantido em sync com migration 062 (lead_data column comment).
CARE_LEAD_DATA_SCHEMA: dict[str, type] = {
    "nome": str,
    "primeiro_nome": str,
    "telefone": str,
    "email": str,
    "cidade": str,
    "estado": str,
    "relacao": str,           # "filho_a", "neto_a", "conjuge", "cuidador_pro", "self"
    "count_idosos": int,
    "idades_idosos": list,    # list[int]
    "moram_sozinhos": bool,
    "moram_em_ilpi": bool,
    "dores": list,            # list[str]
    "count_medicamentos": int,
    "tem_dificuldade_medicacao": bool,
    "organizacao": str,        # B2B: nome da ILPI / clínica
    "cargo_b2b": str,          # B2B: "diretor_a", "enfermeira_chefe", etc
    "ja_cliente_concorrente": bool,
    "concorrente_nome": str,   # se ja_cliente_concorrente=True
    "quer_demo": bool,
    "intent_b2c_b2b": str,     # "b2c" | "b2b" | "indefinido"
}


@dataclass
class CareLeadData:
    """Lead data cumulativo. Todos campos Optional.

    Construção:
        ld = CareLeadData()
        ld.merge({"primeiro_nome": "Douglas", "count_idosos": 2})
        ld.dados_confirmados → ["primeiro_nome", "count_idosos"]
    """

    # Identificação
    nome: Optional[str] = None
    primeiro_nome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None

    # Relacionamento com idoso(s)
    relacao: Optional[str] = None
    count_idosos: Optional[int] = None
    idades_idosos: list[int] = field(default_factory=list)
    moram_sozinhos: Optional[bool] = None
    moram_em_ilpi: Optional[bool] = None

    # Quadro de saúde / dores
    dores: list[str] = field(default_factory=list)
    count_medicamentos: Optional[int] = None
    tem_dificuldade_medicacao: Optional[bool] = None

    # B2B
    organizacao: Optional[str] = None
    cargo_b2b: Optional[str] = None
    ja_cliente_concorrente: Optional[bool] = None
    concorrente_nome: Optional[str] = None

    # Intent
    quer_demo: Optional[bool] = None
    intent_b2c_b2b: Optional[str] = None  # "b2c" | "b2b" | "indefinido"

    # Tracking
    dados_confirmados: list[str] = field(default_factory=list)
    dados_pendentes: list[str] = field(default_factory=list)

    # ─── Persistência ────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "CareLeadData":
        """Constrói CareLeadData de um JSONB do banco. Tolerante a
        campos extras (ignora) e ausentes (usa default)."""
        if not data:
            return cls()
        kwargs: dict[str, Any] = {}
        for f in cls.__dataclass_fields__:
            if f in data and data[f] is not None:
                kwargs[f] = data[f]
        # Garante listas mesmo se vier null
        for list_field in ("idades_idosos", "dores",
                           "dados_confirmados", "dados_pendentes"):
            if list_field in kwargs and not isinstance(kwargs[list_field], list):
                kwargs[list_field] = []
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Serializa pra JSONB. Omite campos None pra economizar
        espaço (banco aceita keys ausentes)."""
        out: dict[str, Any] = {}
        for f in self.__dataclass_fields__:
            v = getattr(self, f)
            if v is None:
                continue
            if isinstance(v, list) and not v:
                # listas vazias só serializa se for tracker
                if f not in ("dados_confirmados", "dados_pendentes"):
                    continue
            out[f] = v
        return out

    # ─── Mutação ─────────────────────────────────────────────────

    def merge(self, updates: dict[str, Any]) -> list[str]:
        """Aplica updates somente nos campos que mudam de valor.

        Returns:
            Lista de campos que foram efetivamente atualizados (não
            no-op). Útil pra logar "data extraído: X, Y, Z".
        """
        changed: list[str] = []
        for k, v in updates.items():
            if k not in self.__dataclass_fields__:
                continue
            if v is None or v == "":
                continue
            current = getattr(self, k)
            # Listas: append-distinct (não sobrescreve histórico)
            if isinstance(current, list):
                if isinstance(v, list):
                    new_items = [x for x in v if x not in current]
                    if new_items:
                        current.extend(new_items)
                        changed.append(k)
                else:
                    if v not in current:
                        current.append(v)
                        changed.append(k)
                continue
            # Escalares: só sobrescreve se ainda não tinha valor
            # (evita extractor low-confidence apagar valor explícito).
            # Se quiser forçar overwrite, chamador faz setattr direto.
            if current is None:
                setattr(self, k, v)
                changed.append(k)
            elif current != v:
                # valor já existe e é diferente: log mas não sobrescreve
                # (caller decide via overwrite=True flag se quiser)
                pass

        # Atualiza dados_confirmados
        for c in changed:
            if c in ("dados_confirmados", "dados_pendentes"):
                continue
            if c not in self.dados_confirmados:
                self.dados_confirmados.append(c)
        return changed

    def has(self, field_name: str) -> bool:
        """True se o campo já tem valor (não None, não lista vazia)."""
        if field_name not in self.__dataclass_fields__:
            return False
        v = getattr(self, field_name)
        if v is None:
            return False
        if isinstance(v, list) and not v:
            return False
        return True

    def missing(self, fields: list[str]) -> list[str]:
        """Dado um set de campos esperados, retorna os que faltam."""
        return [f for f in fields if not self.has(f)]
