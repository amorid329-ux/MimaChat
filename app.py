from flask import Flask, render_template, request, redirect, session, jsonify
from flask_socketio import SocketIO, emit
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import random
from pathlib import Path

app = Flask(__name__)
app.config["SECRET_KEY"] = "mimachat-secreto-v8-premium"
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["CHAT_UPLOAD_FOLDER"] = "static/chat_uploads"
app.config["AUDIO_UPLOAD_FOLDER"] = "static/audio_uploads"
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024

socketio = SocketIO(app, cors_allowed_origins="*")
usuarios_online = set()

def conectar():
    banco = sqlite3.connect("mimachat.db")
    banco.row_factory = sqlite3.Row
    return banco

def agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M")

def gerar_mima_id():
    banco = conectar()
    cursor = banco.cursor()
    while True:
        mima_id = f"MC-{random.randint(100000, 999999)}"
        cursor.execute("SELECT id FROM usuarios WHERE mima_id = ?", (mima_id,))
        if not cursor.fetchone():
            banco.close()
            return mima_id

def add_coluna(cursor, tabela, coluna, tipo):
    cursor.execute(f"PRAGMA table_info({tabela})")
    colunas = [c["name"] for c in cursor.fetchall()]
    if coluna not in colunas:
        try:
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        except Exception:
            pass

