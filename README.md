# 🥫 Sistema de Entrega de Cestas Básicas

App em Streamlit + Supabase para controlar a entrega de cestas básicas:
terminal com leitor de crachá, cadastro permanente de colaboradores,
períodos de entrega, estoque, histórico, relatórios e áudios.

## Estrutura

| Arquivo / pasta | O que faz |
|---|---|
| `app.py` | Telas do app (Terminal, Consulta, Dashboard, Colaboradores…) |
| `database/database.py` | Períodos, estoque, histórico, liberação de cesta |
| `services/identificacao.py` | Identifica matrícula/crachá |
| `services/cadastro.py` | Cadastro permanente matrícula → crachá |
| `services/importador.py` | Importação da planilha Excel |
| `services/autenticacao.py` | Login e usuários |
| `services/audio_manager.py` | Áudios do terminal |
| `services/tempo.py` | Data/hora no fuso local |
| `sql/` | Scripts para rodar no Supabase (SQL Editor) |

## Secrets (Streamlit Cloud → Settings → Secrets)

```toml
SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
SUPABASE_KEY = "sua-chave"
SUPABASE_SERVICE_ROLE_KEY = "chave-service-role"   # usada pelos áudios
FUSO_HORARIO = "America/Manaus"                    # opcional
ADMIN_SENHA_INICIAL = "uma-senha-forte"            # só usada na 1ª instalação
```

Nunca coloque essas chaves no código nem no GitHub.

## Como o crachá funciona

1. No Terminal, digite a matrícula.
2. Se a pessoa não tiver crachá cadastrado, o app pede para aproximar o
   crachá do leitor. O crachá fica salvo no **cadastro permanente** e a
   cesta é liberada.
3. Nas próximas entregas basta aproximar o crachá.
4. Em toda leitura aparece o botão **🪪 Atualizar crachá** para trocar o
   crachá (perdido, novo etc.). A troca não libera cesta.
5. A tela **Colaboradores** (admin) mostra o cadastro, permite ajustes
   manuais e exportação.

## Como atualizar o app

- Todo commit na branch `main` atualiza o app no Streamlit Cloud
  automaticamente (cerca de 1 minuto).
- Mudanças pequenas: edite o arquivo no GitHub (ícone ✏️) e clique em
  **Commit changes**.
- Mudanças maiores: teste antes no computador:

```bash
pip install -r requirements.txt
streamlit run app.py
```

  (crie o arquivo `.streamlit/secrets.toml` com os Secrets acima; ele não
  vai para o GitHub.)
- Biblioteca nova → adicione no `requirements.txt`.
- Mudança no banco → salve o script em `sql/` e rode no SQL Editor do
  Supabase **antes** de publicar o código que depende dele.
- Logs de erro e botão **Reboot**: share.streamlit.io → seu app →
  **Manage app**.
