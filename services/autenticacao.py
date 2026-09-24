import hashlib
from datetime import datetime

from services.supabase_client import obter_supabase


# ============================================================
# UTILITÁRIOS
# ============================================================

def gerar_hash_senha(senha):
    return hashlib.sha256(
        str(senha).encode("utf-8")
    ).hexdigest()


def agora_data():
    return datetime.now().strftime("%d/%m/%Y")


def _cliente():
    return obter_supabase()


# ============================================================
# INICIALIZAÇÃO
# ============================================================

def inicializar_usuarios():
    cliente = _cliente()

    senha_admin = gerar_hash_senha(
        "admin123"
    )

    resposta = (
        cliente
        .table("usuarios")
        .select("*")
        .eq("usuario", "admin")
        .limit(1)
        .execute()
    )

    if resposta.data:
        return

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

    senha_digitada = gerar_hash_senha(
        senha
    )

    if senha_digitada != registro.get("senha"):
        return None

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

    (
        cliente
        .table("usuarios")
        .insert(
            {
                "usuario": usuario,
                "nome": nome,
                "senha": gerar_hash_senha(senha),
                "perfil": perfil,
                "ativo": True,
                "data_criacao": agora_data(),
            }
        )
        .execute()
    )


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

    (
        cliente
        .table("usuarios")
        .update(
            {
                "senha": gerar_hash_senha(nova_senha),
            }
        )
        .eq("id", usuario_id)
        .execute()
    )