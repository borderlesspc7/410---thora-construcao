import base64
import fitz
import camelot

def test_camelot_fitz(pdf_path):
    tables = camelot.read_pdf(pdf_path, pages='1-3', flavor='lattice')
    print(f"Found {len(tables)} tables")
    
    doc = fitz.open(pdf_path)
    
    for idx, table in enumerate(tables):
        print(f"Table {idx}: page {table.page}, bbox {table._bbox}")
        
        page_num = int(table.page) - 1
        page = doc[page_num]
        
        x0, y0, x1, y1 = table._bbox
        
        # Convert coordinates
        rect = fitz.Rect(x0, page.rect.height - y1, x1, page.rect.height - y0)
        
        # Render image
        pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        print(f"Base64 length: {len(b64)}")

if __name__ == "__main__":
    import sys
    test_camelot_fitz(sys.argv[1])
