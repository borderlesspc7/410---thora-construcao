# 🗓️ ROADMAP DE DESENVOLVIMENTO - Thora Construção

**Última Atualização:** 24/02/2026  
**Status Atual:** 68% MVP | 54% Robusta

---

## 📍 Marcos do Projeto

```
┌─────────────┬─────────────┬─────────────┐
│   FASE 0    │   FASE 1    │   FASE 2    │
│  FUNDAÇÃO   │  MVP CORE   │  MELHORIAS  │
│   ✅ 40%    │   ⏳ 0%     │   ⏳ 0%     │
│    28h      │    43h      │    60h      │
└─────────────┴─────────────┴─────────────┘
              │   FASE 3    │
              │  ADVANCED   │
              │   ⏳ 0%     │
              │    45h      │
              └─────────────┘
```

---

## ✅ FASE 0: FUNDAÇÃO (28h investidas - 40% do MVP)

### Sprint 0.1: Infraestrutura e Setup ✅
- [x] Configuração do projeto (FastAPI + React + Vite)
- [x] Integração com Firebase/Firestore
- [x] Sistema de cache offline
- [x] Deploy scripts (Vercel + Render)
- [x] Configuração de CORS e ambiente

**Status:** ✅ Completo  
**Horas:** ~2h

---

### Sprint 0.2: Upload e Armazenamento ✅
- [x] Endpoint `/api/upload` com validação
- [x] Limite de 50MB e verificação de tipo
- [x] Salvamento no Firestore
- [x] Geração de UUID único por projeto
- [x] Interface de upload no frontend (drag & drop)

**Status:** ✅ Completo  
**Horas:** ~4h

---

### Sprint 0.3: Extração de Dados ⚠️
- [x] Integração com pdfplumber
- [x] Endpoint `/api/extract` para processar PDF
- [x] Identificação automática de tabelas
- [x] Parse de colunas (descrição, quantidade, valor, etc.)
- [x] Logs detalhados de processamento
- [x] Tratamento básico de erros
- [ ] Refinamento da detecção de colunas (pendente)

**Status:** ⚠️ 60% - Funcional mas precisa refinamento  
**Horas:** ~7h  
**Pendente:** Melhorias no parse (5h para MVP)

---

### Sprint 0.4: Validação e Edição ⚠️
- [x] Página ValidacaoOrcamento.tsx completa
- [x] Visualizador de PDF integrado (react-pdf)
- [x] Tabela editável de itens
- [x] Parse inteligente de dados extraídos
- [x] Detecção de cabeçalhos
- [x] Normalização de números (vírgula → ponto)
- [x] Seleção e remoção de itens
- [ ] Validações avançadas (pendente)

**Status:** ⚠️ 70% - Funcional mas precisa refinamento  
**Horas:** ~7h  
**Pendente:** Validações e refinamentos (3h para MVP)

---

### Sprint 0.5: Exportação ✅
- [x] Integração com openpyxl
- [x] Endpoint `/api/export-xlsx`
- [x] Formatação profissional (bordas, cores, headers)
- [x] Cálculo de totais
- [x] Ajuste automático de colunas
- [x] Download no frontend

**Status:** ✅ MVP Completo  
**Horas:** ~4h

---

### Sprint 0.6: Curva ABC ✅
- [x] Endpoint `/api/curva-abc/{upload_id}`
- [x] Ordenação por valor (Pareto)
- [x] Classificação A (80%), B (15%), C (5%)
- [x] Cálculo de percentuais acumulados
- [x] Página CurvaABC.tsx com gráficos (Recharts)
- [x] Filtros por classificação
- [x] Tabela detalhada
- [x] Resumo estatístico

**Status:** ✅ MVP Completo  
**Horas:** ~8h

---

### Sprint 0.7: Dashboard e UI ⚠️
- [x] Dashboard principal (Dashboard.tsx)
- [x] Sidebar responsiva (SidebarLayout.tsx)
- [x] Página de Relatórios (Reports.tsx)
- [x] Página de Analytics (Analytics.tsx)
- [x] Navegação entre páginas (React Router)
- [x] Componentes reutilizáveis
- [ ] Ajustes finais de UX (pendente)

