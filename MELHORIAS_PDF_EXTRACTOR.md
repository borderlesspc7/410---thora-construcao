# Melhorias no Importador de PDF

## Resumo
O importador de PDF foi melhorado para lidar com diferentes tipos de documentos, incluindo planilhas de BDI (Benefícios e Despesas Indiretas) com células mescladas e formatação complexa.

## Melhorias Implementadas

### 1. Múltiplas Estratégias de Extração
O sistema agora tenta três estratégias diferentes para extrair dados de PDFs:

- **Estratégia 1: extract_tables() padrão**
  - Usa a configuração padrão do pdfplumber
  - Funciona bem para PDFs com linhas de grade claras

- **Estratégia 2: extract_tables() com configurações customizadas**
  - Usa estratégia baseada em texto quando linhas não são detectadas
  - Parâmetros: `vertical_strategy="text"`, `horizontal_strategy="text"`
  - Tolerâncias ajustadas para capturar mais variações

- **Estratégia 3: Extração de texto estruturado**
  - Usada como fallback quando tabelas não são detectadas
  - Extrai texto linha por linha e cria uma estrutura tabular

### 2. Processamento de Células Mescladas
- Converte valores `None` (células mescladas) para strings vazias `""`
- Mantém a estrutura da tabela intacta
- Facilita o processamento posterior dos dados

### 3. Limpeza de Dados
- Remove quebras de linha (`\n`) do texto, substituindo por espaços
- Remove espaços extras no início e fim das células
- Converte todos os valores para strings para consistência

### 4. Logs Detalhados
O sistema agora registra informações detalhadas sobre cada extração:
- Número de páginas do PDF
- Dimensões de cada página
- Número de tabelas encontradas por página
- Linhas e colunas de cada tabela
- Avisos quando nenhuma tabela é encontrada

### 5. Metadados Adicionais
Cada tabela extraída agora inclui:
```json
{
  "page": 1,
  "table_id": "page_0_table_0",
  "rows": [...],
  "original_rows": 34,
  "columns": 4
}
```

## Teste Realizado

### Documento Testado
**Doc 28 - Projeto Básico ANEXO XXV_Det. de Taxas de BDI Ref. e Dif.**
- 2 páginas
- Planilha de BDI com células mescladas
- 4 colunas: Componente, Número, Descrição, Incidência
- 34 linhas por página

### Resultado
✅ **2 tabelas extraídas com sucesso**
- Página 1: 34 linhas x 4 colunas (BDI Referencial)
- Página 2: 34 linhas x 4 colunas (BDI Diferenciado)
- Células mescladas convertidas para strings vazias
- Texto limpo sem quebras de linha

### Exemplo de Dados Extraídos
```json
[
  ["BDI - BENEFÍCIOS E DESPESAS INIDIRETAS PARA ENCARGOS SOCIAIS: (preencher)", "", "", ""],
  ["DESCREVER A QUE SE REFERE O BDI REFERENCIAL", "", "", ""],
  ["COMPONENTE", "", "", ""],
  ["A", "", "DESPESAS INDIRETAS", "INCIDÊNCIA"],
  ["", "1", "Administração Central", ""],
  ["", "2", "Seguros + Garantias", ""],
  ...
]
```

## Arquivos Modificados

### backend/main.py
- Linhas 300-372: Função `extract_pdf()` completamente reescrita
- Adicionadas múltiplas estratégias de extração
- Processamento de células mescladas
- Logs detalhados

## Scripts de Teste Criados

1. **test_pdf_extraction.py** - Testa diferentes estratégias de extração
2. **test_pdf_detailed.py** - Mostra conteúdo detalhado das tabelas
3. **test_improved_extraction.py** - Testa a lógica melhorada diretamente
4. **test_api_complete.py** - Teste completo via API (upload + extração)

## Como Usar

1. Inicie o backend:
```powershell
$env:FIREBASE_DISABLED=1
$env:PORT=8081
python backend/main.py
```

2. Faça upload de um PDF:
```python
import requests

with open('seu_arquivo.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8081/api/upload',
        files={'file': ('arquivo.pdf', f, 'application/pdf')}
    )
    upload_id = response.json()['upload_id']
```

3. Extraia os dados:
```python
response = requests.post(
    'http://localhost:8081/api/extract',
    params={'upload_id': upload_id}
)
tables = response.json()['tables']
```

## Tipos de PDF Suportados

O sistema agora lida bem com:
- PDFs com linhas de grade visíveis
- PDFs com células mescladas
- Tabelas sem bordas (baseadas em alinhamento de texto)
- Documentos com texto estruturado
- Planilhas de BDI, orçamentos, etc.

## Próximos Passos (Opcional)

- Detecção automática de cabeçalhos de tabela
- Extração de imagens e gráficos
- OCR para PDFs escaneados
- Validação de dados extraídos
- Suporte a tabelas com estrutura hierárquica
