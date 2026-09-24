import streamlit as st
from supabase import create_client


st.set_page_config(
    page_title="Teste Supabase",
    page_icon="🧪",
    layout="centered",
)


st.title("🧪 Teste de conexão com Supabase")

try:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]

    supabase = create_client(
        supabase_url,
        supabase_key,
    )

    st.success("✅ Cliente Supabase criado com sucesso.")

    st.info(
        "Isso confirma que o app conseguiu ler os Secrets "
        "e inicializar a conexão com o Supabase."
    )

    st.divider()

    st.subheader("🔎 Teste opcional de tabela")

    tabela = st.text_input(
        "Nome da tabela para testar",
        value="colaboradores",
    )

    if st.button("Testar leitura da tabela"):
        try:
            resposta = (
                supabase
                .table(tabela)
                .select("*")
                .limit(5)
                .execute()
            )

            st.success(f"✅ Consegui consultar a tabela: {tabela}")
            st.write(resposta.data)

        except Exception as erro_tabela:
            st.warning(
                "A conexão com o Supabase foi criada, "
                "mas não consegui consultar essa tabela."
            )
            st.error(str(erro_tabela))

except KeyError as erro_secret:
    st.error("❌ Secrets do Supabase não configurados corretamente.")
    st.code(
        """
SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
SUPABASE_KEY = "SUA_CHAVE_AQUI"
        """
    )
    st.error(f"Secret ausente: {erro_secret}")

except Exception as erro:
    st.error("❌ Erro ao conectar com o Supabase.")
    st.error(str(erro))