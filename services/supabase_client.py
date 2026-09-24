import os

import streamlit as st
from supabase import create_client


def _obter_secret(nome):
    valor = None

    try:
        valor = st.secrets.get(nome)
    except Exception:
        valor = None

    if not valor:
        valor = os.getenv(nome)

    if valor is None:
        return None

    return str(valor).strip()


@st.cache_resource
def obter_supabase():
    supabase_url = _obter_secret("SUPABASE_URL")
    supabase_key = _obter_secret("SUPABASE_KEY")

    if not supabase_url:
        raise RuntimeError(
            "SUPABASE_URL não configurado nos Secrets do Streamlit."
        )

    if not supabase_key:
        raise RuntimeError(
            "SUPABASE_KEY não configurado nos Secrets do Streamlit."
        )

    if "/rest/v1" in supabase_url:
        raise RuntimeError(
            "SUPABASE_URL está incorreto. "
            "Use apenas https://SEU-PROJETO.supabase.co, sem /rest/v1."
        )

    return create_client(
        supabase_url,
        supabase_key,
    )