**Status:** ⚠️ 50% - UI feita, falta ajustes  
**Horas:** ~3h  
**Pendente:** Refinamentos de UX (3h para MVP)
43h - 1,5 semanas)

### Sprint 1.0: Completar Features Parciais (21h)
**Objetivo:** Finalizar funcionalidades já iniciadas do MVP

#### Sprint 1.0.1: Processamento PDF Refinado (5h)
**Objetivo:** Melhorar detecção e parse de colunas

##### Backend (3h)
- [ ] Melhorar algoritmo de detecção de colunas (2h)
  - [ ] Detectar colunas por posição e alinhamento
  - [ ] Melhorar identificação de headers
  - [ ] Suporte para diferentes layouts de tabela
  
- [ ] Tratamento de erros mais robusto (1h)
  - [ ] Fallbacks quando parse falha
  - [ ] Mensagens de erro mais claras

##### Testes (2h)
- [ ] Testar com 10+ PDFs diferentes
- [ ] Validar taxa de acerto > 85%

**Entregável:** Extração confiável de dados  
**Prioridade:** 🔴 ALTA

---

#### Sprint 1.0.2: Normalização Completa (3h)
**Objetivo:** Validações e refinamentos

##### Backend (2h)
- [ ] Validações automáticas de dados (1h)
  - [ ] Detectar valores zerados
  - [ ] Validar unidades de medida
  - [ ] Alertar sobre inconsistências
  
- [ ] Endpoint `/api/validate` (1h)
  - [ ] Retornar relatório de validação
  - [ ] Sugestões de correção

##### Frontend (1h)
- [ ] Exibir alertas de validação na UI
- [ ] Opções para aceitar/rejeitar sugestões

**Entregável:** Sistema valida dados automaticamente  
#### Sprint 1.0.4: IA Organização Completa (10h)
**Objetivo:** Completar funcionalidades de IA para organização

##### Backend (6h)
- [ ] Completar endpoint `/api/ai/standardize` (2h)
  - [ ] Refinar padronização de descrições
  - [ ] Normalização de unidades
  - [ ] Correção de inconsistências
  
- [ ] Endpoint `/api/ai/identify-similar` (2h)
  - [ ] Algoritmo de similaridade de strings (Levenshtein)
  - [ ] Análise semântica com Gemini
  - [ ] Retornar grupos de itens similares
  
- [ ] Endpoint `/api/ai/suggest-grouping` (2h)
  - [ ] IA categoriza itens por tipo
  - [ ] Sugestões de organização
  - [ ] Retornar categorias

##### Frontend (3h)
- [ ] Botão "Padronizar com IA" (1h)
- [ ] Botão "Identificar Similares" (1h)
- [ ] Modal com sugestões de agrupamento (1h)

##### Testes (1h)
- [ ] Validar precisão das sugestões

**Entregável:** IA detecta e sugere melhorias automaticamente  
**Prioridade:** 🔴 ALTA

---

### Sprint 1.1: Features Novas do MVP (22h)
**Objetivo:** Implementar Orçamento e Propostas

#### Sprint 1.1.1

#### Sprint 1.0.3: Dashboard Ajustes Finais (3h)
**O# Sprint 1.1.2Refinar UX e navegação

##### Frontend (3h)
- [ ] Melhorar navegação entre páginas (1h)
  - [ ] Breadcrumbs
  - [ ] Links contextuais
  
- [ ] Loading states consistentes (1h)
  - [ ] Skeletons
  - [ ] Spinners
  
- [ ] Mensagens de feedback (1h)
  - [ ] Toasts de sucesso/erro
  - [ ] Confirmações de ações

**Entregável:** Experiência de usuário polida

- [ ] Endpoint `/api/ai/suggest-grouping` para categorização
  - [ ] IA categoriza itens por tipo (estrutura, acabamento, etc.)
  - [ ] Sugestões de organização hierárquica
  - [ ] Retornar árvore de categorias (3h)

#### Frontend (4h)
- [ ] Botão "Identificar Similares" na página de validação (1h)
- [ ] Modal com lista de itens similares e ação de merge (2h)
- [ ] Exibição de sugestões de agrupamento (1h)