def criar_banco():
    banco = conectar()
    cursor = banco.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            mima_id TEXT UNIQUE,
            bio TEXT DEFAULT '',
            foto TEXT DEFAULT '',
            aparecer_online INTEGER DEFAULT 1,
            tema TEXT DEFAULT 'escuro',
            criado_em TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS amizades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            solicitante TEXT NOT NULL,
            solicitado TEXT NOT NULL,
            status TEXT NOT NULL,
            criado_em TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mensagens_privadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            remetente TEXT NOT NULL,
            destinatario TEXT NOT NULL,
            texto TEXT DEFAULT '',
            arquivo TEXT DEFAULT '',
            arquivo_nome TEXT DEFAULT '',
            arquivo_tipo TEXT DEFAULT '',
            audio TEXT DEFAULT '',
            reacao TEXT DEFAULT '',
            fixada INTEGER DEFAULT 0,
            editada INTEGER DEFAULT 0,
            apagada INTEGER DEFAULT 0,
            criado_em TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leituras (
            usuario TEXT NOT NULL,
            amigo TEXT NOT NULL,
            ultima_lida_id INTEGER DEFAULT 0,
            PRIMARY KEY (usuario, amigo)
        )
    """)

    banco.commit()

    for coluna, tipo in {
        "mima_id": "TEXT UNIQUE",
        "bio": "TEXT DEFAULT ''",
        "foto": "TEXT DEFAULT ''",
        "aparecer_online": "INTEGER DEFAULT 1",
        "tema": "TEXT DEFAULT 'escuro'"
    }.items():
        add_coluna(cursor, "usuarios", coluna, tipo)

    for coluna, tipo in {
        "arquivo": "TEXT DEFAULT ''",
        "arquivo_nome": "TEXT DEFAULT ''",
        "arquivo_tipo": "TEXT DEFAULT ''",
        "audio": "TEXT DEFAULT ''",
        "reacao": "TEXT DEFAULT ''",
        "fixada": "INTEGER DEFAULT 0",
        "editada": "INTEGER DEFAULT 0",
        "apagada": "INTEGER DEFAULT 0"
    }.items():
        add_coluna(cursor, "mensagens_privadas", coluna, tipo)

    cursor.execute("SELECT id FROM usuarios WHERE mima_id IS NULL OR mima_id = ''")
    for u in cursor.fetchall():
        cursor.execute("UPDATE usuarios SET mima_id = ? WHERE id = ?", (f"MC-{random.randint(100000, 999999)}", u["id"]))

    banco.commit()
    banco.close()

criar_banco()

def usuario_logado():
    return session.get("usuario")

def buscar_usuario(nome=None):
    nome = nome or usuario_logado()
    if not nome:
        return None
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("SELECT nome, mima_id, bio, foto, aparecer_online, tema, criado_em FROM usuarios WHERE nome = ?", (nome,))
    usuario = cursor.fetchone()
    banco.close()
    return usuario

def sao_amigos(a, b):
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("""
        SELECT id FROM amizades
        WHERE status = 'aceita'
        AND ((solicitante = ? AND solicitado = ?) OR (solicitante = ? AND solicitado = ?))
    """, (a, b, b, a))
    ok = cursor.fetchone() is not None
    banco.close()
    return ok

def usuario_visivel_online(nome):
    u = buscar_usuario(nome)
    return bool(u and u["aparecer_online"] == 1 and nome in usuarios_online)

@app.route("/")
def inicio():
    if usuario_logado():
        return redirect("/app")
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        nome = request.form["nome"].strip()
        senha = request.form["senha"].strip()
        banco = conectar()
        cursor = banco.cursor()
        cursor.execute("SELECT senha FROM usuarios WHERE nome = ?", (nome,))
        usuario = cursor.fetchone()
        banco.close()
        if usuario and check_password_hash(usuario["senha"], senha):
            session["usuario"] = nome
            return redirect("/app")
        erro = "Nome ou senha incorretos."
    return render_template("login.html", erro=erro)

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    erro = None
    if request.method == "POST":
        nome = request.form["nome"].strip()
        senha = request.form["senha"].strip()
        if len(nome) < 3:
            erro = "O nome precisa ter pelo menos 3 letras."
        elif len(senha) < 4:
            erro = "A senha precisa ter pelo menos 4 caracteres."
        else:
            try:
                banco = conectar()
                cursor = banco.cursor()
                cursor.execute(
                    "INSERT INTO usuarios (nome, senha, mima_id, criado_em) VALUES (?, ?, ?, ?)",
                    (nome, generate_password_hash(senha), gerar_mima_id(), agora())
                )
                banco.commit()
                banco.close()
                return redirect("/login")
            except sqlite3.IntegrityError:
                erro = "Esse nome já existe."
    return render_template("cadastro.html", erro=erro)

@app.route("/app")
def app_principal():
    if not usuario_logado():
        return redirect("/login")
    return render_template("app.html", usuario=buscar_usuario())

@app.route("/sair")
def sair():
    nome = usuario_logado()
    if nome in usuarios_online:
        usuarios_online.remove(nome)
    session.clear()
    return redirect("/login")

@app.route("/api/amigos")
def api_amigos():
    nome = usuario_logado()
    if not nome:
        return jsonify({"amigos": [], "pendentes": [], "enviadas": []})

    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("""
        SELECT * FROM amizades
        WHERE status = 'aceita' AND (solicitante = ? OR solicitado = ?)
    """, (nome, nome))

    amigos = []
    for linha in cursor.fetchall():
        amigo_nome = linha["solicitado"] if linha["solicitante"] == nome else linha["solicitante"]
        cursor.execute("SELECT nome, mima_id, bio, foto, aparecer_online FROM usuarios WHERE nome = ?", (amigo_nome,))
        a = cursor.fetchone()
        if not a:
            continue

        cursor.execute("""
            SELECT id, texto, arquivo_nome, audio, apagada, criado_em FROM mensagens_privadas
            WHERE (remetente = ? AND destinatario = ?) OR (remetente = ? AND destinatario = ?)
            ORDER BY id DESC LIMIT 1
        """, (nome, amigo_nome, amigo_nome, nome))
        ultima = cursor.fetchone()

        cursor.execute("SELECT ultima_lida_id FROM leituras WHERE usuario = ? AND amigo = ?", (nome, amigo_nome))
        leitura = cursor.fetchone()
        ultima_lida = leitura["ultima_lida_id"] if leitura else 0

        cursor.execute("""
            SELECT COUNT(*) AS total FROM mensagens_privadas
            WHERE remetente = ? AND destinatario = ? AND id > ? AND apagada = 0
        """, (amigo_nome, nome, ultima_lida))
        nao_lidas = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT id, texto FROM mensagens_privadas
            WHERE fixada = 1 AND apagada = 0
            AND ((remetente = ? AND destinatario = ?) OR (remetente = ? AND destinatario = ?))
            ORDER BY id DESC LIMIT 1
        """, (nome, amigo_nome, amigo_nome, nome))
        fixada = cursor.fetchone()

        if ultima:
            if ultima["apagada"]:
                previa = "Mensagem apagada"
            elif ultima["audio"]:
                previa = "🎙️ Mensagem de voz"
            elif ultima["arquivo_nome"]:
                previa = "📎 " + ultima["arquivo_nome"]
            else:
                previa = ultima["texto"] or "Mensagem"
        else:
            previa = "Chat vazio"

        amigos.append({
            "nome": a["nome"],
            "mima_id": a["mima_id"],
            "bio": a["bio"] or "",
            "foto": a["foto"] or "",
            "online": usuario_visivel_online(a["nome"]),
            "ultima": previa,
            "ultima_data": ultima["criado_em"] if ultima else "",
            "nao_lidas": nao_lidas,
            "fixada": dict(fixada) if fixada else None
        })

    cursor.execute("""
        SELECT a.id, u.nome, u.mima_id, u.bio, u.foto FROM amizades a
        JOIN usuarios u ON u.nome = a.solicitante
        WHERE a.solicitado = ? AND a.status = 'pendente'
    """, (nome,))
    pendentes = [dict(linha) for linha in cursor.fetchall()]

    cursor.execute("""
        SELECT a.id, u.nome, u.mima_id FROM amizades a
        JOIN usuarios u ON u.nome = a.solicitado
        WHERE a.solicitante = ? AND a.status = 'pendente'
    """, (nome,))
    enviadas = [dict(linha) for linha in cursor.fetchall()]

    banco.close()
    return jsonify({"amigos": amigos, "pendentes": pendentes, "enviadas": enviadas})

