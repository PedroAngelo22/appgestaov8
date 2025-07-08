import os
import shutil
import base64
import hashlib
from datetime import datetime
import streamlit as st
import sqlite3
import re

# Banco de dados SQLite
conn = sqlite3.connect('document_manager.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    projects TEXT,
    permissions TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS logs (
    timestamp TEXT,
    user TEXT,
    action TEXT,
    file TEXT
)''')
conn.commit()

BASE_DIR = "uploads"
os.makedirs(BASE_DIR, exist_ok=True)

# Disciplinas, fases e projetos padrão
if "disciplinas" not in st.session_state:
    st.session_state.disciplinas = ["GES", "PRO", "MEC", "MET", "CIV", "ELE", "AEI"]
if "fases" not in st.session_state:
    st.session_state.fases = ["FEL1", "FEL2", "FEL3", "Executivo"]
if "projetos_registrados" not in st.session_state:
    st.session_state.projetos_registrados = []

def get_project_path(project, discipline, phase):
    path = os.path.join(BASE_DIR, project, discipline, phase)
    os.makedirs(path, exist_ok=True)
    return path

def save_versioned_file(file_path):
    if os.path.exists(file_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base, ext = os.path.splitext(file_path)
        versioned_path = f"{base}_v{timestamp}{ext}"
        shutil.move(file_path, versioned_path)

def log_action(user, action, file, note=None):
    log_entry = f"{file} ({note})" if note else file
    c.execute("INSERT INTO logs (timestamp, user, action, file) VALUES (?, ?, ?, ?)",
              (datetime.now().isoformat(), user, action, log_entry))
    conn.commit()

def file_icon(file_name):
    if file_name.lower().endswith(".pdf"):
        return "📄"
    elif file_name.lower().endswith((".jpg", ".jpeg", ".png")):
        return "🖼️"
    else:
        return "📁"

def hash_key(text):
    return hashlib.md5(text.encode()).hexdigest()

def extrair_info_arquivo(nome_arquivo):
    padrao = r"(.+)_r(\d+)v(\d+)\.[\w]+$"
    match = re.match(padrao, nome_arquivo)
    if match:
        nome_base = match.group(1)
        revisao = f"r{match.group(2)}"
        versao = f"v{match.group(3)}"
        return nome_base, revisao, versao
    return None, None, None

# Estado da sessão
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "registration_mode" not in st.session_state:
    st.session_state.registration_mode = False
if "registration_unlocked" not in st.session_state:
    st.session_state.registration_unlocked = False
if "admin_mode" not in st.session_state:
    st.session_state.admin_mode = False
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

st.title("📁 Gerenciador de Documentos Inteligente")

# LOGIN / REGISTRO / PAINEL ADMIN - mantido conforme já implementado
# (suprimido aqui para foco na parte do erro)

# USUÁRIO AUTENTICADO
if st.session_state.authenticated:
    username = st.session_state.username
    user_data = c.execute("SELECT projects, permissions FROM users WHERE username=?", (username,)).fetchone()
    user_projects = user_data[0].split(',') if user_data and user_data[0] else []
    user_permissions = user_data[1].split(',') if user_data and user_data[1] else []

    st.sidebar.markdown(f"🔐 Logado como: **{username}**")
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.rerun()

    # UPLOAD - com controle de versão e revisão
    if "upload" in user_permissions:
        st.markdown("### ⬆️ Upload de Arquivos")
        with st.form("upload_form"):
            if not user_projects:
                st.warning("Você ainda não tem projetos atribuídos. Contate o administrador.")
            else:
                project = st.selectbox("Projeto", user_projects)
                discipline = st.selectbox("Disciplina", st.session_state.disciplinas)
                phase = st.selectbox("Fase", st.session_state.fases)
                uploaded_file = st.file_uploader("Escolha o arquivo")
                confirmar_mesma_revisao = st.checkbox("Confirmo que estou mantendo a mesma revisão e subindo nova versão")

                submitted = st.form_submit_button("Enviar")
                if submitted and uploaded_file:
                    filename = uploaded_file.name
                    path = get_project_path(project, discipline, phase)
                    file_path = os.path.join(path, filename)

                    nome_base, revisao, versao = extrair_info_arquivo(filename)

                    if not nome_base:
                        st.error("O nome do arquivo deve seguir o padrão: NOME-BASE_rXvY.extensão")
                    else:
                        arquivos_existentes = os.listdir(path)
                        nomes_existentes = [f for f in arquivos_existentes if f.startswith(nome_base)]

                        if filename in arquivos_existentes:
                            st.error("Arquivo com este nome completo já existe.")
                        else:
                            revisoes_anteriores = []
                            for f in nomes_existentes:
                                base_ant, rev_ant, ver_ant = extrair_info_arquivo(f)
                                if base_ant == nome_base:
                                    revisoes_anteriores.append((f, rev_ant, ver_ant))

                            existe_revisao_anterior = any(r[1] != revisao for r in revisoes_anteriores)
                            mesma_revisao_outras_versoes = any(r[1] == revisao and r[2] != versao for r in revisoes_anteriores)

                            if existe_revisao_anterior and all(r[1] != revisao for r in revisoes_anteriores):
                                pasta_revisao = os.path.join(path, "Revisoes", nome_base)
                                os.makedirs(pasta_revisao, exist_ok=True)
                                for f, _, _ in revisoes_anteriores:
                                    shutil.move(os.path.join(path, f), os.path.join(pasta_revisao, f))
                                st.info(f"Arquivos da revisão anterior movidos para {pasta_revisao}.")

                            elif mesma_revisao_outras_versoes and not confirmar_mesma_revisao:
                                st.warning("Detectada mesma revisão com versão diferente. Marque a caixa de confirmação para prosseguir.")
                                st.stop()

                            with open(file_path, "wb") as f:
                                f.write(uploaded_file.read())

                            st.success(f"Arquivo '{filename}' salvo com sucesso.")
                            log_action(username, "upload", file_path)

    # VISUALIZAÇÃO HIERÁRQUICA COM EXPANDERS
    if "download" in user_permissions or "view" in user_permissions:
        st.markdown("### 📂 PROJETOS")

        for proj in sorted(os.listdir(BASE_DIR)):
            proj_path = os.path.join(BASE_DIR, proj)
            if not os.path.isdir(proj_path): continue

            with st.expander(f"📁 Projeto: {proj}", expanded=False):
                for disc in sorted(os.listdir(proj_path)):
                    disc_path = os.path.join(proj_path, disc)
                    if not os.path.isdir(disc_path): continue

                    with st.expander(f"📂 Disciplina: {disc}", expanded=False):
                        for fase in sorted(os.listdir(disc_path)):
                            fase_path = os.path.join(disc_path, fase)
                            if not os.path.isdir(fase_path): continue

                            with st.expander(f"📄 Fase: {fase}", expanded=False):
                                for file in sorted(os.listdir(fase_path)):
                                    full_path = os.path.join(fase_path, file)
                                    icon = file_icon(file)
                                    st.markdown(f"- {icon} `{file}`")

                                    with open(full_path, "rb") as f:
                                        b64 = base64.b64encode(f.read()).decode("utf-8")
                                        if file.endswith(".pdf"):
                                            href = f'<a href="data:application/pdf;base64,{b64}" target="_blank">🔍 Visualizar PDF</a>'
                                            if st.button(f"🔍 Abrir PDF ({file})", key=hash_key("btn_" + full_path)):
                                                st.markdown(href, unsafe_allow_html=True)
                                            f.seek(0)
                                            if "download" in user_permissions:
                                                st.download_button("📥 Baixar PDF", f, file_name=file, mime="application/pdf", key=hash_key("dl_" + full_path))
                                        elif file.lower().endswith(('.jpg', '.jpeg', '.png')):
                                            try:
                                                st.image(f.read(), caption=file)
                                            except Exception as e:
                                                st.warning(f"Não foi possível exibir a imagem '{file}': {str(e)}")
                                            f.seek(0)
                                            if "download" in user_permissions:
                                                st.download_button("📥 Baixar Imagem", f, file_name=file, key=hash_key("img_" + full_path))
                                        else:
                                            if "download" in user_permissions:
                                                st.download_button("📥 Baixar Arquivo", f, file_name=file, key=hash_key("oth_" + full_path))

                                    log_action(username, "visualizar", full_path)
    # PESQUISA POR PALAVRA-CHAVE
    if "download" in user_permissions or "view" in user_permissions:
        st.markdown("### 🔍 Pesquisa de Documentos")
        keyword = st.text_input("Buscar por palavra-chave")
        if keyword:
            matched = []
            for root, _, files in os.walk(BASE_DIR):
                for file in files:
                    if keyword.lower() in file.lower():
                        matched.append(os.path.join(root, file))

            if matched:
                for file in matched:
                    st.write(f"📄 {os.path.relpath(file, BASE_DIR)}")
                    with open(file, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                        if file.endswith(".pdf"):
                            href = f'<a href="data:application/pdf;base64,{b64}" target="_blank">🔍 Visualizar PDF</a>'
                            if st.button(f"🔍 Abrir PDF ({file})", key=hash_key("btnk_" + file)):
                                st.markdown(href, unsafe_allow_html=True)
                            f.seek(0)
                            if "download" in user_permissions:
                                st.download_button("📥 Baixar PDF", f, file_name=os.path.basename(file), mime="application/pdf", key=hash_key("dlk_" + file))
                        elif file.lower().endswith(('.jpg', '.jpeg', '.png')):
                            st.image(f.read(), caption=os.path.basename(file))
                            f.seek(0)
                            if "download" in user_permissions:
                                st.download_button("📥 Baixar Imagem", f, file_name=os.path.basename(file), key=hash_key("imgk_" + file))
                        else:
                            if "download" in user_permissions:
                                st.download_button("📥 Baixar Arquivo", f, file_name=os.path.basename(file), key=hash_key("othk_" + file))
                    log_action(username, "visualizar", file)
            else:
                st.warning("Nenhum arquivo encontrado.")

    # HISTÓRICO DE AÇÕES
    st.markdown("### 📜 Histórico de Ações")
    if st.checkbox("Mostrar log"):
        for row in c.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 50"):
            st.write(f"{row[0]} | Usuário: {row[1]} | Ação: {row[2]} | Arquivo: {row[3]}")
