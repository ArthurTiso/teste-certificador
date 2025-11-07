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

st.set_page_config(page_title="Gerador de Certificados", layout="wide")

st.title("Gerador de Certificados — Escola")
st.write("Faça upload do template (PNG/JPG) e do Excel (.xlsx) com coluna 'nome'. O app gera PDFs centralizados.")

# Sidebar settings
st.sidebar.header("Configurações")
FONT_PATH = st.sidebar.text_input("Caminho para fonte .ttf (deixe vazio para tentar Arial)", value="arial.ttf")
default_font_size = st.sidebar.slider("Tamanho de fonte (inicial)", min_value=20, max_value=180, value=48)
max_width_pct = st.sidebar.slider("Largura máxima do nome (% da largura da imagem)", min_value=40, max_value=95, value=80)
# Y position as percentage of image height
y_pos_pct = st.sidebar.slider("Posição vertical do nome (percentual da altura)", min_value=0, max_value=100, value=43)
output_zip_name = st.sidebar.text_input("Nome do arquivo ZIP de saída", value=f"certificados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")

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


def fit_text_to_width(draw, text, font_path, initial_font_size, max_width):
    font_size = initial_font_size
    while font_size > 1:
        font = ImageFont.truetype(font_path, font_size)
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
    preview_placeholder.image(image, use_column_width=True)

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
                st.error("O arquivo Excel precisa ter uma coluna chamada 'nome' (ou nome em outra capitalização).")
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

        # Create a temp zip in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for idx, nome in enumerate(nomes, start=1):
                # Open fresh image each iteration
                base = image.copy().convert("RGBA")
                draw = ImageDraw.Draw(base)
                W, H = base.size

                # Determine Y position in pixels from percent
                y = int(H * (y_pos_pct / 100.0))

                # Max width in pixels
                max_w = int(W * (max_width_pct / 100.0))

                # Fit font
                font, (text_w, text_h) = fit_text_to_width(draw, nome, FONT_PATH if FONT_PATH.strip() != "" else "arial.ttf", default_font_size, max_w)

                # X position
                if centered_checkbox:
                    x = (W - text_w) // 2
                else:
                    x = int(W * 0.1)  # 10% from left as fallback

                # Draw text with a slight black shadow for readability
                shadow_offset = 2
                try:
                    draw.text((x+shadow_offset, y+shadow_offset), nome, font=font, fill=(0,0,0,180))
                except Exception:
                    draw.text((x+shadow_offset, y+shadow_offset), nome, font=font, fill=(0,0,0))
                try:
                    draw.text((x, y), nome, font=font, fill=(0,0,0,255))
                except Exception:
                    draw.text((x, y), nome, font=font, fill=(0,0,0))

                # Convert to RGB and save as PDF into BytesIO
                out_rgb = base.convert('RGB')
                pdf_bytes = io.BytesIO()
                # Use high quality by specifying resolution
                out_rgb.save(pdf_bytes, format='PDF', resolution=300)
                pdf_bytes.seek(0)

                # Name the file safely
                safe_name = "".join([c for c in nome if c.isalnum() or c in (' ', '-', '_')]).rstrip()
                filename = f"{idx:03d} - {safe_name}.pdf"
                zipf.writestr(filename, pdf_bytes.read())

        zip_buffer.seek(0)
        st.success(f"Gerados {len(nomes)} certificados — download pronto.")
        st.download_button("Baixar todos os PDFs (.zip)", data=zip_buffer, file_name=output_zip_name, mime='application/zip')

        st.info("Dica: se os nomes estiverem cortados, ajuste o 'Tamanho de fonte (inicial)' ou a 'Posição vertical'.")

st.markdown("---")
st.caption("Desenvolvido com Pillow + Streamlit. Fonte: Arial (se disponível).")