@app.route("/api/adicionar-amigo", methods=["POST"])
def api_adicionar_amigo():
    nome = usuario_logado()
    mima_id = request.get_json().get("mima_id", "").strip().upper()
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("SELECT nome FROM usuarios WHERE mima_id = ?", (mima_id,))
    alvo = cursor.fetchone()
    if not alvo:
        banco.close()
        return jsonify({"ok": False, "msg": "ID não encontrado."})
    alvo_nome = alvo["nome"]
    if alvo_nome == nome:
        banco.close()
        return jsonify({"ok": False, "msg": "Você não pode adicionar você mesmo."})
    cursor.execute("""
        SELECT id FROM amizades
        WHERE (solicitante = ? AND solicitado = ?) OR (solicitante = ? AND solicitado = ?)
    """, (nome, alvo_nome, alvo_nome, nome))
    if cursor.fetchone():
        banco.close()
        return jsonify({"ok": False, "msg": "Já existe amizade ou solicitação pendente."})
    cursor.execute("INSERT INTO amizades (solicitante, solicitado, status, criado_em) VALUES (?, ?, 'pendente', ?)", (nome, alvo_nome, agora()))
    banco.commit()
    banco.close()
    return jsonify({"ok": True, "msg": f"Convite enviado para {alvo_nome}."})

@app.route("/api/aceitar-amigo", methods=["POST"])
def api_aceitar_amigo():
    nome = usuario_logado()
    amizade_id = request.get_json().get("id")
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("UPDATE amizades SET status = 'aceita' WHERE id = ? AND solicitado = ?", (amizade_id, nome))
    banco.commit()
    banco.close()
    return jsonify({"ok": True})

@app.route("/api/recusar-amigo", methods=["POST"])
def api_recusar_amigo():
    nome = usuario_logado()
    amizade_id = request.get_json().get("id")
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("DELETE FROM amizades WHERE id = ? AND solicitado = ?", (amizade_id, nome))
    banco.commit()
    banco.close()
    return jsonify({"ok": True})

@app.route("/api/desfazer-amizade", methods=["POST"])
def api_desfazer_amizade():
    nome = usuario_logado()
    amigo = request.get_json().get("nome")
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("""
        DELETE FROM amizades
        WHERE status = 'aceita'
        AND ((solicitante = ? AND solicitado = ?) OR (solicitante = ? AND solicitado = ?))
    """, (nome, amigo, amigo, nome))
    banco.commit()
    banco.close()
    return jsonify({"ok": True})

