from datetime import datetime, timezone
from pathlib import Path
import re

import streamlit as st

from services.supabase_client import obter_supabase_admin


BUCKET_AUDIO = "audios-cestas"
TABELA_AUDIO = "configuracoes_audio"
MAX_AUDIO_BYTES = 10 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_LOCAL_DIR = BASE_DIR / "assets" / "audio"

TIPOS_AUDIO = {
    "cesta_normal": {
        "titulo": "🥫 Cesta normal",
        "descricao": "Retirada liberada somente com cesta normal.",
        "padrao_local": "cesta_normal.wav",
    },
    "cesta_especial": {
        "titulo": "⭐ Cesta especial",
        "descricao": "Retirada liberada somente com cesta especial.",
        "padrao_local": "cesta_especial.wav",
    },
    "cesta_normal_especial": {
        "titulo": "🥫⭐ Normal + especial",
        "descricao": "Retirada liberada com uma cesta normal e uma especial.",
        "padrao_local": "cesta_normal_especial.wav",
    },
    "negado": {
        "titulo": "🚫 Cesta não liberada",
        "descricao": "Usado quando a retirada é negada, inclusive por motivo na coluna Perde.",
        "padrao_local": None,
    },
    "duplicado": {
        "titulo": "🟠 Retirada já realizada",
        "descricao": "Usado quando o colaborador já retirou a cesta.",
        "padrao_local": None,
    },
    "sem_estoque": {
        "titulo": "📦 Estoque insuficiente",
        "descricao": "Usado quando não há estoque suficiente para a retirada.",
        "padrao_local": None,
    },
    "nao_encontrado": {
        "titulo": "❌ Colaborador não encontrado",
        "descricao": "Usado quando matrícula/crachá não é localizado.",
        "padrao_local": None,
    },
    "demitido": {
        "titulo": "⚫ Colaborador demitido",
        "descricao": "Usado quando a identificação pertence à lista de demitidos.",
        "padrao_local": None,
    },
    "erro_cracha": {
        "titulo": "🪪 Erro no cadastro do crachá",
        "descricao": "Usado quando o novo crachá não pode ser cadastrado.",
        "padrao_local": None,
    },
}

EXTENSOES_AUDIO = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
}


def _agora_iso():
    return datetime.now(timezone.utc).isoformat()


def _validar_tipo(tipo):
    if tipo not in TIPOS_AUDIO:
        raise ValueError("Tipo de áudio inválido.")


def _nome_seguro(nome):
    nome = Path(str(nome or "audio")).name
    base = Path(nome).stem
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-") or "audio"
    return base[:80]


def _mime_por_nome(nome):
    extensao = Path(str(nome or "")).suffix.lower()
    mime = EXTENSOES_AUDIO.get(extensao)
    if mime is None:
        raise ValueError("Formato não permitido. Use MP3, WAV ou OGG.")
    return mime, extensao


def _linha_config(tipo):
    cliente = obter_supabase_admin()
    resposta = (
        cliente
        .table(TABELA_AUDIO)
        .select("*")
        .eq("tipo", tipo)
        .limit(1)
        .execute()
    )
    return resposta.data[0] if resposta.data else None


def verificar_setup_audio():
    """Valida tabela e bucket sem modificar dados."""
    try:
        cliente = obter_supabase_admin()
        cliente.table(TABELA_AUDIO).select("tipo").limit(1).execute()
        cliente.storage.from_(BUCKET_AUDIO).list()
        return {"ok": True, "erro": None}
    except Exception as erro:
        return {"ok": False, "erro": str(erro)}


def listar_configuracoes_audio():
    cliente = obter_supabase_admin()
    resposta = cliente.table(TABELA_AUDIO).select("*").execute()
    por_tipo = {
        item.get("tipo"): item
        for item in (resposta.data or [])
        if item.get("tipo") in TIPOS_AUDIO
    }

    saida = []
    for tipo, info in TIPOS_AUDIO.items():
        row = por_tipo.get(tipo) or {}
        caminho = row.get("caminho_storage")
        ativo = row.get("ativo")
        if ativo is None:
            ativo = True

        if caminho:
            fonte = "Supabase Storage"
        elif info.get("padrao_local"):
            fonte = "Áudio padrão local"
        else:
            fonte = "Sem áudio configurado"

        saida.append(
            {
                "tipo": tipo,
                "titulo": info["titulo"],
                "descricao": info["descricao"],
                "ativo": bool(ativo),
                "fonte": fonte,
                "nome_arquivo": row.get("nome_arquivo"),
                "caminho_storage": caminho,
                "mime_type": row.get("mime_type"),
                "atualizado_em": row.get("atualizado_em"),
                "atualizado_por": row.get("atualizado_por"),
            }
        )

    return saida


