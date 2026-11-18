"""Data e hora no fuso horário local.

Os servidores do Streamlit Cloud rodam em UTC. Sem isso, os horários
gravados ficariam adiantados (4h em Manaus, 3h em Brasília).
O fuso pode ser trocado pelo Secret FUSO_HORARIO (ex.: "America/Sao_Paulo").
"""

import os
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


FUSO_PADRAO = "America/Manaus"


def _nome_fuso():
    nome = None

    try:
        import streamlit as st

        nome = st.secrets.get("FUSO_HORARIO")
    except Exception:
        nome = None

    return str(nome or os.getenv("FUSO_HORARIO") or FUSO_PADRAO).strip()


def fuso_local():
    if ZoneInfo is not None:
        try:
            return ZoneInfo(_nome_fuso())
        except Exception:
            pass

    # Último recurso: horário de Manaus (UTC-4, sem horário de verão).
    return timezone(timedelta(hours=-4))


def agora_local():
    return datetime.now(fuso_local())


def agora_texto():
    """Formato usado no banco: 18/11/2026 15:30:00."""
    return agora_local().strftime("%d/%m/%Y %H:%M:%S")


def hoje_texto():
    return agora_local().strftime("%d/%m/%Y")


def agora_iso():
    return agora_local().isoformat()
