"""
Script para ver conteúdo detalhado das tabelas extraídas
"""
import pdfplumber
import json

pdf_path = r"c:\Users\lucas\Downloads\Doc 28 - Projeto Básico ANEXO XXV_Det. de Taxas de BDI Ref. e Dif. (188086111).pdf"

with pdfplumber.open(pdf_path) as pdf:
    print(f"📄 Extraindo: {pdf_path}\n")
    
    for page_num, page in enumerate(pdf.pages):
        print(f"\n{'='*80}")
        print(f"PÁGINA {page_num + 1}")
        print('='*80)
        
        tables = page.extract_tables()
        
        for table_idx, table in enumerate(tables):
            print(f"\nTabela {table_idx + 1}: {len(table)} linhas x {len(table[0]) if table else 0} colunas\n")
            
            # Mostrar primeiras 10 linhas
            for i, row in enumerate(table[:15]):
                print(f"Linha {i+1}: {row}")
