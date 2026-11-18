import hashlib
import hmac
import os
import secrets

from services.supabase_client import obter_supabase
from services.tempo import hoje_texto


# ============================================================
# SENHAS
# ============================================================
# Formato novo: pbkdf2_sha256$<iterações>$<sal>$<hash>
# Senhas antigas (SHA-256 simples, 64 caracteres) continuam funcionando e
# são convertidas automaticamente para o formato novo no próximo login.

ITERACOES_PBKDF2 = 260_000


def _hash_legado(senha):
    return hashlib.sha256(str(senha).encode("utf-8")).hexdigest()


def gerar_hash_senha(senha):
    sal = secrets.token_hex(16)
    derivado = hashlib.pbkdf2_hmac(
        "sha256",
        str(senha).encode("utf-8"),
        sal.encode("utf-8"),
        ITERACOES_PBKDF2,
    ).hex()
    return f"pbkdf2_sha256${ITERACOES_PBKDF2}${sal}${derivado}"


def senha_confere(senha, hash_salvo):
    hash_salvo = str(hash_salvo or "")

    if hash_salvo.startswith("pbkdf2_sha256$"):
        try:
            _, iteracoes, sal, esperado = hash_salvo.split("$", 3)
            derivado = hashlib.pbkdf2_hmac(
                "sha256",
                str(senha).encode("utf-8"),
                sal.encode("utf-8"),
                int(iteracoes),
            ).hex()
        except Exception:
            return False
        return hmac.compare_digest(derivado, esperado)

    return hmac.compare_digest(_hash_legado(senha), hash_salvo)


def _precisa_atualizar_hash(hash_salvo):
    return not str(hash_salvo or "").startswith("pbkdf2_sha256$")


def _salvar_hash(cliente, usuario_id, senha):
    """Grava no formato novo. Se a coluna do banco ainda for curta
    (ex.: varchar(64)), mantém o formato antigo para não quebrar."""
    try:
        cliente.table("usuarios").update(
            {"senha": gerar_hash_senha(senha)}
        ).eq("id", usuario_id).execute()
    except Exception:
        cliente.table("usuarios").update(
            {"senha": _hash_legado(senha)}
        ).eq("id", usuario_id).execute()


def agora_data():
    return hoje_texto()


def _cliente():
    return obter_supabase()


def _senha_admin_inicial():
    valor = None
    try:
        import streamlit as st

        valor = st.secrets.get("ADMIN_SENHA_INICIAL")
    except Exception:
        valor = None
    valor = valor or os.getenv("ADMIN_SENHA_INICIAL")
    return str(valor).strip() if valor else None


# ============================================================
# INICIALIZAÇÃO
# ============================================================

def inicializar_usuarios():
    """Cria o usuário admin só na primeira instalação.

    A senha inicial vem do Secret ADMIN_SENHA_INICIAL. Ela não fica mais
    escrita no código, que está num repositório público.
    """
    cliente = _cliente()

    resposta = (
        cliente
        .table("usuarios")
        .select("id")
        .eq("usuario", "admin")
        .limit(1)
        .execute()
    )

    if resposta.data:
        return

    senha_inicial = _senha_admin_inicial()

    if not senha_inicial:
        # Sem a senha nos Secrets, não cria admin com senha conhecida.
        return

    senha_admin = gerar_hash_senha(senha_inicial)

    (
        cliente
        .table("usuarios")
        .insert(
            {
                "usuario": "admin",
                "nome": "Administrador",
                "senha": senha_admin,
                "perfil": "ADMIN",
                "ativo": True,
                "data_criacao": agora_data(),
            }
        )
        .execute()
    )


# ============================================================
# LOGIN
# ============================================================

def autenticar(usuario, senha):
    if not usuario or not senha:
        return None

    cliente = _cliente()

    usuario = str(usuario).strip()

    resposta = (
        cliente
        .table("usuarios")
        .select("*")
        .eq("usuario", usuario)
        .limit(1)
        .execute()
    )

    if not resposta.data:
        return None

    registro = resposta.data[0]

    if not registro.get("ativo"):
        return None

    if not senha_confere(senha, registro.get("senha")):
        return None

    if _precisa_atualizar_hash(registro.get("senha")):
        try:
            _salvar_hash(cliente, registro["id"], senha)
        except Exception:
            pass

    return registro


# ============================================================
# CRUD DE USUÁRIOS
# ============================================================

def listar_usuarios():
    cliente = _cliente()

    resposta = (
        cliente
        .table("usuarios")
        .select("*")
        .order(
            "id",
            desc=False,
        )
        .execute()
    )

    return resposta.data or []


def criar_usuario(usuario, nome, senha, perfil):
    if not usuario or not str(usuario).strip():
        raise Exception("Informe o usuário.")

    if not nome or not str(nome).strip():
        raise Exception("Informe o nome.")

    if not senha or not str(senha).strip():
        raise Exception("Informe a senha.")

    if perfil not in ["ADMIN", "OPERADOR"]:
        raise Exception("Perfil inválido.")

    cliente = _cliente()

    usuario = str(usuario).strip()
    nome = str(nome).strip()

    existente = (
        cliente
        .table("usuarios")
        .select("*")
        .eq("usuario", usuario)
        .limit(1)
        .execute()
    )

    if existente.data:
        raise Exception("Já existe um usuário com esse login.")

    dados = {
        "usuario": usuario,
        "nome": nome,
        "senha": gerar_hash_senha(senha),
        "perfil": perfil,
        "ativo": True,
        "data_criacao": agora_data(),
    }

    try:
        cliente.table("usuarios").insert(dados).execute()
    except Exception:
        # Coluna de senha ainda curta no banco: usa o formato antigo.
        dados["senha"] = _hash_legado(senha)
        cliente.table("usuarios").insert(dados).execute()


def alterar_status_usuario(usuario_id, ativo):
    cliente = _cliente()

    (
        cliente
        .table("usuarios")
        .update(
            {
                "ativo": bool(ativo),
            }
        )
        .eq("id", usuario_id)
        .execute()
    )


def alterar_senha_usuario(usuario_id, nova_senha):
    if not nova_senha or not str(nova_senha).strip():
        raise Exception("Informe a nova senha.")

    cliente = _cliente()

    _salvar_hash(cliente, usuario_id, nova_senha)