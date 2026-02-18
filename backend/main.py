from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import uuid
import logging
from pathlib import Path
from typing import List, Dict
import json

import httpx
from pydantic import BaseModel, Field

from config import (
    FRONTEND_URLS,
    API_TITLE,
    API_VERSION,
    API_DESCRIPTION,
    UPLOAD_FOLDER,
    MAX_FILE_SIZE,
    TEMP_FOLDER,
    BASE_DIR,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)
from firebase_service import OrcamentoFirestore

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    Workbook = None

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description=API_DESCRIPTION,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_URLS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== STATIC FILES (FRONTEND) ==============
# Servir arquivos estáticos do frontend build
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    logger.info(f"✅ Frontend dist encontrado: {FRONTEND_DIST}")
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False), name="assets")
else:
    logger.warning(f"⚠️  Frontend dist não encontrado: {FRONTEND_DIST}")

# ============== HEALTH CHECK ==============
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "version": API_VERSION,
    }

# ============== TEST ==============
@app.get("/api/test")
async def test_endpoint():
    """Test endpoint to verify API is working"""
    return {
        "message": "✅ Backend está funcionando!",
        "timestamp": datetime.now().isoformat(),
    }

# ============== AI STANDARDIZATION ==============
class AIItem(BaseModel):
    descricao: str
    quantidade: float
    unidade: str
    valor_unitario: float
    valor_total: float


class AIStandardizeRequest(BaseModel):
    items: List[AIItem] = Field(default_factory=list)


@app.post("/api/ai/standardize")
async def ai_standardize_items(payload: AIStandardizeRequest):
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY não configurada",
        )

    system_message = (
        "Você é um assistente de normalização de dados de orçamento. "
        "Padronize descrições e unidades de medida, mantendo quantidades e valores. "
        "Retorne apenas JSON válido com uma lista de itens."
    )
    user_message = {
        "tarefa": "padronizar_itens",
        "regras": {
            "unidades": ["un", "m", "m2", "m3", "kg", "t", "l"],
            "manter_campos": ["quantidade", "valor_unitario", "valor_total"],
        },
        "items": [item.model_dump() for item in payload.items],
        "formato_retorno": {
            "items": [
                {
                    "descricao": "string",
                    "quantidade": 0,
                    "unidade": "string",
                    "valor_unitario": 0,
                    "valor_total": 0,
                }
            ]
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": json.dumps(user_message)},
                    ],
                },
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Erro na OpenAI: {response.text}",
            )

        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:].strip()

        parsed = json.loads(content)
        items = parsed.get("items") if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            raise ValueError("Resposta de IA inválida")

        return {
            "status": "success",
            "items": items,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"❌ Erro ao padronizar itens com IA: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao processar padronização com IA",
        )

