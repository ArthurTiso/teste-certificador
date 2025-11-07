# app_certificados.py
# Streamlit app to generate certificates in PDF from a template image and an Excel (.xlsx) with a column named 'nome'.
#
# Requirements (put in requirements.txt):
# streamlit
# pillow
# pandas
# openpyxl
# reportlab
#
# How to run:
# 1. Create a virtualenv and install requirements:
#    python -m venv .venv
#    source .venv/bin/activate   (on Windows: .venv\Scripts\activate)
#    pip install -r requirements.txt
# 2. Run the app:
#    streamlit run app_certificados.py
#
# Notes about fonts:
# The script tries to use Arial (arial.ttf). On some systems Arial may not be available.
# If you get an error about the font, place a TTF file (for example arial.ttf or a substitute) in the same
# folder as the app, or adjust FONT_PATH variable below to a valid .ttf file path.

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
import io
import zipfile
import os
import tempfile
from datetime import datetime
import glob
st.set_page_config(page_title="Gerador de Certificados", layout="wide")

st.title("Gerador de Certificados")
st.write("Faça upload do template (PNG/JPG) e do Excel (.xlsx) com coluna a 'nome', seguida dos nomes que deseja")

# Sidebar settings
st.sidebar.header("Configurações")
# --- Fontes disponíveis ---
font_files = glob.glob("fonts/*.ttf")
font_names = [os.path.basename(f) for f in font_files]
if not font_files:
    st.sidebar.warning("Nenhuma fonte encontrada na pasta 'fonts/'.")
    FONT_PATH = "arial.ttf"
else:
    FONT_PATH = os.path.join("fonts", st.sidebar.selectbox("Selecione a fonte", font_names))

default_font_size = st.sidebar.slider("Tamanho de fonte (inicial)", min_value=20, max_value=180, value=48)
max_width_pct = st.sidebar.slider("Largura máxima do nome (% da largura da imagem)", min_value=40, max_value=95, value=80)

# Y position como prct em slider
y_pos_pct = st.sidebar.slider("Posição vertical do nome (percentual da altura)", min_value=0, max_value=100, value=43)

fix_size = st.sidebar.checkbox("Usar tamanho fixo para todos os nomes", value=True)
gerar_pdf_unico = st.sidebar.checkbox("Gerar um único PDF com todos os certificados", value=False)

# Define nome do arquivo
if "output_zip_name" not in st.session_state:
    st.session_state.output_zip_name = f"certificados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

output_zip_name = st.sidebar.text_input(
    "Nome do arquivo de saída", 
    value=st.session_state.output_zip_name,
    key="zip_name_input"
)
st.session_state.output_zip_name = output_zip_name  # salva edição


uploaded_image = st.file_uploader("Upload do template do certificado (PNG/JPG)", type=["png", "jpg", "jpeg"]) 
uploaded_excel = st.file_uploader("Upload do arquivo Excel (.xlsx) com coluna 'nome'", type=["xlsx"]) 

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Pré-visualização do template**")
    preview_placeholder = st.empty()
with col2:
    st.markdown("**Opções Rápidas**")
    centered_checkbox = st.checkbox("Centralizar horizontalmente (recomendado)", value=True)
    generate_btn = st.button("Gerar certificados")



# Utilities

def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype("arial.ttf", size)
        except Exception:
            return ImageFont.load_default()


# Font utilities

def load_font(font_path, size):
    """Tenta carregar a fonte especificada. Se falhar, tenta Arial. Se falhar novamente, usa a fonte padrão."""
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        try:
            return ImageFont.truetype("arial.ttf", size)
        except OSError:
            return ImageFont.load_default()