#### Testes (1h)
- [ ] Testar com planilhas reais
- [ ] Validar precisão das sugestões

**Entregável:** Sistema detecta e sugere melhorias automaticamente  
**Prioridade:** 🔴 ALTA

---

### Sprint 1.2: Orçamento Automático com IA (12h)
**Objetivo:** Gerar orçamento automaticamente com base em tabelas de preço
60h - 1,5 semanas
#### Backend (8h)
- [ ] Base de dados de preços SINAPI/locais
  - [ ] Estrutura de dados (JSON/CSV)
  - [ ] Endpoint `/api/prices/search?item=description` (2h)
  
- [ ] Endpoint `/api/budget/generate/{upload_id}`
  - [ ] Buscar itens extraídos
  - [ ] Consultar base de preços para cada item
  - [ ] IA sugere valores quando não encontrado
  - [ ] Calcular custos totais
  - [ ] Aplicar margens (BDI, lucro)
  - [ ] Retornar orçamento completo (5h)
  
- [ ] Lógica de fallback (quando não achar preço)
  - [ ] IA estima valor baseado em similares (1h)

#### Frontend (3h)
- [ ] Página de Orçamento com visualização (2h)
  - [ ] Tabela de itens com valores sugeridos
  - [ ] Possibilidade de editar valores manualmente
  - [ ] Totais e subtotais
  
- [ ] Botão "Gerar Orçamento" no fluxo principal (1h)

#### Testes (1h)
- [ ] Validar precisão dos valores
- [ ] Testar diferentes tipos de obra

**Entregável:** Orçamento gerado automaticamente com valores reais  
**Prioridade:** 🔴 ALTA

---

### Sprint 1.3: Propostas Comerciais Automáticas (10h)
**Objetivo:** Gerar proposta comercial em PDF automaticamente

#### Backend (6h)
- [ ] Template de proposta (HTML/Jinja2)
  - [ ] Header com logo e dados da empresa
  - [ ] Seção de escopo (texto)
  - [ ] Tabela de itens e valores
  - [ ] Totais, condições de pagamento, prazo
  - [ ] Footer com assinatura (2h)

- [ ] Endpoint `/api/proposals/generate`
  - [ ] Receber dados do orçamento
  - [ ] IA gera texto do escopo baseado nos itens
  - [ ] Preencher template com dados
  - [ ] Gerar PDF com pdfkit/weasyprint
  - [ ] Salvar no Firestore
  - [ ] Retornar URL de download (3h)

- [ ] Endpoint `/api/proposals/{upload_id}` para listar propostas (1h)

#### Frontend (3h)
- [ ] Página de Proposta (Proposal.tsx) (2h)
  - [ ] Preview da proposta
  - [ ] Botão "Gerar Proposta"
  - [ ] Download do PDF
  
- [ ] Integrar no fluxo após orçamento (1h)

#### Testes (1h)
- [ ] Validar formatação do PDF
- [ ] Testar diferentes cenários

**Entregável:** Proposta comercial em PDF gerada automaticamente  
**Prioridade:** 🔴 ALTA

---

## 🔧 FASE 2: ROBUSTEZ E MELHORIAS (40h - 1 semana)

### Sprint 2.1: Dashboard com Dados Reais (14h)
**Objetivo:** Integrar Reports e Analytics com backend real

#### Backend (8h)
- [ ] Endpoint `/api/reports/generate`
  - [ ] Tipos: orçamento, curva-abc, comparativo, financeiro
  - [ ] Geração de PDF com dados reais (4h)
  
- [ ] Endpoint `/api/analytics/dashboard`
  - [ ] KPIs: total, gasto, saldo, taxa de utilização
  - [ ] Dados mensais: orçado vs executado
  - [ ] Distribuição por categoria
  - [ ] Top fornecedores
  - [ ] Variação de preços (4h)

#### Frontend (5h)
- [ ] Reports.tsx integrado com backend real (2h)
  - [ ] Listar relatórios do Firestore
  - [ ] Gerar novos relatórios via API
  
