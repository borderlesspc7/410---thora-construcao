"""
Script para testar extração de PDF com diferentes estratégias
"""
import pdfplumber
import sys
from pathlib import Path

def test_extraction(pdf_path):
    print(f"\n{'='*80}")
    print(f"Testando extração: {pdf_path}")
    print(f"{'='*80}\n")
    
    with pdfplumber.open(pdf_path) as pdf:
        print(f"📄 Total de páginas: {len(pdf.pages)}\n")
        
        for page_num, page in enumerate(pdf.pages):
            print(f"\n--- PÁGINA {page_num + 1} ---")
            print(f"Dimensões: {page.width}x{page.height}")
            
            # Estratégia 1: Extração padrão
            print("\n🔍 Estratégia 1: extract_tables() padrão")
            tables = page.extract_tables()
            print(f"Tabelas encontradas: {len(tables)}")
            if tables:
                for i, table in enumerate(tables):
                    print(f"  Tabela {i+1}: {len(table)} linhas x {len(table[0]) if table else 0} colunas")
                    if table and len(table) > 0:
                        print(f"  Primeira linha: {table[0][:3]}...")
            
            # Estratégia 2: Com settings personalizados
            print("\n🔍 Estratégia 2: extract_tables() com settings")
            try:
                tables_custom = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 5,
                    "join_tolerance": 5,
                    "edge_min_length": 3,
                    "min_words_vertical": 1,
                    "min_words_horizontal": 1,
                })
                print(f"Tabelas encontradas: {len(tables_custom)}")
                if tables_custom:
                    for i, table in enumerate(tables_custom):
                        print(f"  Tabela {i+1}: {len(table)} linhas")
            except Exception as e:
                print(f"Erro: {e}")
            
            # Estratégia 3: extract_text
            print("\n🔍 Estratégia 3: extract_text()")
            text = page.extract_text()
            lines = text.split('\n') if text else []
            print(f"Linhas de texto: {len(lines)}")
            if lines:
                print("Primeiras 5 linhas:")
                for i, line in enumerate(lines[:5]):
                    print(f"  {i+1}: {line[:80]}")
            
            # Estratégia 4: extract_words para análise de layout
            print("\n🔍 Estratégia 4: extract_words()")
            words = page.extract_words()
            print(f"Palavras encontradas: {len(words)}")
            if words:
                print(f"Primeira palavra: {words[0]}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        # Usar o PDF anexado
        pdf_path = r"c:\Users\lucas\Downloads\Doc 28 - Projeto Básico ANEXO XXV_Det. de Taxas de BDI Ref. e Dif. (188086111).pdf"
    
    if not Path(pdf_path).exists():
        print(f"❌ Arquivo não encontrado: {pdf_path}")
        sys.exit(1)
    
    test_extraction(pdf_path)