def fit_text_to_width(draw, text, font_path, initial_font_size, max_width):
    """Ajusta o tamanho da fonte para que o texto caiba na largura especificada."""
    font_size = initial_font_size
    while font_size > 1:
        font = load_font(font_path, font_size)
        try:
            # Pillow 10+
            bbox = draw.textbbox((0, 0), text, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            # Pillow <10
            w, h = draw.textsize(text, font=font)

        if w <= max_width:
            return font, (w, h)
        font_size -= 1
    return font, (w, h)



if uploaded_image is not None:
    image = Image.open(uploaded_image).convert("RGBA")
    base_preview = image.copy().convert("RGBA")
    draw_prev = ImageDraw.Draw(base_preview)
    W, H = base_preview.size

    # Texto de exemplo
    exemplo_nome = "NOME DO ALUNO"
    y_prev = int(H * (y_pos_pct / 100.0))
    max_w_prev = int(W * (max_width_pct / 100.0))

    if fix_size:
        font_prev = load_font(FONT_PATH or "arial.ttf", default_font_size)
        bbox = draw_prev.textbbox((0, 0), exemplo_nome, font=font_prev)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    else:
        font_prev, (text_w, text_h) = fit_text_to_width(
            draw_prev, exemplo_nome, FONT_PATH if FONT_PATH.strip() != "" else "arial.ttf",
            default_font_size, max_w_prev
        )

    x_prev = (W - text_w) // 2
    draw_prev.text((x_prev, y_prev), exemplo_nome, font=font_prev, fill=(0, 0, 0, 255))

    preview_placeholder.image(base_preview, use_container_width=True)


if generate_btn:
    if uploaded_image is None or uploaded_excel is None:
        st.warning("Por favor envie o template e o arquivo Excel (.xlsx) antes de gerar.")
    else:
        try:
            df = pd.read_excel(uploaded_excel)
        except Exception as e:
            st.error(f"Erro ao ler o Excel: {e}")
            st.stop()

        if 'nome' not in map(str.lower, df.columns):
            # try to find a column that resembles 'nome'
            cols_lower = [c.lower() for c in df.columns]
            if 'nome' in cols_lower:
                # nothing
                pass
            else:
                st.error("O arquivo Excel precisa ter uma coluna chamada 'nome' (ou nome com caixa alta!).")
                st.stop()

        # Normalize column name to 'nome'
        col_map = {c: c for c in df.columns}
        selected_col = None
        for c in df.columns:
            if c.lower() == 'nome':
                selected_col = c
                break
        if selected_col is None:
            # fallback: pick first column
            selected_col = df.columns[0]
            st.warning(f"A coluna 'nome' não foi encontrada. Usando a primeira coluna: {selected_col}")

        nomes = df[selected_col].astype(str).str.strip().dropna().tolist()
        
        if len(nomes) == 0:
            st.error("Nenhum nome válido encontrado no Excel.")
            st.stop()

        # --- Geração dos certificados ---
        pdf_list = []  # Armazena PDFs individuais em memória
        
        for idx, nome in enumerate(nomes, start=1):
            base = image.copy().convert("RGBA")
            draw = ImageDraw.Draw(base)
            W, H = base.size
        
            y = int(H * (y_pos_pct / 100.0))
            max_w = int(W * (max_width_pct / 100.0))
        
            # --- Fonte ---
            if fix_size:
                font = load_font(FONT_PATH or "arial.ttf", default_font_size)
                bbox = draw.textbbox((0, 0), nome, font=font)
                text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            else:
                font, (text_w, text_h) = fit_text_to_width(
                    draw, nome, FONT_PATH if FONT_PATH.strip() != "" else "arial.ttf",
                    default_font_size, max_w
                )
        
            x = (W - text_w) // 2 if centered_checkbox else int(W * 0.1)
        
            # Texto 
            draw.text((x, y), nome, font=font, fill=(0,0,0,255))
        
            # Salvar como PDF individual
            out_rgb = base.convert('RGB')
            pdf_bytes = io.BytesIO()
            out_rgb.save(pdf_bytes, format='PDF', resolution=300)
            pdf_bytes.seek(0)
            pdf_list.append(pdf_bytes.read())
        
        # --- Unir ou compactar ---
        if gerar_pdf_unico:
            from PyPDF2 import PdfMerger
            merger = PdfMerger()
            for pdf_data in pdf_list:
                merger.append(io.BytesIO(pdf_data))
        
            merged_pdf = io.BytesIO()
            merger.write(merged_pdf)
            merger.close()
            merged_pdf.seek(0)
        
            st.success(f"Gerado um único PDF com {len(nomes)} certificados.")
            st.download_button("Baixar PDF único", data=merged_pdf, file_name="certificados_unificados.pdf", mime="application/pdf")
        
        else:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for idx, nome in enumerate(nomes, start=1):
                    safe_name = "".join([c for c in nome if c.isalnum() or c in (' ', '-', '_')]).rstrip()
                    filename = f"{idx:03d} - {safe_name}.pdf"
                    zipf.writestr(filename, pdf_list[idx-1])
            zip_buffer.seek(0)
        
            st.success(f"Gerados {len(nomes)} certificados — download pronto.")
            st.download_button("Baixar todos os PDFs (.zip)", data=zip_buffer, file_name=output_zip_name, mime='application/zip')


st.markdown("---")
st.caption("Desenvolvido Arthur de Morais com Pillow + Streamlit..")