@app.route("/api/perfil/<nome>")
def api_perfil(nome):
    atual = usuario_logado()
    u = buscar_usuario(nome)
    if not u:
        return jsonify({"ok": False})
    return jsonify({
        "ok": True,
        "nome": u["nome"],
        "mima_id": u["mima_id"],
        "bio": u["bio"] or "Sem bio ainda.",
        "foto": u["foto"] or "",
        "online": usuario_visivel_online(u["nome"]),
        "amigo": sao_amigos(atual, u["nome"]) if atual else False
    })

@app.route("/api/mensagens/<amigo>")
def api_mensagens_privadas(amigo):
    nome = usuario_logado()
    if not nome or not sao_amigos(nome, amigo):
        return jsonify([])
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("""
        SELECT id, remetente, destinatario, texto, arquivo, arquivo_nome, arquivo_tipo,
               audio, reacao, fixada, editada, apagada, criado_em
        FROM mensagens_privadas
        WHERE (remetente = ? AND destinatario = ?) OR (remetente = ? AND destinatario = ?)
        ORDER BY id ASC LIMIT 400
    """, (nome, amigo, amigo, nome))
    mensagens = [dict(linha) for linha in cursor.fetchall()]
    cursor.execute("SELECT MAX(id) AS ultimo FROM mensagens_privadas WHERE remetente = ? AND destinatario = ?", (amigo, nome))
    ultimo = cursor.fetchone()["ultimo"] or 0
    cursor.execute("""
        INSERT INTO leituras (usuario, amigo, ultima_lida_id)
        VALUES (?, ?, ?)
        ON CONFLICT(usuario, amigo) DO UPDATE SET ultima_lida_id = excluded.ultima_lida_id
    """, (nome, amigo, ultimo))
    banco.commit()
    banco.close()
    socketio.emit("mensagens_lidas", {"por": nome, "amigo": amigo})
    return jsonify(mensagens)