- [ ] Analytics.tsx integrado com backend real (3h)
  - [ ] Buscar dados reais do endpoint
  - [ ] Filtros dinâmicos
  - [ ] Atualização em tempo real

#### Testes (1h)
- [ ] Validar cálculos
- [ ] Performance com grande volume de dados

**Entregável:** Dashboard completo com dados reais  
**Prioridade:** 🟡 MÉDIA

---

### Sprint 2.2: OCR Avançado (12h)
**Objetivo:** Processar PDFs escaneados com OCR

#### Backend (10h)
- [ ] Integração com Tesseract OCR ou Google Vision API
  - [ ] Detecção de PDF escaneado vs texto nativo (2h)
  - [ ] Conversão de imagens em texto (4h)
  - [ ] Pré-processamento de imagem (contraste, rotação) (2h)
  - [ ] Merge com extração de pdfplumber (2h)

- [ ] Endpoint `/api/extract-ocr` separado (opcional)

#### Testes (2h)
- [ ] Testar comExportação Avançada (4h)
**Objetivo:** Múltiplos formatos e templates

#### Backend (3h)
- [ ] Suporte para múltiplos formatos (2h)
  - [ ] XLSX (já existe)
  - [ ] CSV
  - [ ] PDF
  
- [ ] Templates customizáveis (1h)
  - [ ] Salvar preferências de formato
  - [ ] Layout personalizado

#### Frontend (1h)
- [ ] Seletor de formato de exportação
- [ ] Preview antes de exportar

**Entregável:** Exportação flexível  
**Prioridade:** 🟡 MÉDIA

---

### Sprint 2.5: Curva ABC Avançada (8h)
**Objetivo:** Análises e relatórios detalhados

#### Backend (5h)
- [ ] Análises adicionais (3h)5h - 1
  - [ ] Tendências temporais
  - [ ] Comparação entre projetos
  - [ ] Sugestões de otimização
  
- [ ] Relatórios detalhados (2h)
  - [ ] PDF com análise completa
  - [ ] Gráficos exportáveis

#### Frontend (2h)
- [ ] Visualizações adicionais
- [ ] Filtros avançados

#### Testes (1h)
- [ ] Validar cálculos complexos

**Entregável:** Análise ABC completa  
**Prioridade:** 🟡 MÉDIA

---

### Sprint 2.6:  PDFs escaneados de qualidade variável
- [ ] Validar precisão do OCR
- [ ] Benchmark de performance

**Entregável:** Sistema processa PDFs escaneados  
**Prioridade:** 🟡 MÉDIA

---

### Sprint 2.3: Normalização Avançada (5h)
**Objetivo:** Melhorar detecção e correção de inconsistências

#### Backend (3h)
- [ ] Regras de validação automática
  - [ ] Detectar valores zerados ou negati6os
  - [ ] Validar unidades de medida
  - [ ] Identificar descrições duplicadas
  - [ ] Alertar3h)
- [ ] Base de conhecimento de materiais de construção (5h)
  - [ ] Dicionário de sinônimos (ex: "cimento" = "concreto")
  - [ ] Hierarquia de categorias
  - [ ] Relacionamentos entre itens
  
- [ ] Algoritmos de similaridade avançados (5h)
  - [ ] Word embeddings (Word2Vec/BERT)
  - [ ] Análise semântica profunda
  - [ ] Clustering de itens similares
  
- [ ] Correção automática de unidades (3h)
  - [ ] Detectar unidades erradas (ex: "m2" quando deveria ser "m3")
  - [ ] Conversões automáticas
  - [ ] Sugestões de correç

---

### Sprint 2.4: Refinamentos e Testes (9h)
**Objetivo:** Polir experiência do usuário e garantir estabilidade

#### Tasks
- [ ] Tratamento de erros robusto (2h)
  - [ ] Mensagens claras para o usuário
  - [ ] Fallbacks quando APIs falham
  
- [ ] Loading states e feedback visual (2h)
  - [ ] Skeletons durante carregamento
  - [ ] Toasts de sucesso/erro
  
- [ ] Performance optimization (2h)
  - [ ] Caching de respostas
  - [ ] Lazy loading de imagens
  
