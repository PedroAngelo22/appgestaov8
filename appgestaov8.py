import os
import shutil
import base64
import hashlib
import re
from datetime import datetime
import streamlit as st
import sqlite3

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

def extract_base_and_revision(filename):
    match = re.match(r"(.+?)(r\d+)v(\d+)", filename, re.IGNORECASE)
    if match:
        base_name = match.group(1)
        rev = match.group(2).lower()
        ver = match.group(3)
        return base_name, rev, ver
    return filename, None, None

def handle_file_versioning(path, filename):
    """
    Implementa a lógica de controle de revisão e versão:
    - Bloqueia envio de arquivo com mesmo nome completo
    - Aceita nova revisão e move a anterior para subpasta
    - Alerta se mesma revisão e versão diferente
    """
    base, rev, ver = extract_base_and_revision(filename)
    existing_files = os.listdir(path)
    same_name = [f for f in existing_files if f == filename]
    if same_name:
        st.error(f"Arquivo '{filename}' já existe. Envio bloqueado.")
        return False

    revision_conflict = [f for f in existing_files if f.startswith(base) and f"{rev}" in f and f != filename]
    if revision_conflict and f"{rev}v" in filename.lower():
        st.warning(f"Já existe arquivo com revisão {rev}. Verifique se está correta antes de enviar.")
        if not st.checkbox("Confirmo que a revisão está correta"):
            return False

    revision_folder = os.path.join(path, base.strip("-") + "_revisoes")
    os.makedirs(revision_folder, exist_ok=True)
    for f in existing_files:
        if f.startswith(base) and f != filename and f"{rev}" in f:
            shutil.move(os.path.join(path, f), os.path.join(revision_folder, f))
            log_action(st.session_state.username, "mover para revisão", f"de {f} para {revision_folder}")
    return True
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

# LOGIN
if not st.session_state.authenticated and not st.session_state.registration_mode and not st.session_state.admin_mode:
    st.subheader("Login")
    login_user = st.text_input("Usuário")
    login_pass = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        result = c.execute("SELECT * FROM users WHERE username=? AND password=?", (login_user, login_pass)).fetchone()
        if result:
            st.session_state.authenticated = True
            st.session_state.username = login_user
            st.rerun()
        else:
            st.error("Credenciais inválidas.")

    if st.button("Registrar novo usuário"):
        st.session_state.registration_mode = True
        st.rerun()

    if st.button("Painel Administrativo"):
        st.session_state.admin_mode = True
        st.rerun()

# REGISTRO
elif st.session_state.registration_mode and not st.session_state.authenticated:
    st.subheader("Registro de Novo Usuário")
    master_pass = st.text_input("Senha Mestra", type="password")
    if st.button("Liberar Acesso"):
        if master_pass == "#Heisenberg7":
            st.session_state.registration_unlocked = True
            st.success("Acesso liberado. Preencha os dados do novo usuário.")
        else:
            st.error("Senha Mestra incorreta.")

    if st.session_state.registration_unlocked:
        new_user = st.text_input("Novo Usuário")
        new_pass = st.text_input("Nova Senha", type="password")
        if st.button("Criar usuário"):
            if c.execute("SELECT * FROM users WHERE username=?", (new_user,)).fetchone():
                st.error("Usuário já existe.")
            else:
                c.execute("INSERT INTO users (username, password, projects, permissions) VALUES (?, ?, ?, ?)",
                          (new_user, new_pass, '', ''))
                conn.commit()
                st.success("Usuário registrado com sucesso.")
                st.session_state.registration_mode = False
                st.session_state.registration_unlocked = False
                st.rerun()

    if st.button("Voltar ao Login"):
        st.session_state.registration_mode = False
        st.session_state.registration_unlocked = False
        st.rerun()

# PAINEL ADMINISTRATIVO
elif st.session_state.admin_mode and not st.session_state.admin_authenticated:
    st.subheader("Autenticação do Administrador")
    master = st.text_input("Senha Mestra", type="password")
    if st.button("Liberar Painel Admin"):
        if master == "#Heisenberg7":
            st.session_state.admin_authenticated = True
            st.success("Acesso concedido.")
            st.rerun()
        else:
            st.error("Senha incorreta.")