@app.route("/api/upload-chat", methods=["POST"])
def api_upload_chat():
    nome = usuario_logado()
    amigo = request.form.get("para", "")
    texto = request.form.get("texto", "").strip()
    if not nome or not sao_amigos(nome, amigo):
        return jsonify({"ok": False, "msg": "Acesso negado."})

    arquivo_url = ""
    arquivo_nome = ""
    arquivo_tipo = ""
    audio_url = ""

    arquivo = request.files.get("arquivo")
    if arquivo and arquivo.filename:
        original = secure_filename(arquivo.filename)
        ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
        permitidas = ["png", "jpg", "jpeg", "webp", "gif", "pdf", "txt", "doc", "docx", "zip", "rar"]
        if ext not in permitidas:
            return jsonify({"ok": False, "msg": "Tipo de arquivo não permitido."})
        filename = f"{nome}_{random.randint(10000,99999)}_{original}"
        Path(app.config["CHAT_UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
        arquivo.save(str(Path(app.config["CHAT_UPLOAD_FOLDER"]) / filename))
        arquivo_url = f"/static/chat_uploads/{filename}"
        arquivo_nome = original
        arquivo_tipo = "imagem" if ext in ["png", "jpg", "jpeg", "webp", "gif"] else "arquivo"

    audio = request.files.get("audio")
    if audio and audio.filename:
        filename = secure_filename(f"{nome}_{random.randint(10000,99999)}_voz.webm")
        Path(app.config["AUDIO_UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
        audio.save(str(Path(app.config["AUDIO_UPLOAD_FOLDER"]) / filename))
        audio_url = f"/static/audio_uploads/{filename}"

    if not texto and not arquivo_url and not audio_url:
        return jsonify({"ok": False, "msg": "Digite algo ou selecione um arquivo."})

    data = agora()
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("""
        INSERT INTO mensagens_privadas (remetente, destinatario, texto, arquivo, arquivo_nome, arquivo_tipo, audio, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (nome, amigo, texto, arquivo_url, arquivo_nome, arquivo_tipo, audio_url, data))
    msg_id = cursor.lastrowid
    banco.commit()
    banco.close()

    payload = {
        "id": msg_id, "remetente": nome, "destinatario": amigo, "texto": texto,
        "arquivo": arquivo_url, "arquivo_nome": arquivo_nome, "arquivo_tipo": arquivo_tipo,
        "audio": audio_url, "reacao": "", "fixada": 0, "editada": 0, "apagada": 0, "criado_em": data
    }
    socketio.emit("nova_mensagem_privada", payload)
    return jsonify({"ok": True})

@app.route("/api/editar-mensagem", methods=["POST"])
def api_editar_mensagem():
    nome = usuario_logado()
    dados = request.get_json()
    msg_id = dados.get("id")
    texto = dados.get("texto", "").strip()
    if not texto:
        return jsonify({"ok": False, "msg": "Mensagem vazia."})
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("UPDATE mensagens_privadas SET texto = ?, editada = 1 WHERE id = ? AND remetente = ? AND apagada = 0", (texto, msg_id, nome))
    banco.commit()
    banco.close()
    socketio.emit("mensagem_editada", {"id": msg_id, "texto": texto})
    return jsonify({"ok": True})

@app.route("/api/apagar-mensagem", methods=["POST"])
def api_apagar_mensagem():
    nome = usuario_logado()
    msg_id = request.get_json().get("id")
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("""
        UPDATE mensagens_privadas SET apagada = 1, texto = '', arquivo = '', arquivo_nome = '', arquivo_tipo = '', audio = '', reacao = ''
        WHERE id = ? AND remetente = ?
    """, (msg_id, nome))
    banco.commit()
    banco.close()
    socketio.emit("mensagem_apagada", {"id": msg_id})
    return jsonify({"ok": True})

@app.route("/api/reagir-mensagem", methods=["POST"])
def api_reagir_mensagem():
    dados = request.get_json()
    msg_id = dados.get("id")
    reacao = dados.get("reacao", "")[:3]
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("UPDATE mensagens_privadas SET reacao = ? WHERE id = ? AND apagada = 0", (reacao, msg_id))
    banco.commit()
    banco.close()
    socketio.emit("mensagem_reagida", {"id": msg_id, "reacao": reacao})
    return jsonify({"ok": True})

@app.route("/api/fixar-mensagem", methods=["POST"])
def api_fixar_mensagem():
    nome = usuario_logado()
    dados = request.get_json()
    msg_id = dados.get("id")
    amigo = dados.get("amigo")
    if not sao_amigos(nome, amigo):
        return jsonify({"ok": False})
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("""
        UPDATE mensagens_privadas SET fixada = 0
        WHERE (remetente = ? AND destinatario = ?) OR (remetente = ? AND destinatario = ?)
    """, (nome, amigo, amigo, nome))
    cursor.execute("UPDATE mensagens_privadas SET fixada = 1 WHERE id = ?", (msg_id,))
    banco.commit()
    banco.close()
    socketio.emit("mensagem_fixada", {"id": msg_id, "amigo": amigo, "por": nome})
    return jsonify({"ok": True})

@app.route("/api/atualizar-perfil", methods=["POST"])
def api_atualizar_perfil():
    nome = usuario_logado()
    bio = request.form.get("bio", "").strip()[:250]
    foto_atual = buscar_usuario(nome)["foto"] or ""
    foto_nome = foto_atual
    arquivo = request.files.get("foto")
    if arquivo and arquivo.filename:
        ext = arquivo.filename.rsplit(".", 1)[-1].lower()
        if ext in ["png", "jpg", "jpeg", "webp", "gif"]:
            filename = secure_filename(f"{nome}_{random.randint(1000,9999)}.{ext}")
            Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
            arquivo.save(str(Path(app.config["UPLOAD_FOLDER"]) / filename))
            foto_nome = f"/static/uploads/{filename}"
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("UPDATE usuarios SET bio = ?, foto = ? WHERE nome = ?", (bio, foto_nome, nome))
    banco.commit()
    banco.close()
    return redirect("/app")

@app.route("/api/status", methods=["POST"])
def api_status():
    nome = usuario_logado()
    aparecer = 1 if request.get_json().get("aparecer_online") else 0
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("UPDATE usuarios SET aparecer_online = ? WHERE nome = ?", (aparecer, nome))
    banco.commit()
    banco.close()
    emit_online()
    return jsonify({"ok": True})

@app.route("/api/tema", methods=["POST"])
def api_tema():
    nome = usuario_logado()
    tema = request.get_json().get("tema", "escuro")
    if tema not in ["escuro", "claro"]:
        tema = "escuro"
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("UPDATE usuarios SET tema = ? WHERE nome = ?", (tema, nome))
    banco.commit()
    banco.close()
    return jsonify({"ok": True})

@app.route("/api/trocar-senha", methods=["POST"])
def api_trocar_senha():
    nome = usuario_logado()
    dados = request.get_json()
    atual = dados.get("senha_atual", "")
    nova = dados.get("nova_senha", "")
    if len(nova) < 4:
        return jsonify({"ok": False, "msg": "A nova senha precisa ter pelo menos 4 caracteres."})
    banco = conectar()
    cursor = banco.cursor()
    cursor.execute("SELECT senha FROM usuarios WHERE nome = ?", (nome,))
    u = cursor.fetchone()
    if not u or not check_password_hash(u["senha"], atual):
        banco.close()
        return jsonify({"ok": False, "msg": "Senha atual incorreta."})
    cursor.execute("UPDATE usuarios SET senha = ? WHERE nome = ?", (generate_password_hash(nova), nome))
    banco.commit()
    banco.close()
    return jsonify({"ok": True, "msg": "Senha alterada com sucesso."})

@app.route("/api/alterar-nome", methods=["POST"])
def api_alterar_nome():
    atual_nome = usuario_logado()
    novo = request.get_json().get("novo_nome", "").strip()
    if len(novo) < 3:
        return jsonify({"ok": False, "msg": "O novo nome precisa ter pelo menos 3 letras."})
    banco = conectar()
    cursor = banco.cursor()
    try:
        cursor.execute("UPDATE usuarios SET nome = ? WHERE nome = ?", (novo, atual_nome))
        cursor.execute("UPDATE amizades SET solicitante = ? WHERE solicitante = ?", (novo, atual_nome))
        cursor.execute("UPDATE amizades SET solicitado = ? WHERE solicitado = ?", (novo, atual_nome))
        cursor.execute("UPDATE mensagens_privadas SET remetente = ? WHERE remetente = ?", (novo, atual_nome))
        cursor.execute("UPDATE mensagens_privadas SET destinatario = ? WHERE destinatario = ?", (novo, atual_nome))
        cursor.execute("UPDATE leituras SET usuario = ? WHERE usuario = ?", (novo, atual_nome))
        cursor.execute("UPDATE leituras SET amigo = ? WHERE amigo = ?", (novo, atual_nome))
        banco.commit()
        session["usuario"] = novo
        if atual_nome in usuarios_online:
            usuarios_online.remove(atual_nome)
            usuarios_online.add(novo)
        banco.close()
        return jsonify({"ok": True, "msg": "Nome alterado. Recarregue a página."})
    except sqlite3.IntegrityError:
        banco.close()
        return jsonify({"ok": False, "msg": "Esse nome já está em uso."})

def emit_online():
    socketio.emit("usuarios_online", list(usuarios_online))

@socketio.on("connect")
def conectar_socket():
    nome = usuario_logado()
    if nome:
        usuarios_online.add(nome)
        emit_online()

@socketio.on("disconnect")
def desconectar_socket():
    nome = usuario_logado()
    if nome in usuarios_online:
        usuarios_online.remove(nome)
        emit_online()

@socketio.on("digitando")
def digitando(dados):
    nome = usuario_logado()
    para = dados.get("para")
    if nome and para:
        emit("usuario_digitando", {"de": nome, "para": para}, broadcast=True, include_self=False)

if __name__ == "__main__":
    print("MimaChat V8 Premium rodando em http://127.0.0.1:5000")
    socketio.run(app, host="127.0.0.1", port=5000, debug=True)