- [ ] Testes end-to-end (3h)
  - [ ] Fluxo completo: upload → validação → curva ABC → orçamento → proposta
  - [ ] Testes com diferentes tipos de PDF
  - [ ] Validação de edge cases

**Entregável:** Sistema polido e estável  
**Prioridade:** 🟡 MÉDIA

---

## 🎓 FASE 3: FEATURES AVANÇADAS (41h - 1+ semana)

### Sprint 3.1: IA Organização Avançada (15h)
**Objetivo:** Melhorar algoritmos de IA para organização

#### Backend (12h)
- [ ] Base de conhecimento de materiais de construção (4h)
  - [ ] Dicionário de sinônimos (ex: "cimento" = "concreto")
  - [ ] Hierarquia de categorias
  
- [ ] Algoritmos de similaridade avançados (4h)
  - [ ] Word embeddings (Word2Vec/BERT)
  - [ ] Análise semântica profunda
  - [ ] Clustering de itens similares
  
- [ ] Correção automática de unidades (4h)
  - [ ] Detectar unidades erradas (ex: "m2" quando deveria ser "m3")
  - [ ] Sugestões de conversão

#### Frontend (2h)
- [ ] Interface para gerenciar base de conhecimento
- [ ] Visualização de clusters

#### Testes (1h)
- [ ] Validar precisão
- [ ] Benchmark vs versão básica

**Entregável:** IA de organização de alto nível  
**Prioridade:** 🟢 BAIXA

---

### Sprint 3.2: Orçamento Avançado (12h)
**Objetivo:** Múltiplas bases de preços e cenários

#### Backend (9h)
- [ ] Integração com múltiplas bases (5h)
  - [ ] SINAPI
  - [ ] Tabelas locais (por estado)
  - [ ] API de fornecedores reais
  - [ ] Histórico de preços do próprio sistema
  
- [ ] Cenários de orçamento (3h)
  - [ ] Otimista (preços baixos)
  - [ ] Pessimista (preços altos)
  - [ ] Realista (média ponderada)
  
- [ ] Análise de tendências de preço (1h)
  - [ ] Gráficos de evolução de preço por item

#### Frontend (2h)
- [ ] Seletor de base de preços
- [ ] Visualização de cenários lado a lado

#### Testes (1h)
- [ ] Validar cálculos
-ituação Atual: 28h investidas (40% do MVP)

Semana 1-2: FASE 1 - Completar MVP (43h)
├─ Seg-Ter: Sprint 1.0 - Completar Features Parciais (21h)
│  ├─ Processamento PDF (5h)
│  ├─ Normalização (3h)
│  ├─ Dashboard UX (3h)
│  └─ IA Organização (10h)
├─ Qua-Qui: Sprint 1.1.1 - Orçamento IA (12h)
└─ Sex:     Sprint 1.1.2 - Propostas (10h)

Semana 3-4: FASE 2 - Melhorias (60h) - Após Validação
├─ Seg-Ter: Sprint 2.1 - Dashboard Real (14h)
├─ Qua:     Sprint 2.2 - OCR Avançado (12h)
├─ Qui:     Sprint 2.3 - Normalização Avançada (10h)
├─ Sex:     Sprint 2.4 - Exportação Avançada (4h)
│           Sprint 2.5 - Curva ABC Avançada (8h)
└─ Sáb:     Sprint 2.6 - Refinamentos (9h)
            Sprint 2.7 - Processamento Robusto (3h restantes)