elif st.session_state.admin_mode and st.session_state.admin_authenticated:
    st.subheader("Painel Administrativo")

    st.markdown("### ➕ Cadastrar Projeto / Disciplina / Fase")
    novo_proj = st.text_input("Novo Projeto")
    if st.button("Adicionar Projeto") and novo_proj:
        if novo_proj not in st.session_state.projetos_registrados:
            st.session_state.projetos_registrados.append(novo_proj)
            st.success(f"Projeto '{novo_proj}' adicionado.")
        else:
            st.warning("Projeto já existe.")

    nova_disc = st.text_input("Nova Disciplina")
    if st.button("Adicionar Disciplina") and nova_disc:
        if nova_disc not in st.session_state.disciplinas:
            st.session_state.disciplinas.append(nova_disc)
            st.success(f"Disciplina '{nova_disc}' adicionada.")
        else:
            st.warning("Disciplina já existe.")

    nova_fase = st.text_input("Nova Fase")
    if st.button("Adicionar Fase") and nova_fase:
        if nova_fase not in st.session_state.fases:
            st.session_state.fases.append(nova_fase)
            st.success(f"Fase '{nova_fase}' adicionada.")
        else:
            st.warning("Fase já existe.")

    filtro = st.text_input("🔍 Filtrar usuários por nome")
    usuarios = c.execute("SELECT username, projects, permissions FROM users").fetchall()
    usuarios = [u for u in usuarios if filtro.lower() in u[0].lower()] if filtro else usuarios

    for user, projetos_atuais, permissoes_atuais in usuarios:
        st.markdown(f"#### 👤 {user}")
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button(f"Excluir {user}", key=hash_key(f"del_{user}")):
                c.execute("DELETE FROM users WHERE username=?", (user,))
                conn.commit()
                st.success(f"Usuário {user} removido.")
                st.rerun()
        with col2:
            projetos = st.multiselect(f"Projetos ({user})", options=st.session_state.projetos_registrados,
                                      default=projetos_atuais.split(',') if projetos_atuais else [],
                                      key=hash_key(f"proj_{user}"))
            permissoes = st.multiselect(f"Permissões ({user})", options=["upload", "download", "view"],
                                        default=permissoes_atuais.split(',') if permissoes_atuais else [],
                                        key=hash_key(f"perm_{user}"))
            nova_senha = st.text_input(f"Nova senha ({user})", key=hash_key(f"senha_{user}"))
            if st.button(f"Atualizar senha {user}", key=hash_key(f"update_{user}")):
                c.execute("UPDATE users SET password=?, projects=?, permissions=? WHERE username=?",
                          (nova_senha, ','.join(projetos), ','.join(permissoes), user))
                conn.commit()
                st.success(f"Usuário {user} atualizado.")
                st.rerun()

    if st.button("Sair do Painel Admin"):
        st.session_state.admin_authenticated = False
        st.session_state.admin_mode = False
        st.rerun()

# USUÁRIO AUTENTICADO E UPLOAD COM CONTROLE DE VERSÃO
elif st.session_state.authenticated:
    username = st.session_state.username
    user_data = c.execute("SELECT projects, permissions FROM users WHERE username=?", (username,)).fetchone()
    user_projects = user_data[0].split(',') if user_data and user_data[0] else []
    user_permissions = user_data[1].split(',') if user_data and user_data[1] else []

    st.sidebar.markdown(f"🔐 Logado como: **{username}**")
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.rerun()

    if "upload" in user_permissions:
        st.markdown("### ⬆️ Upload de Arquivos")
        with st.form("upload_form"):
            if not user_projects:
                st.warning("Você ainda não tem projetos atribuídos.")
            else:
                project = st.selectbox("Projeto", user_projects)
                discipline = st.selectbox("Disciplina", st.session_state.disciplinas)
                phase = st.selectbox("Fase", st.session_state.fases)
                uploaded_file = st.file_uploader("Escolha o arquivo")

                submitted = st.form_submit_button("Enviar")
                if submitted and uploaded_file:
                    filename = uploaded_file.name
                    path = get_project_path(project, discipline, phase)

                    # Aplica controle de versão
                    if handle_file_versioning(path, filename):
                        file_path = os.path.join(path, filename)
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.read())
                        st.success(f"Arquivo '{filename}' salvo com sucesso.")
                        log_action(username, "upload", file_path)
    # VISUALIZAÇÃO HIERÁRQUICA
    if "download" in user_permissions or "view" in user_permissions:
        st.markdown("### 📂 Navegação por Projetos")

        for proj in sorted(os.listdir(BASE_DIR)):
            proj_path = os.path.join(BASE_DIR, proj)
            if not os.path.isdir(proj_path):
                continue

            with st.expander(f"📁 Projeto: {proj}", expanded=False):
                for disc in sorted(os.listdir(proj_path)):
                    disc_path = os.path.join(proj_path, disc)
                    if not os.path.isdir(disc_path):
                        continue

                    with st.expander(f"📂 Disciplina: {disc}", expanded=False):
                        for fase in sorted(os.listdir(disc_path)):
                            fase_path = os.path.join(disc_path, fase)
                            if not os.path.isdir(fase_path):
                                continue

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