# ============== UPLOAD PDF ==============
@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload de arquivo PDF
    
    Returns:
        {
            "status": "success",
            "upload_id": "uuid",
            "filename": "documento.pdf",
            "size": 1234567,
            "message": "Arquivo recebido com sucesso"
        }
    """
    try:
        # Validar tipo de arquivo
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=400,
                detail="❌ Apenas arquivos PDF são permitidos",
            )
        
        # Validar tamanho (50MB)
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"❌ Arquivo muito grande. Máximo: 50MB. Seu arquivo tem: {len(contents) / 1024 / 1024:.2f}MB",
            )
        
        # Gerar ID único
        upload_id = str(uuid.uuid4())
        file_path = UPLOAD_FOLDER / f"{upload_id}_{file.filename}"
        
        # Salvar arquivo
        with open(file_path, "wb") as buffer:
            buffer.write(contents)
        
        logger.info(f"✅ PDF salvo: {file_path} ({len(contents) / 1024 / 1024:.2f}MB)")
        
        return {
            "status": "success",
            "upload_id": upload_id,
            "filename": file.filename,
            "size": len(contents),
            "message": "✅ Arquivo recebido com sucesso",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro no upload: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao fazer upload: {str(e)}",
        )

# ============== EXTRACT PDF ==============
@app.post("/api/extract")
async def extract_pdf(upload_id: str):
    """
    Extrai tabelas do PDF usando pdfplumber
    Salva dados no Firestore e deleta arquivo PDF
    
    Args:
        upload_id: ID retornado pelo endpoint /api/upload
    
    Returns:
        {
            "status": "success",
            "upload_id": "uuid",
            "document_id": "firestore_doc_id",
            "tables_found": 1,
            "tables": [...]
        }
    """
    try:
        if not pdfplumber:
            raise HTTPException(
                status_code=500,
                detail="pdfplumber não está instalado",
            )
        
        # Encontrar arquivo
        files = list(UPLOAD_FOLDER.glob(f"{upload_id}_*"))
        if not files:
            raise HTTPException(
                status_code=404,
                detail=f"❌ Upload não encontrado: {upload_id}",
            )
        
        file_path = files[0]
        filename = file_path.name
        
        # Extrair tabelas
        tables = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_tables = page.extract_tables()
                    if page_tables:
                        for table_idx, table in enumerate(page_tables):
                            tables.append({
                                "page": page_num + 1,
                                "table_id": f"page_{page_num}_table_{table_idx}",
                                "rows": table
                            })
        except Exception as e:
            logger.error(f"❌ Erro ao extrair tabelas: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao extrair tabelas: {str(e)}",
            )
        
        logger.info(f"✅ {len(tables)} tabela(s) extraída(s) de {file_path}")
        
        # Salvar no Firestore
        try:
            doc_id = OrcamentoFirestore.save_orcamento(
                upload_id=upload_id,
                filename=filename,
                tables=tables,
            )
            logger.info(f"✅ Dados salvos no Firestore: {doc_id}")
        except Exception as e:
            logger.error(f"❌ Erro ao salvar no Firestore: {str(e)}")
            # Continuar mesmo se Firestore falhar, dados extraídos ainda serão retornados
            doc_id = None
        
        # Deletar arquivo PDF
        try:
            file_path.unlink()
            logger.info(f"🗑️  PDF deletado: {file_path}")
        except Exception as e:
            logger.warning(f"⚠️  Erro ao deletar PDF: {str(e)}")
        
        return {
            "status": "success",
            "upload_id": upload_id,
            "document_id": doc_id,
            "filename": filename,
            "tables_found": len(tables),
            "tables": tables,
            "message": "✅ Dados extraídos e persistidos com sucesso"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro na extração: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )

# ============== FIRESTORE OPERATIONS ==============

@app.get("/api/orcamentos")
async def list_orcamentos():
    """
    Listar todos os orçamentos salvos no Firestore
    
    Returns:
        {
            "status": "success",
            "count": 5,
            "orcamentos": [...]
        }
    """
    try:
        orcamentos = OrcamentoFirestore.list_all_orcamentos()
        return {
            "status": "success",
            "count": len(orcamentos),
            "orcamentos": orcamentos,
        }
    except Exception as e:
        logger.error(f"❌ Erro ao listar orçamentos: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao listar orçamentos: {str(e)}",
        )

@app.get("/api/orcamentos/{upload_id}")
async def get_orcamento(upload_id: str):
    """
    Recuperar orçamento específico do Firestore
    
    Args:
        upload_id: Upload ID
    
    Returns:
        {
            "status": "success",
            "orcamento": {...}
        }
    """
    try:
        orcamento = OrcamentoFirestore.get_orcamento_by_upload_id(upload_id)
        
        if not orcamento:
            raise HTTPException(
                status_code=404,
                detail=f"❌ Orçamento não encontrado: {upload_id}",
            )
        
        return {
            "status": "success",
            "orcamento": orcamento,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao recuperar orçamento: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao recuperar orçamento: {str(e)}",
        )

# ============== EXPORT XLSX ==============
@app.post("/api/export-xlsx")
async def export_xlsx(items: List[Dict]):
    """
    Exporta itens da planilha para arquivo XLSX
    
    Args:
        items: Lista de itens [
            {
                "id": 1,
                "code": "001",
                "description": "Item",
                "unit": "un",
                "qty": 10,
                "unitPrice": 100.00
            }
        ]
    
    Returns:
        arquivo XLSX para download
    """
    try:
        if not Workbook:
            raise HTTPException(
                status_code=500,
                detail="openpyxl não está instalado",
            )
        
        # Criar workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Orçamento"
        
        # Estilos
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        total_fill = PatternFill(start_color="E8F4F8", end_color="E8F4F8", fill_type="solid")
        total_font = Font(bold=True, size=11)
        currency_fill = PatternFill(start_color="F0F8FF", end_color="F0F8FF", fill_type="solid")
        
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # Cabeçalho
        headers = ["Código", "Descrição", "Unidade", "Quantidade", "Valor Unitário", "Total"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border
        
        # Dados
        total_geral = 0
        for row_num, item in enumerate(items, 2):
            ws.cell(row=row_num, column=1).value = item.get("code", "")
            ws.cell(row=row_num, column=2).value = item.get("description", "")
            ws.cell(row=row_num, column=3).value = item.get("unit", "")
            
            qty = float(item.get("qty", 0))
            unit_price = float(item.get("unitPrice", 0))
            total = qty * unit_price
            total_geral += total
            
            ws.cell(row=row_num, column=4).value = qty
            ws.cell(row=row_num, column=5).value = unit_price
            ws.cell(row=row_num, column=6).value = total
            
            # Formato moeda para R$
            ws.cell(row=row_num, column=5).number_format = 'R$ #,##0.00'
            ws.cell(row=row_num, column=6).number_format = 'R$ #,##0.00'
            ws.cell(row=row_num, column=6).fill = currency_fill
            
            # Bordas
            for col in range(1, 7):
                ws.cell(row=row_num, column=col).border = border
                ws.cell(row=row_num, column=col).alignment = Alignment(horizontal="right" if col >= 4 else "left")
        
        # Linha de Total
        total_row = len(items) + 3
        ws.cell(row=total_row, column=5).value = "TOTAL GERAL:"
        ws.cell(row=total_row, column=5).font = total_font
        ws.cell(row=total_row, column=5).alignment = Alignment(horizontal="right")
        
        ws.cell(row=total_row, column=6).value = total_geral
        ws.cell(row=total_row, column=6).number_format = 'R$ #,##0.00'
        ws.cell(row=total_row, column=6).fill = total_fill
        ws.cell(row=total_row, column=6).font = total_font
        ws.cell(row=total_row, column=6).border = border
        
        # Ajustar largura das colunas
        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 40
        ws.column_dimensions['C'].width = 12
        ws.column_dimensions['D'].width = 15
        ws.column_dimensions['E'].width = 15
        ws.column_dimensions['F'].width = 15
        
        # Altura do cabeçalho
        ws.row_dimensions[1].height = 25
        
        # Salvar arquivo
        filename = f"orcamento_{uuid.uuid4().hex[:8]}.xlsx"
        file_path = TEMP_FOLDER / filename
        wb.save(file_path)
        
        logger.info(f"✅ XLSX gerado: {file_path}")
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao exportar XLSX: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar Excel: {str(e)}",
        )

# ============== SERVE FRONTEND INDEX (SPA FALLBACK) ==============
@app.get("/{path_name:path}")
async def serve_frontend(path_name: str):
    """
    Serve o frontend para rotas que não são API
    Necessário para SPA (Single Page Application)
    """
    # Se é um arquivo com extensão (CSS, JS, etc), tentar servir como estático
    if "." in path_name and not path_name.startswith("api"):
        return {"error": "File not found"}
    
    # Servir index.html para rotas do frontend
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    
    return {"error": "Frontend not available"}

# ============== RUN ==============
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
