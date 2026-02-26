"""
Teste completo do fluxo de upload e extração usando a API
"""
import requests
import json
from pathlib import Path

# Configurações
API_URL = "http://localhost:8081"
PDF_PATH = r"c:\Users\lucas\Downloads\Doc 28 - Projeto Básico ANEXO XXV_Det. de Taxas de BDI Ref. e Dif. (188086111).pdf"

print("="*80)
print("TESTE COMPLETO: Upload e Extração de PDF")
print("="*80)

# 1. Upload do PDF
print("\n1️⃣ Fazendo upload do PDF...")
try:
    with open(PDF_PATH, 'rb') as f:
        files = {'file': ('Doc28-BDI.pdf', f, 'application/pdf')}
        response = requests.post(f"{API_URL}/api/upload", files=files, timeout=30)
    
    if response.status_code == 200:
        upload_data = response.json()
        upload_id = upload_data['upload_id']
        print(f"✅ Upload realizado com sucesso!")
        print(f"   Upload ID: {upload_id}")
        print(f"   Filename: {upload_data['filename']}")
        print(f"   Size: {upload_data['size'] / 1024 / 1024:.2f} MB")
    else:
        print(f"❌ Erro no upload: {response.status_code}")
        print(response.text)
        exit(1)
except requests.exceptions.ConnectionError:
    print("❌ Não foi possível conectar ao backend. Certifique-se de que está rodando em http://localhost:8081")
    exit(1)
except Exception as e:
    print(f"❌ Erro: {str(e)}")
    exit(1)

# 2. Extrair dados do PDF
print("\n2️⃣ Extraindo dados do PDF...")
try:
    response = requests.post(
        f"{API_URL}/api/extract", 
        params={'upload_id': upload_id},
        timeout=60
    )
    
    if response.status_code == 200:
        extract_data = response.json()
        print(f"✅ Extração realizada com sucesso!")
        print(f"   Tables found: {extract_data['tables_found']}")
        
        # Mostrar resumo de cada tabela
        for i, table in enumerate(extract_data['tables']):
            print(f"\n   📊 Tabela {i+1}:")
            print(f"      Página: {table['page']}")
            print(f"      ID: {table['table_id']}")
            if 'original_rows' in table:
                print(f"      Linhas: {table['original_rows']}")
            else:
                print(f"      Linhas: {len(table['rows'])}")
            if 'columns' in table:
                print(f"      Colunas: {table['columns']}")
            
            # Mostrar primeiras 3 linhas
            print(f"\n      Primeiras 3 linhas:")
            for j, row in enumerate(table['rows'][:3]):
                print(f"        {j+1}: {row}")
        
        # Salvar resultado
        output_file = "api_test_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(extract_data, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Resultado completo salvo em: {output_file}")
        
    else:
        print(f"❌ Erro na extração: {response.status_code}")
        print(response.text)
        exit(1)
        
except Exception as e:
    print(f"❌ Erro: {str(e)}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "="*80)
print("✅ TESTE COMPLETO FINALIZADO COM SUCESSO!")
print("="*80)
