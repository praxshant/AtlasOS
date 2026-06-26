import os
import re
import fitz  # PyMuPDF
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from dataclasses import dataclass, asdict

@dataclass
class DocumentChunk:
    text: str
    page: int
    chunk_index: int
    metadata: Dict[str, Any]

def extract_text_from_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts text page-by-page from a PDF using PyMuPDF.
    """
    pages_data = []
    try:
        doc = fitz.open(file_path)
        for page_idx, page in enumerate(doc):
            text = page.get_text()
            # Basic fallback: If page is empty, it might be an image.
            # In a real environment, we'd run OCR here. We'll add a placeholder warning.
            if not text.strip():
                text = f"[Image/Scanned Page - OCR Not Available for page {page_idx + 1}]"
            pages_data.append({
                "page": page_idx + 1,
                "text": text
            })
        doc.close()
    except Exception as e:
        raise RuntimeError(f"Error reading PDF file {file_path}: {e}")
    return pages_data

def extract_text_from_docx(file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts text from a DOCX file using native zip/xml parsing.
    """
    try:
        with zipfile.ZipFile(file_path) as docx:
            xml_content = docx.read('word/document.xml')
            root = ET.fromstring(xml_content)
            
            # Namespace for word processing ML
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            
            # Extract paragraphs
            paragraphs = []
            for para in root.findall('.//w:p', ns):
                texts = [node.text for node in para.findall('.//w:t', ns) if node.text]
                if texts:
                    paragraphs.append("".join(texts))
            
            full_text = "\n".join(paragraphs)
            # Since docx doesn't easily map to physical page numbers, treat entire doc as page 1
            return [{"page": 1, "text": full_text}]
    except Exception as e:
        raise RuntimeError(f"Error reading DOCX file {file_path}: {e}")

def extract_text_from_txt(file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts text from plain text file.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return [{"page": 1, "text": text}]
    except Exception as e:
        raise RuntimeError(f"Error reading text file {file_path}: {e}")

def chunk_text(text: str, page_number: int, start_idx: int = 0, chunk_size: int = 512, overlap: int = 64) -> List[DocumentChunk]:
    """
    Splits text into overlapping semantic chunks of words.
    """
    # Clean up excess whitespace
    clean_text = re.sub(r'\s+', ' ', text).strip()
    words = clean_text.split(' ')
    
    if len(words) <= chunk_size:
        return [DocumentChunk(text=clean_text, page=page_number, chunk_index=start_idx, metadata={})]
    
    chunks = []
    idx = 0
    step = chunk_size - overlap
    
    while idx < len(words):
        chunk_words = words[idx : idx + chunk_size]
        chunk_text_str = " ".join(chunk_words)
        
        chunks.append(DocumentChunk(
            text=chunk_text_str,
            page=page_number,
            chunk_index=start_idx + len(chunks),
            metadata={}
        ))
        
        idx += step
        # Prevent infinite loop if step is somehow 0
        if step <= 0:
            break
            
    return chunks

def process_file(file_path: str, filename: str) -> List[Dict[str, Any]]:
    """
    Identifies the file type, extracts text, chunks it, and returns the chunk list.
    """
    ext = os.path.splitext(filename)[1].lower()
    
    if ext == ".pdf":
        pages = extract_text_from_pdf(file_path)
    elif ext == ".docx":
        pages = extract_text_from_docx(file_path)
    elif ext in [".txt", ".log", ".csv", ".json"]:
        pages = extract_text_from_txt(file_path)
    else:
        # Fallback to text reading for unknown formats
        pages = extract_text_from_txt(file_path)
        
    all_chunks = []
    chunk_index = 0
    
    for page_data in pages:
        page_text = page_data["text"]
        page_num = page_data["page"]
        
        # Skip empty pages
        if not page_text.strip():
            continue
            
        page_chunks = chunk_text(page_text, page_num, start_idx=chunk_index)
        for chunk in page_chunks:
            # Add metadata including provenance
            chunk_dict = asdict(chunk)
            chunk_dict["metadata"] = {
                "source_file": filename,
                "file_type": ext
            }
            all_chunks.append(chunk_dict)
            chunk_index += 1
            
    return all_chunks

def process_document(file_path: str, document_id: Any) -> List[Dict[str, Any]]:
    """
    Compatibility wrapper around process_file that normalizes keys.
    """
    filename = os.path.basename(file_path)
    chunks = process_file(file_path, filename)
    normalized_chunks = []
    for chunk in chunks:
        normalized_chunks.append({
            "text": chunk["text"],
            "page_number": chunk.get("page", 1),
            "chunk_index": chunk["chunk_index"],
            "metadata": chunk.get("metadata", {})
        })
    return normalized_chunks

