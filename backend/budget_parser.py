"""
Parser inteligente para planilhas orçamentárias
Extrai e normaliza dados de tabelas de orçamento sem depender de IA
"""

import re
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class BudgetParser:
    """Parser robusto para extração de dados de orçamentos"""
    
    # Palavras-chave para identificar colunas
    DESCRICAO_KEYWORDS = [
        'descrição', 'descricao', 'description', 'descr', 'serviço', 'servico',
        'do serviço', 'do servico', 'material', 'especificação', 'especificacao',
    ]
    QUANTIDADE_KEYWORDS = [
        'qtd', 'quant', 'quantidade', 'quantity', 'qty', 'qtde',
        'qtde. máxima', 'qtde máxima', 'qtde maxima', 'qtde. maxima',
    ]
    UNIDADE_KEYWORDS = ['un', 'und', 'unid', 'unidade', 'unit', 'u.', 'unid.']
    VALOR_KEYWORDS = [
        'valor', 'price', 'preço', 'preco', 'unitário', 'unitario', 'unit', 'v.unit',
        'preço unit', 'preco unit', 'p. unit', 'p.unit', 'valor unit',
    ]
    TOTAL_KEYWORDS = ['total', 'v.total', 'valor total', 'amount', 'preço total', 'preco total']
    CODIGO_KEYWORDS = ['código', 'codigo', 'code', 'ref', 'referência', 'referencia']
    BDI_KEYWORDS = ['bdi', '% bdi', 'encargos']
    
    # Palavras para ignorar (linhas de totalizações)
    IGNORE_KEYWORDS = ['total geral', 'subtotal', 'total:', 'suma', 'resumen', 'grand total']
    
    def __init__(self):
        self.confidence = 0.0
        self.structure = {}
    
    def parse_number(self, value: Any) -> float:
        """Converte string em número, tratando formatos brasileiros"""
        if value is None or value == "":
            return 0.0
        
        if isinstance(value, (int, float)):
            return float(value)
        
        # String
        s = str(value).strip()
        
        # Remover símbolos de moeda
        s = s.replace('R$', '').replace('$', '').strip()
        
        # Remover espaços
        s = s.replace(' ', '')
        
        # Se tem vírgula e ponto, assume formato brasileiro (1.234,56)
        if '.' in s and ',' in s:
            # Remover pontos (separador de milhar)
            s = s.replace('.', '')
            # Converter vírgula em ponto
            s = s.replace(',', '.')
        # Se tem apenas vírgula, assume decimal
        elif ',' in s and '.' not in s:
            s = s.replace(',', '.')
        
        try:
            return float(s)
        except (ValueError, AttributeError):
            return 0.0
    
    def is_header_row(self, row: List[Any]) -> bool:
        """Verifica se a linha é um cabeçalho"""
        if not row:
            return False
        
        # Converte para texto minúsculo
        row_text = ' '.join(str(cell).lower() for cell in row if cell)
        
        # Conta quantas palavras-chave de cabeçalho aparecem
        keyword_count = 0
        all_keywords = (
            self.DESCRICAO_KEYWORDS
            + self.QUANTIDADE_KEYWORDS
            + self.UNIDADE_KEYWORDS
            + self.VALOR_KEYWORDS
            + self.CODIGO_KEYWORDS
            + self.BDI_KEYWORDS
        )

        for keyword in all_keywords:
            if keyword in row_text:
                keyword_count += 1

        has_codigo = any(k in row_text for k in self.CODIGO_KEYWORDS)
        has_qtd = any(k in row_text for k in self.QUANTIDADE_KEYWORDS)
        has_desc = any(k in row_text for k in self.DESCRICAO_KEYWORDS)
        has_val = any(k in row_text for k in self.VALOR_KEYWORDS)

        if has_codigo and (has_qtd or has_desc or has_val):
            return True
        return keyword_count >= 2
    
    def should_ignore_row(self, row: List[Any]) -> bool:
        """Verifica se a linha deve ser ignorada"""
        if not row:
            return True
        
        row_text = ' '.join(str(cell).lower() for cell in row if cell).strip()
        
        # Ignorar linhas vazias
        if not row_text:
            return True
        
        # Ignorar totalizações
        for keyword in self.IGNORE_KEYWORDS:
            if keyword in row_text:
                return True
        
        # NÃO ignorar items com códigos hierárquicos (ex: "1.1", "1.1.1")
        # Estes são justamente os items principais do orçamento!
        
        return False
    
    def identify_columns(self, header_row: List[Any]) -> Dict[str, int]:
        """Identifica os índices das colunas importantes"""
        structure = {
            'codigo': -1,
            'descricao': -1,
            'quantidade': -1,
            'unidade': -1,
            'valor_unitario': -1,
            'valor_total': -1,
            'bdi': -1,
        }

        for idx, cell in enumerate(header_row):
            cell_lower = str(cell).lower().strip()
            
            if structure['codigo'] == -1:
                for keyword in self.CODIGO_KEYWORDS:
                    if keyword in cell_lower:
                        structure['codigo'] = idx
                        break

            if structure['bdi'] == -1:
                for keyword in self.BDI_KEYWORDS:
                    if keyword in cell_lower:
                        structure['bdi'] = idx
                        break

            if structure['descricao'] == -1:
                for keyword in self.DESCRICAO_KEYWORDS:
                    if keyword in cell_lower:
                        structure['descricao'] = idx
                        break
            
            if structure['quantidade'] == -1:
                for keyword in self.QUANTIDADE_KEYWORDS:
                    if keyword in cell_lower:
                        structure['quantidade'] = idx
                        break
                if structure['quantidade'] == -1 and 'qtde' in cell_lower and 'mín' not in cell_lower and 'min' not in cell_lower:
                    structure['quantidade'] = idx
            
            if structure['unidade'] == -1:
                for keyword in self.UNIDADE_KEYWORDS:
                    if keyword in cell_lower:
                        structure['unidade'] = idx
                        break
            
            if structure['valor_unitario'] == -1:
                for keyword in self.VALOR_KEYWORDS:
                    if keyword in cell_lower and 'total' not in cell_lower:
                        structure['valor_unitario'] = idx
                        break
            
            if structure['valor_total'] == -1:
                for keyword in self.TOTAL_KEYWORDS:
                    if keyword in cell_lower:
                        structure['valor_total'] = idx
                        break
        
        return structure
    
    def guess_columns_from_data(self, rows: List[List[Any]]) -> Dict[str, int]:
        """Tenta adivinhar colunas analisando os dados (fallback)"""
        if not rows or len(rows) < 2:
            return {}
        
        structure = {
            'descricao': -1,
            'quantidade': -1,
            'unidade': -1,
            'valor_unitario': -1,
            'valor_total': -1
        }
        
        num_cols = max(len(row) for row in rows)
        
        # Heurística: descrição geralmente é a coluna mais larga com texto
        text_lengths = [0] * num_cols
        numeric_counts = [0] * num_cols
        
        for row in rows[:10]:  # Analisa primeiras 10 linhas
            for idx, cell in enumerate(row):
                if idx < num_cols:
                    cell_str = str(cell).strip()
                    text_lengths[idx] += len(cell_str)
                    
                    # Conta células numéricas
                    if self.parse_number(cell) > 0:
                        numeric_counts[idx] += 1
        
        # Descrição: coluna com mais texto
        if text_lengths:
            structure['descricao'] = text_lengths.index(max(text_lengths))
        
        # Colunas numéricas (quantidade, valores)
        numeric_cols = [i for i, count in enumerate(numeric_counts) if count > len(rows) * 0.3]
        
        if numeric_cols:
            # Assume: quantidade, valor_unitario, valor_total
            if len(numeric_cols) >= 1:
                structure['quantidade'] = numeric_cols[0]
            if len(numeric_cols) >= 2:
                structure['valor_unitario'] = numeric_cols[-2]
            if len(numeric_cols) >= 3:
                structure['valor_total'] = numeric_cols[-1]
        
        # Unidade geralmente está perto de quantidade
        if structure['quantidade'] != -1:
            structure['unidade'] = structure['quantidade'] + 1
        
        return structure
    
    def parse_table(self, rows: List[List[Any]], page: int = 0) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Parseia uma tabela de orçamento
        
        Returns:
            (items, structure): Lista de itens extraídos e estrutura detectada
        """
        items = []
        structure = {}
        
        if not rows or len(rows) < 2:
            return items, structure
        
        # 1. Tentar identificar cabeçalho - procurar nas primeiras linhas
        header_idx = -1
        for idx, row in enumerate(rows[:25]):
            if self.is_header_row(row):
                structure = self.identify_columns(row)
                if structure.get('descricao', -1) != -1 or structure.get('codigo', -1) != -1:
                    header_idx = idx
                    logger.info(f"📋 Cabeçalho detectado na linha {idx}: {structure}")
                    break
        
        # 2. Se não encontrou cabeçalho, tenta adivinhar
        if header_idx == -1:
            logger.warning("⚠️ Cabeçalho não encontrado, tentando adivinhar estrutura...")
            structure = self.guess_columns_from_data(rows)
            header_idx = 0
        
        # 3. Verificar se estrutura é válida
        if structure.get('descricao', -1) == -1 and structure.get('codigo', -1) == -1:
            logger.warning("⚠️ Não foi possível identificar colunas de descrição/código")
            return items, structure
        
        # 4. Extrair itens
        for idx, row in enumerate(rows[header_idx + 1:], start=header_idx + 1):
            if self.should_ignore_row(row):
                continue
            
            try:
                # Extrair valores
                codigo = ""
                if structure.get('codigo', -1) >= 0 and structure['codigo'] < len(row):
                    codigo = str(row[structure['codigo']]).strip()

                if structure.get('descricao', -1) >= 0 and structure['descricao'] < len(row):
                    descricao = str(row[structure['descricao']]).strip()
                else:
                    descricao = ""
                if not descricao and codigo:
                    descricao = codigo
                elif descricao and codigo and codigo not in descricao:
                    descricao = f"{codigo} — {descricao}"

                quantidade = self.parse_number(row[structure['quantidade']]) if structure['quantidade'] >= 0 and structure['quantidade'] < len(row) else 0
                unidade = str(row[structure['unidade']]).strip() if structure['unidade'] >= 0 and structure['unidade'] < len(row) else "un"
                valor_unitario = self.parse_number(row[structure['valor_unitario']]) if structure['valor_unitario'] >= 0 and structure['valor_unitario'] < len(row) else 0

                if structure['valor_total'] >= 0 and structure['valor_total'] < len(row):
                    valor_total = self.parse_number(row[structure['valor_total']])
                else:
                    valor_total = quantidade * valor_unitario

                if not descricao or len(descricao) < 3:
                    continue

                if quantidade <= 0 and valor_unitario <= 0 and valor_total <= 0:
                    continue

                items.append({
                    'id': f'item_{page}_{idx}',
                    'codigo': codigo,
                    'descricao': descricao,
                    'quantidade': quantidade,
                    'unidade': unidade or 'un',
                    'valor_unitario': valor_unitario,
                    'valor_total': valor_total if valor_total > 0 else quantidade * valor_unitario,
                    'status': 'validado',
                    'origem': f'página {page}, linha {idx}'
                })
            
            except (IndexError, ValueError, TypeError) as e:
                logger.debug(f"Erro ao processar linha {idx}: {e}")
                continue
        
        logger.info(f"✅ Extraídos {len(items)} itens da página {page}")
        return items, structure
    
    def parse_all_tables(self, tables: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parseia todas as tabelas extraídas do PDF
        
        Args:
            tables: Lista de dicionários com 'page', 'rows', etc
        
        Returns:
            Dicionário com items, resumo e estrutura
        """
        all_items = []
        structures = []
        
        # Detectar tabelas de orçamento sintético vs. composições detalhadas
        priority_tables = []
        other_tables = []
        
        for table in tables:
            rows = table.get('rows', [])
            # Verificar se tem "orçamento sintético" nas primeiras linhas
            has_orcamento_sintetico = False
            for row in rows[:3]:
                row_text = ' '.join(str(cell).lower() for cell in row if cell)
                if 'orçamento sintético' in row_text or 'orcamento sintetico' in row_text:
                    has_orcamento_sintetico = True
                    break
            
            if has_orcamento_sintetico:
                priority_tables.append(table)
                logger.info(f"📊 Tabela prioritária detectada (Orçamento Sintético) na página {table.get('page', 0)}")
            else:
                other_tables.append(table)
        
        # Processar tabelas prioritárias primeiro
        tables_to_process = priority_tables if priority_tables else other_tables
        
        for table in tables_to_process:
            page = table.get('page', 0)
            rows = table.get('rows', [])
            
            items, structure = self.parse_table(rows, page)
            all_items.extend(items)
            if structure:
                structures.append(structure)
        
        # Filtrar items de baixo valor (provavelmente composições internas)
        # Items principais geralmente têm valor total > R$ 10
        MIN_VALUE_THRESHOLD = 10.0
        
        main_items = [item for item in all_items if item['valor_total'] >= MIN_VALUE_THRESHOLD]
        low_value_items = [item for item in all_items if item['valor_total'] < MIN_VALUE_THRESHOLD]
        
        # Se temos items principais, usar apenas eles. Senão, usar todos.
        final_items = main_items if main_items else all_items
        
        logger.info(f"📊 Total de items extraídos: {len(all_items)}")
        logger.info(f"📊 Items principais (≥ R$ {MIN_VALUE_THRESHOLD}): {len(main_items)}")
        logger.info(f"📊 Items de baixo valor: {len(low_value_items)}")
        
        # Calcular resumo
        total_value = sum(item['valor_total'] for item in final_items)
        
        return {
            'status': 'success',
            'items': final_items,
            'resumo': {
                'total_items': len(final_items),
                'valor_total': total_value,
                'confianca': 0.85 if structures else 0.5,
                'metodo': 'parser_deterministico'
            },
            'estruturas_detectadas': structures
        }