@st.cache_data(ttl=60, show_spinner=False)
def obter_audio_evento(tipo):
    """
    Retorna bytes do áudio efetivo. Se o Supabase estiver indisponível,
    preserva o áudio padrão local para os três tipos de retirada liberada.
    """
    _validar_tipo(tipo)
    info = TIPOS_AUDIO[tipo]

    try:
        row = _linha_config(tipo)
    except Exception:
        row = None

    if row is not None and row.get("ativo") is False:
        return {
            "tipo": tipo,
            "ativo": False,
            "dados": None,
            "mime_type": None,
            "fonte": "desativado",
            "nome_arquivo": None,
        }

    if row and row.get("caminho_storage"):
        try:
            cliente = obter_supabase_admin()
            dados = cliente.storage.from_(BUCKET_AUDIO).download(
                row["caminho_storage"]
            )
            if dados:
                return {
                    "tipo": tipo,
                    "ativo": True,
                    "dados": bytes(dados),
                    "mime_type": row.get("mime_type") or "audio/mpeg",
                    "fonte": "supabase",
                    "nome_arquivo": row.get("nome_arquivo") or "audio",
                }
        except Exception:
            # Se um arquivo remoto sumir, o terminal continua funcionando
            # com o padrão local quando houver.
            pass

    padrao = info.get("padrao_local")
    if padrao:
        caminho = AUDIO_LOCAL_DIR / padrao
        if caminho.exists():
            mime, _ = _mime_por_nome(caminho.name)
            return {
                "tipo": tipo,
                "ativo": True,
                "dados": caminho.read_bytes(),
                "mime_type": mime,
                "fonte": "local",
                "nome_arquivo": caminho.name,
            }

    return {
        "tipo": tipo,
        "ativo": True,
        "dados": None,
        "mime_type": None,
        "fonte": "nenhum",
        "nome_arquivo": None,
    }


def salvar_audio_personalizado(tipo, nome_arquivo, dados, usuario=None):
    _validar_tipo(tipo)

    if dados is None:
        raise ValueError("Nenhum arquivo de áudio foi informado.")

    dados = bytes(dados)
    if not dados:
        raise ValueError("O arquivo de áudio está vazio.")

    if len(dados) > MAX_AUDIO_BYTES:
        raise ValueError("O arquivo deve ter no máximo 10 MB.")

    mime, extensao = _mime_por_nome(nome_arquivo)
    nome_base = _nome_seguro(nome_arquivo)
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    caminho_novo = f"{tipo}/{carimbo}_{nome_base}{extensao}"

    cliente = obter_supabase_admin()
    antigo = _linha_config(tipo)
    caminho_antigo = antigo.get("caminho_storage") if antigo else None

    bucket = cliente.storage.from_(BUCKET_AUDIO)
    try:
        bucket.upload(
            path=caminho_novo,
            file=dados,
            file_options={
                "content-type": mime,
                "cache-control": "3600",
                "upsert": "false",
            },
        )

        cliente.table(TABELA_AUDIO).upsert(
            {
                "tipo": tipo,
                "caminho_storage": caminho_novo,
                "nome_arquivo": Path(str(nome_arquivo)).name,
                "mime_type": mime,
                "ativo": True,
                "atualizado_em": _agora_iso(),
                "atualizado_por": usuario,
            }
        ).execute()
    except Exception:
        try:
            bucket.remove([caminho_novo])
        except Exception:
            pass
        raise

    if caminho_antigo and caminho_antigo != caminho_novo:
        try:
            bucket.remove([caminho_antigo])
        except Exception:
            pass

    obter_audio_evento.clear()
    return caminho_novo


def definir_audio_ativo(tipo, ativo, usuario=None):
    _validar_tipo(tipo)
    cliente = obter_supabase_admin()
    row = _linha_config(tipo) or {}

    cliente.table(TABELA_AUDIO).upsert(
        {
            "tipo": tipo,
            "caminho_storage": row.get("caminho_storage"),
            "nome_arquivo": row.get("nome_arquivo"),
            "mime_type": row.get("mime_type"),
            "ativo": bool(ativo),
            "atualizado_em": _agora_iso(),
            "atualizado_por": usuario,
        }
    ).execute()

    obter_audio_evento.clear()


def restaurar_audio_padrao(tipo, usuario=None):
    _validar_tipo(tipo)
    cliente = obter_supabase_admin()
    row = _linha_config(tipo)
    caminho_antigo = row.get("caminho_storage") if row else None

    cliente.table(TABELA_AUDIO).upsert(
        {
            "tipo": tipo,
            "caminho_storage": None,
            "nome_arquivo": None,
            "mime_type": None,
            "ativo": True,
            "atualizado_em": _agora_iso(),
            "atualizado_por": usuario,
        }
    ).execute()

    if caminho_antigo:
        try:
            cliente.storage.from_(BUCKET_AUDIO).remove([caminho_antigo])
        except Exception:
            pass

    obter_audio_evento.clear()
