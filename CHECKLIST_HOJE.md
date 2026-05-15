# Checklist de Implementações e Correções (15/05/2026)

## 🚀 Deploy e Infraestrutura
- [x] **Configuração Vercel (Fullstack)**: Ajuste do `vercel.json` para suportar o deploy do frontend (Vite) e backend (FastAPI) no mesmo projeto (`api/index.py`).
- [x] **Ajuste de Timeouts**: Aumento dos timeouts da OpenAI e Ollama no `backend/config.py` (de 12s para 55s) para evitar cortes prematuros no plano Hobby da Vercel.
- [x] **Dependências**: Adição de `openai`, `camelot-py[cv]`, `PyMuPDF` e `opencv-python-headless` ao `pyproject.toml` e `requirements.txt`.
- [x] **Runtime Python**: Criação do ficheiro `.python-version` (3.12) para forçar a versão correta na Vercel.
- [x] **Git Push Protection**: Identificação e explicação do bloqueio do GitHub devido a uma API Key da OpenAI exposta no ficheiro `.env` (commit `24baa4b`).

## 🧠 Inteligência Artificial (OpenAI)
- [x] **Correção de Erro 400 (Bad Request)**: Adição da palavra "JSON" no `DETECTION_SYSTEM_PROMPT` para cumprir a exigência da OpenAI ao usar `response_format={"type": "json_object"}`.
- [x] **Mudança de Paradigma (Vision + Structured Outputs)**:
  - Implementação de conversão de páginas PDF para imagens Base64 (JPEG alta resolução) usando `pdfplumber`.
  - Envio do payload de imagem (`image_url`) para o GPT-4o analisar visualmente as grelhas da tabela.
  - Implementação do `EXTRACTION_JSON_SCHEMA` com `strict: True` para garantir que a IA devolve sempre a estrutura exata sem inventar chaves.
- [x] **Engenharia de Prompt Avançada**:
  - Regras rígidas de **Mapeamento Espacial** (leitura da esquerda para a direita, sem puxar valores de colunas vizinhas).
  - Regras de **Ancoragem pela Unidade** e separação de letras/números (ex: `422,33 CHP`).
  - **Sanity Check Matemático Obrigatório**: A IA agora é forçada a validar se `Quantidade * Valor Unitário = Valor Total` antes de gerar a linha.

## 📊 Processamento de Tabelas (Backend)
- [x] **Deteção Visual (Camelot + PyMuPDF)**:
  - Refatoração do endpoint `/api/orcamentos/detect-tables` para usar o `camelot` (leitura vetorial) em vez de depender exclusivamente de texto bruto.
  - Geração de *thumbnails* (prints reais) de cada tabela detetada usando `fitz` (PyMuPDF), convertendo as coordenadas da *bounding box* do Camelot.
- [x] **Processamento Multi-Tabela**:
  - Alteração do endpoint `/api/orcamentos/process-confirmed` para aceitar um *array* de `table_ids`.
  - Implementação de lógica de *merge* para combinar os itens e os resumos financeiros de várias tabelas num único objeto final.
  - Correção de erro de *fallback* e variáveis não declaradas (`raw_structured_items`) que causavam `Exception in ASGI application`.

## 💻 Interface de Utilizador (Frontend)
- [x] **Visualização de Thumbnails**: Atualização da interface `MockTableOption` e do componente `TableSelector.tsx` para exibir as imagens Base64 das tabelas detetadas em vez de texto bruto.
- [x] **Seleção Múltipla**: Transformação do `TableSelector` para permitir a seleção de múltiplas tabelas em simultâneo (checkboxes + array de IDs).
- [x] **Ajuste da Grelha de Validação**: Adição das colunas `Item`, `Banco` e `Tipo` (Grupo/Item) na página `ValidacaoOrcamento.tsx` para acomodar os novos dados estruturados devolvidos pela IA.