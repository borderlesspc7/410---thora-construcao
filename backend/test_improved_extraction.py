"""
Testa a extração melhorada diretamente no código
"""
import sys
sys.path.append('.')

import pdfplumber
from pathlib import Path

# Simular a lógica melhorada
pdf_path = Path(r"c:\Borderless\410\410---thora-construcao\backend\uploads\test-bdi_Doc28.pdf")

tables = []
try:
    with pdfplumber.open(pdf_path) as pdf:
        print(f"📄 Processando PDF: {len(pdf.pages)} página(s)\n")
        
        for page_num, page in enumerate(pdf.pages):
            print(f"--- Página {page_num + 1}: {page.width}x{page.height} ---")
            
            # Estratégia 1: extract_tables() padrão
            page_tables = page.extract_tables()
            
            # Se não encontrou tabelas, tentar com configurações customizadas
            if not page_tables:
                print(f"  Tentando extração com settings customizados...")
                try:
                    page_tables = page.extract_tables({
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                        "snap_tolerance": 5,
                        "join_tolerance": 5,
                        "edge_min_length": 3,
                    })
                except Exception as e:
                    print(f"  Erro na extração customizada: {str(e)}")
            
            # Se ainda não encontrou tabelas, tentar extrair texto estruturado
            if not page_tables:
                print(f"  Tentando extração de texto estruturado...")
                text = page.extract_text()
                if text:
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    if lines:
                        # Criar uma "tabela" com as linhas de texto
                        page_tables = [[[line] for line in lines]]
                        print(f"  Extraído {len(lines)} linhas de texto")
            
            if page_tables:
                for table_idx, table in enumerate(page_tables):
                    # Processar células mescladas (None) e limpar dados
                    processed_rows = []
                    for row in table:
                        processed_row = []
                        for cell in row:
                            # Converter None para string vazia
                            if cell is None:
                                processed_row.append("")
                            # Limpar espaços extras e quebras de linha
                            elif isinstance(cell, str):
                                cleaned = cell.strip().replace('\n', ' ')
                                processed_row.append(cleaned)
                            else:
                                processed_row.append(str(cell))
                        processed_rows.append(processed_row)
                    
                    tables.append({
                        "page": page_num + 1,
                        "table_id": f"page_{page_num}_table_{table_idx}",
                        "rows": processed_rows,
                        "original_rows": len(table),
                        "columns": len(table[0]) if table else 0
                    })
                    print(f"  ✓ Tabela {table_idx + 1}: {len(processed_rows)} linhas x {len(table[0]) if table else 0} colunas")
                    
                    # Mostrar primeiras 5 linhas processadas
                    print(f"\n  Primeiras 5 linhas processadas:")
                    for i, row in enumerate(processed_rows[:5]):
                        print(f"    {i+1}: {row}")
                    print()
            else:
                print(f"  ⚠️  Nenhuma tabela encontrada na página {page_num + 1}\n")

    print(f"\n{'='*80}")
    print(f"✅ TOTAL: {len(tables)} tabela(s) extraída(s)")
    print(f"{'='*80}\n")
    
    # Salvar resultado em JSON para inspecionar
    import json
    output_file = "test_extraction_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({"tables": tables, "total": len(tables)}, f, ensure_ascii=False, indent=2)
    print(f"💾 Resultado salvo em: {output_file}")
                
except Exception as e:
    print(f"❌ Erro ao extrair tabelas: {str(e)}")
    import traceback
    traceback.print_exc()