Semana 5: FASE 3 - Avançado (45h) - Opcional
├─ Seg-Ter: Sprint 3.1 - IA Avançada (16h)
├─ Qua-Qui: Sprint 3.2 - Orçamento Avançado (12h)
├─ Sex:     Sprint 3.3 - Propostas Avançadas (14h)
└─ Sáb:     Sprint 3.4 - Analytics Avançado (3
- [ ] Editor de proposta (3h)
  - [ ] Salvar rascunhos
  - [ ] Versionamento de propostas
  
- [ ] Assinatura digital (2h)
  - [ ] Integração com DocuSign/Clicksign
  - [ ] Ou geração de hash para verificação

#### Frontend (5h)
- [ ] Editor visual de proposta (3h)
  - [ ] Editar texto do escopo
  - [ ] Ajustar valores manualmente
  - [ ] Preview em tempo real
  
- [ ] Galeria de templates (1h)
  - [ ] Pré-visualização
  - [ ] Seleção
  
- [ ] Fluxo de assinatura (1h)
  - [ ] Enviar para assinatura
  - [ ] Status de assinatura

#### Testes (1h)
- [ ] Validar assinatura
- [ ] Testar diferentes templates

**Entregável:** Sistema completo de propostas  
**Prioridade:** 🟢 BAIXA

---

### Sprint 3.4: Dashboard Analytics Avançado (3h)
**Objetivo:** Filtros complexos e análises

#### Frontend (2h)
- [ ] Filtros avançados (1h)
  - [ ] Múltiplos critérios
  - [ ] Salvamento de filtros
  
- [ ] Exportação de dashboard (1h)
  - [ ] PDF do dashboard completo
  - [ ] Compartilhamento

#### Testes (1h)
- [ ] Validar performance com grandes volumes

**Entregável:** Analytics enterprise-grade  
**Prioridade:** 🟢 BAIXA

---

## 📊 Timeline Visual

```
Situação Atual: 28h investidas (40% do MVP)

Semana 1-2: FASE 1 - Completar MVP (43h)
├─ Seg-Ter: Sprint 1.0 - Completar Features Parciais (21h)
│  ├─ Processamento PDF (5h)
│  ├─ Normalização (3h)
│  ├─ Dashboard UX (3h)
│  └─ IA Organização (10h)
├─ Qua-Qui: Sprint 1.1.1 - Orçamento IA (12h)
└─ Sex:     Sprint 1.1.2 - Propostas (10h)

Semana 3-4: FASE 2 - Melhorias (60h) - Após Validação
├─ Seg-Ter: Sprint 2.1 - Dashboard Real (14h)
├─ Qua:     Sprint 2.2 - OCR Avançado (12h)
├─ Qui:     Sprint 2.3 - Normalização Avançada (10h)
├─ Sex:     Sprint 2.4 - Exportação Avançada (4h)
│           Sprint 2.5 - Curva ABC Avançada (8h)
└─ Sáb:     Sprint 2.6 - Refinamentos (9h)
            Sprint 2.7 - Processamento Robusto (3h restantes)

Semana 5: FASE 3 - Avançado (45h) - Opcional
├─ Seg-Ter: Sprint 3.1 - IA Avançada (16h)
├─ Qua-Qui: Sprint 3.2 - Orçamento Avançado (12h)
├─ Sex:     Sprint 3.3 - Propostas Avançadas (14h)
└─ Sáb:     Sprint 3.4 - Analytics Avançado (3h)
```

---

## 🎯 Definição de Pronto (DoD)

### Para cada Sprint:
- [ ] Código implementado e commitado
- [ ] Testes manuais realizados
- [ ] Documentação atualizada (se aplicável)
- [ ] Deploy em ambiente de staging
- [ ] Revisão de código (se aplicável)
- [ ] Sem erros no console

### Para cada Fase:
- [ ] Todos os sprints concluídos
- [ ] Testes de integração passando
- [ ] Validação com usuário/stakeholder
- [ ] Deploy em produção
- [ ] Documentação de usuário atualizada

---

## 📝 Notas e Dependências

### Dependências Externas
- **Google Gemini API:** Para todas as features de IA
- **Firebase/Firestore:** Para persistência de dados
- **Bases de Preços:** SINAPI ou tabelas locais (CSV/JSON)
- **(Opcional) Google Vision/Tesseract:** Para OCR avançado
- **(Opcional) DocuSign/Clicksign:** Para assinatura digital

### Riscos Identificados
1. **Precisão da IA:** Pode não ser 100% precisa, necessita supervisão humana
2. **Qualidade dos PDFs:** PDFs mal formatados podem dificultar extração
3. **Bases de Preços:** Manter atualizado é trabalhoso
4. **Custo de APIs:** Gemini e outros serviços têm custos por uso

### Mitigações
- Sempre permitir edição manual
- Oferecer fallbacks quando APIs falharem
- Sistema de feedback para melhorar IA ao longo do tempo
- Cache agressivo para reduzir custos

---

## ✅ Checklist de Validação Final (MVP)

Antes de considerar o MVP completo, validar:

- [ ] **Upload:** PDF é carregado e armazenado corretamente
- [ ] **Extração:** Tabelas são extraídas com precisão aceitável (>85%)
- [ ] **Validação:** Usuário pode visualizar e editar dados extraídos
- [ ] **Normalização:** Sistema valida e normaliza dados automaticamente
- [ ] **Exportação:** XLSX é gerado corretamente com formatação profissional
- [ ] **Curva ABC:** Classificação está correta (Pareto 80-15-5)
- [ ] **IA Padronização:** Padroniza descrições e unidades automaticamente
- [ ] **IA Similares:** Detecta itens semelhantes corretamente
- [ ] **IA Agrupamento:** Sugere categorização de itens
- [ ] **Orçamento IA:** Gera valores automaticamente com base em tabelas
- [ ] **Propostas:** PDF de proposta é gerado corretamente com IA
- [ ] **Dashboard:** Listagem e navegação funcionam perfeitamente
- [ ] **UX:** Feedback visual consistente (loading, toasts, erros)
- [ ] **Performance:** Tempo de processamento aceitável (<30s para PDFs médios)
- [ ] **Erros:** Tratamento adequado de erros e feedback ao usuário
- [ ] **Mobile:** Interface responsiva e utilizável em dispositivos móveis

---

**Documento vivo:** Atualizar conforme progresso do projeto  
**Responsável:** Equipe de Desenvolvimento  
**Próxima Revisão:** Após conclusão de cada sprint  
**Última Atualização:** 24/02/2026 - Ajustado para 28h investidas (40% MVP)

### Para cada Fase:
- [ ] Todos os sprints concluídos
- [ ] Testes de integração passando
- [ ] Validação com usuário/stakeholder
- [ ] Deploy em produção
- [ ] Documentação de usuário atualizada

---

## 📝 Notas e Dependências

### Dependências Externas
- **Google Gemini API:** Para todas as features de IA
- **Firebase/Firestore:** Para persistência de dados
- **Bases de Preços:** SINAPI ou tabelas locais (CSV/JSON)
- **(Opcional) Google Vision/Tesseract:** Para OCR avançado
- **(Opcional) DocuSign/Clicksign:** Para assinatura digital

### Riscos Identificados
1. **Precisão da IA:** Pode não ser 100% precisa, necessita supervisão humana
2. **Qualidade dos PDFs:** PDFs mal formatados podem dificultar extração
3. **Bases de Preços:** Manter atualizado é trabalhoso
4. **Custo de APIs:** Gemini e outros serviços têm custos por uso

### Mitigações
- Sempre permitir edição manual
- Oferecer fallbacks quando APIs falharem
- Sistema de feedback para melhorar IA ao longo do tempo
- Cache agressivo para reduzir custos

---

## ✅ Checklist de Validação Final (MVP)

Antes de considerar o MVP completo, validar:

- [ ] **Upload:** PDF é carregado e armazenado corretamente
- [ ] **Extração:** Tabelas são extraídas com precisão aceitável (>80%)
- [ ] **Validação:** Usuário pode visualizar e editar dados extraídos
- [ ] **Exportação:** XLSX é gerado corretamente
- [ ] **Curva ABC:** Classificação está correta (Pareto 80-15-5)
- [ ] **IA Organização:** Detecta itens similares e sugere agrupamentos
- [ ] **Orçamento IA:** Gera valores automaticamente com base em tabelas
- [ ] **Propostas:** PDF de proposta é gerado corretamente
- [ ] **Dashboard:** Listagem e navegação funcionam
- [ ] **Performance:** Tempo de processamento aceitável (<30s para PDFs médios)
- [ ] **Erros:** Tratamento adequado de erros e feedback ao usuário
- [ ] **Mobile:** Interface responsiva e utilizável em dispositivos móveis

---

**Documento vivo:** Atualizar conforme progresso do projeto  
**Responsável:** Equipe de Desenvolvimento  
**Próxima Revisão:** Após conclusão de cada sprint
