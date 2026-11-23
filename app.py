"""
MOONRISE - site de leitura de mangá feito em Python (Flask + SQLite)
trabalho de Big Data no Agronegócio - Fatec Bebedouro

pra rodar:
    pip install flask
    python app.py
    depois abre no navegador: http://127.0.0.1:5000

obs: a PRIMEIRA conta que cadastrar em /cadastro vira admin

pastas:
    app.py      -> o código principal (rotas, banco e login)
    templates/  -> os HTML de cada página
    static/     -> css, js, logo, fontes e as imagens que o admin sobe
"""

import os         # mexer com pastas e caminhos
import re         # pra procurar padrão em texto (validar nome e ordenar arquivo)
import secrets    # gera código aleatório pro nome do arquivo
import shutil     # apagar uma pasta inteira de uma vez
import sqlite3    # o banco de dados (já vem com o python)
from functools import wraps  # usei pra fazer os decoradores de login

from flask import Flask, render_template, request, redirect, session, flash, abort, g
from werkzeug.security import generate_password_hash, check_password_hash  # vem junto com o flask, não precisa instalar


#configurações
app = Flask(__name__)
app.secret_key = "troque-esta-chave-por-qualquer-texto"   # a sessão do login usa isso (trocar depois)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024       # limite de 200 MB por upload

PASTA = os.path.dirname(os.path.abspath(__file__))          # pasta onde esse arquivo tá
BANCO = os.path.join(PASTA, "moonrise.db")                  # o arquivo do banco
UPLOADS = os.path.join(PASTA, "static", "uploads")          # aqui as imagens são salvas

EXTENSOES = {"jpg", "jpeg", "png", "webp", "gif"}           # só aceita esses tipos de imagem
TIPOS = ["Mangá", "Manhwa", "Manhua", "Webtoon", "HQ"]
SITUACOES = ["Em andamento", "Completo", "Pausado"]

#ordens do catálogo: o nome que aparece na tela e o ORDER BY do sql
ORDENS = {
    "recentes": ("Atualizadas", "atualizado_em DESC"),
    "populares": ("Mais lidas", "views_semana DESC, views DESC"),
    "nota": ("Melhor nota", "nota DESC"),
    "az": ("A a Z", "titulo COLLATE NOCASE"),
}


#banco de dados
def conectar():
    #abre o banco. o row_factory deixa usar linha["titulo"] em vez de linha[1]
    con = sqlite3.connect(BANCO)
    con.row_factory = sqlite3.Row
    return con


def ler(sql, params=()):
    #faz um SELECT e devolve todas as linhas
    con = conectar()
    linhas = con.execute(sql, params).fetchall()
    con.close()
    return linhas


def ler_um(sql, params=()):
    #faz um SELECT e devolve só a primeira linha (ou None se não achar)
    linhas = ler(sql, params)
    return linhas[0] if linhas else None


def gravar(sql, params=()):
    #faz INSERT, UPDATE ou DELETE e devolve o id da linha criada
    con = conectar()
    cursor = con.execute(sql, params)
    con.commit()                      # sem o commit não salva nada
    novo_id = cursor.lastrowid
    con.close()
    return novo_id


def criar_tabelas():
    #cria as tabelas na primeira vez que roda o programa
    con = conectar()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS usuario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
            email TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,           -- a senha não é salva pura, só o hash
            admin INTEGER NOT NULL DEFAULT 0,   -- 1 = admin
            criado_em TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS obra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            autor TEXT,
            tipo TEXT DEFAULT 'Mangá',
            status TEXT DEFAULT 'Em andamento',
            generos TEXT,                       -- ex.: "Romance, Escolar"
            descricao TEXT,
            capa TEXT,                          -- caminho da imagem dentro do static/
            destaque INTEGER DEFAULT 0,         -- 1 = aparece no carrossel da página inicial
            criado_em TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS capitulo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            obra_id INTEGER NOT NULL,
            numero REAL NOT NULL,               -- REAL pra aceitar capítulo 10.5
            titulo TEXT,
            criado_em TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS pagina (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capitulo_id INTEGER NOT NULL,
            numero INTEGER NOT NULL,
            arquivo TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS favorito (
            usuario_id INTEGER NOT NULL,
            obra_id INTEGER NOT NULL,
            criado_em TEXT DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY (usuario_id, obra_id)   -- pra não favoritar 2 vezes
        );
        CREATE TABLE IF NOT EXISTS avaliacao (
            usuario_id INTEGER NOT NULL,
            obra_id INTEGER NOT NULL,
            nota INTEGER NOT NULL,              -- de 1 a 10
            PRIMARY KEY (usuario_id, obra_id)   -- uma nota por pessoa
        );
        CREATE TABLE IF NOT EXISTS leitura (    -- cada vez que alguém abre um capítulo
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,                 -- fica NULL se for visitante
            obra_id INTEGER NOT NULL,
            capitulo_id INTEGER NOT NULL,
            lido_em TEXT DEFAULT (datetime('now', 'localtime'))
        );

        -- Índices deixam as buscas mais rápidas
        CREATE INDEX IF NOT EXISTS idx_capitulo_obra ON capitulo (obra_id);
        CREATE INDEX IF NOT EXISTS idx_pagina_capitulo ON pagina (capitulo_id);
        CREATE INDEX IF NOT EXISTS idx_leitura_obra ON leitura (obra_id);
        CREATE INDEX IF NOT EXISTS idx_leitura_usuario ON leitura (usuario_id);

        -- VIEW = uma consulta salva que funciona como se fosse uma tabela.
        -- Junta cada obra com a nota média, as visualizações e o último capítulo.
        DROP VIEW IF EXISTS obra_info;
        CREATE VIEW obra_info AS
        SELECT o.*,
            (SELECT ROUND(AVG(a.nota), 1) FROM avaliacao a WHERE a.obra_id = o.id) AS nota,
            (SELECT COUNT(*) FROM avaliacao a WHERE a.obra_id = o.id) AS total_notas,
            (SELECT COUNT(*) FROM leitura l WHERE l.obra_id = o.id) AS views,
            (SELECT COUNT(*) FROM leitura l WHERE l.obra_id = o.id
                AND l.lido_em >= datetime('now', 'localtime', '-7 days')) AS views_semana,
            (SELECT COUNT(*) FROM favorito f WHERE f.obra_id = o.id) AS favoritos,
            (SELECT COUNT(*) FROM capitulo c WHERE c.obra_id = o.id) AS total_caps,
            (SELECT MAX(c.numero) FROM capitulo c WHERE c.obra_id = o.id) AS ultimo_cap,
            (SELECT c.id FROM capitulo c WHERE c.obra_id = o.id
                ORDER BY c.numero LIMIT 1) AS primeiro_cap_id,
            (SELECT MAX(c.criado_em) FROM capitulo c WHERE c.obra_id = o.id) AS atualizado_em
        FROM obra o;
    """)
    con.close()


#funções de ajuda
def extensao(nome_arquivo):
    # 'Pagina 01.JPG' vira 'jpg'
    return nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""


def ordem_natural(nome_arquivo):
    #pra '2.jpg' vir antes de '10.jpg' (compara como número e não como texto)
    return [int(parte) if parte.isdigit() else parte.lower()
            for parte in re.split(r"(\d+)", nome_arquivo)]


def salvar_capa(obra_id, arquivo):
    # salva a capa em static/uploads/obra_X/ e devolve o caminho
    pasta = os.path.join(UPLOADS, f"obra_{obra_id}")
    os.makedirs(pasta, exist_ok=True)
    nome = f"capa_{secrets.token_hex(4)}.{extensao(arquivo.filename)}"  # nome novo pra não ficar a capa velha no cache
    arquivo.save(os.path.join(pasta, nome))
    return f"uploads/obra_{obra_id}/{nome}"


def apagar_arquivo(caminho):
    #apaga um arquivo do static/ (se existir)
    if caminho:
        completo = os.path.join(PASTA, "static", caminho)
        if os.path.isfile(completo):
            os.remove(completo)


def obra_ou_404(obra_id):
    #procura a obra, se não achar dá erro 404
    obra = ler_um("SELECT * FROM obra_info WHERE id = ?", (obra_id,))
    if obra is None:
        abort(404)
    return obra


def continuar_lendo(usuario_id, limite=20):
    #último capítulo que a pessoa abriu de cada obra (o mais recente primeiro)
    return ler("""
        SELECT o.*, c.id AS cap_id, c.numero AS cap_numero, MAX(l.id) AS ultima_leitura
        FROM leitura l
        JOIN capitulo c ON c.id = l.capitulo_id
        JOIN obra_info o ON o.id = l.obra_id
        WHERE l.usuario_id = ?
        GROUP BY l.obra_id
        ORDER BY ultima_leitura DESC
        LIMIT ?""", (usuario_id, limite))


#filtros: formatam o valor dentro do html, tipo {{ obra.views|br }}
@app.template_filter("br")
def numero_br(valor):
    # número no padrão brasileiro: 25436 vira 25.436 e 6.3 vira 6,3
    if valor is None:
        return "–"
    if isinstance(valor, float):
        return f"{valor:.1f}".replace(".", ",")
    return f"{valor:,}".replace(",", ".")


@app.template_filter("cap")
def numero_capitulo(valor):
    # tira o '.0' do capítulo: 12.0 vira 12 e 10.5 vira 10,5
    return f"{valor:g}".replace(".", ",") if valor is not None else ""


@app.template_filter("data")
def data_br(texto):
    #'2026-11-19 20:15:00' vira '19/11/2026'
    if not texto:
        return ""
    ano, mes, dia = texto[:10].split("-")
    return f"{dia}/{mes}/{ano}"


#login 
@app.before_request
def carregar_usuario():
    #roda antes de toda página e guarda em g.usuario quem tá logado (ou None)
    g.usuario = None
    if request.endpoint == "static":   #arquivo do static não precisa disso
        return
    if "usuario_id" in session:
        g.usuario = ler_um("SELECT * FROM usuario WHERE id = ?", (session["usuario_id"],))


def login_obrigatorio(funcao):
    #decorador: só deixa abrir a página se tiver logado
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if g.usuario is None:
            flash("Entre na sua conta para continuar.", "dica")
            voltar = request.path if request.method == "GET" else "/"
            return redirect(f"/entrar?voltar={voltar}")
        return funcao(*args, **kwargs)
    return verificar


def admin_obrigatorio(funcao):
    #decorador: só deixa abrir a página se for admin
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if g.usuario is None:
            return redirect(f"/entrar?voltar={request.path}")
        if not g.usuario["admin"]:
            abort(403)
        return funcao(*args, **kwargs)
    return verificar


#área do leitor 
@app.route("/")
def inicio():
    destaques = ler("SELECT * FROM obra_info WHERE destaque = 1 ORDER BY id DESC LIMIT 6")
    if not destaques:   #se o admin não marcou nenhuma, mostra as mais novas
        destaques = ler("SELECT * FROM obra_info ORDER BY id DESC LIMIT 5")
    mais_lidas = ler("SELECT * FROM obra_info WHERE views_semana > 0 "
                     "ORDER BY views_semana DESC LIMIT 12")
    novidades = ler("SELECT * FROM obra_info WHERE atualizado_em IS NOT NULL "
                    "ORDER BY atualizado_em DESC LIMIT 12")
    todas = ler("SELECT * FROM obra_info ORDER BY titulo COLLATE NOCASE LIMIT 24")
    continuar = continuar_lendo(g.usuario["id"], 12) if g.usuario else []
    sem_contas = ler_um("SELECT COUNT(*) AS total FROM usuario")["total"] == 0
    return render_template("inicio.html", destaques=destaques, mais_lidas=mais_lidas,
                           novidades=novidades, todas=todas, continuar=continuar,
                           sem_contas=sem_contas)


@app.route("/catalogo")
def catalogo():
    busca = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "")
    ordem = request.args.get("ordem", "recentes")
    if ordem not in ORDENS:
        ordem = "recentes"

    termo = f"%{busca}%"
    sql = "SELECT * FROM obra_info WHERE (titulo LIKE ? OR autor LIKE ? OR generos LIKE ?)"
    params = [termo, termo, termo]
    if tipo in TIPOS:
        sql += " AND tipo = ?"
        params.append(tipo)
    sql += " ORDER BY " + ORDENS[ordem][1]   #é seguro porque o texto vem do dicionário ORDENS

    return render_template("catalogo.html", obras=ler(sql, params), busca=busca,
                           tipo=tipo, ordem=ordem, ordens=ORDENS, tipos=TIPOS)


@app.route("/obra/<int:obra_id>")
def ver_obra(obra_id):
    obra = obra_ou_404(obra_id)
    capitulos = ler("SELECT * FROM capitulo WHERE obra_id = ? ORDER BY numero DESC", (obra_id,))
    generos = [x.strip() for x in (obra["generos"] or "").split(",") if x.strip()]

    favorito, minha_nota, ultimo_lido, lidos = False, None, None, set()
    if g.usuario:
        uid = g.usuario["id"]
        favorito = ler_um("SELECT 1 FROM favorito WHERE usuario_id = ? AND obra_id = ?",
                          (uid, obra_id)) is not None
        nota = ler_um("SELECT nota FROM avaliacao WHERE usuario_id = ? AND obra_id = ?",
                      (uid, obra_id))
        minha_nota = nota["nota"] if nota else None
        ultimo_lido = ler_um("""SELECT c.id, c.numero FROM leitura l
                                JOIN capitulo c ON c.id = l.capitulo_id
                                WHERE l.usuario_id = ? AND l.obra_id = ?
                                ORDER BY l.id DESC LIMIT 1""", (uid, obra_id))
        lidos = {linha["capitulo_id"] for linha in ler(
            "SELECT DISTINCT capitulo_id FROM leitura WHERE usuario_id = ? AND obra_id = ?",
            (uid, obra_id))}

    return render_template("obra.html", obra=obra, capitulos=capitulos, generos=generos,
                           favorito=favorito, minha_nota=minha_nota,
                           ultimo_lido=ultimo_lido, lidos=lidos)


@app.route("/obra/<int:obra_id>/favoritar", methods=["POST"])
@login_obrigatorio
def favoritar(obra_id):
    obra_ou_404(obra_id)
    uid = g.usuario["id"]
    if ler_um("SELECT 1 FROM favorito WHERE usuario_id = ? AND obra_id = ?", (uid, obra_id)):
        gravar("DELETE FROM favorito WHERE usuario_id = ? AND obra_id = ?", (uid, obra_id))
        flash("Obra removida dos favoritos.")
    else:
        gravar("INSERT INTO favorito (usuario_id, obra_id) VALUES (?, ?)", (uid, obra_id))
        flash("Obra adicionada aos favoritos.")
    return redirect(f"/obra/{obra_id}")


@app.route("/obra/<int:obra_id>/avaliar", methods=["POST"])
@login_obrigatorio
def avaliar(obra_id):
    obra_ou_404(obra_id)
    nota = request.form.get("nota", type=int)
    if nota is None or not 1 <= nota <= 10:
        flash("Escolha uma nota de 1 a 10.", "erro")
    else:
        #INSERT OR REPLACE: se a pessoa já deu nota, troca pela nova
        gravar("INSERT OR REPLACE INTO avaliacao (usuario_id, obra_id, nota) VALUES (?, ?, ?)",
               (g.usuario["id"], obra_id, nota))
        flash(f"Nota {nota} salva.")
    return redirect(f"/obra/{obra_id}")


@app.route("/ler/<int:cap_id>")
def ler_capitulo(cap_id):
    cap = ler_um("SELECT * FROM capitulo WHERE id = ?", (cap_id,))
    if cap is None:
        abort(404)
    obra = obra_ou_404(cap["obra_id"])
    paginas = ler("SELECT * FROM pagina WHERE capitulo_id = ? ORDER BY numero", (cap_id,))
    capitulos = ler("SELECT id, numero FROM capitulo WHERE obra_id = ? ORDER BY numero",
                    (obra["id"],))
    anterior = ler_um("SELECT id FROM capitulo WHERE obra_id = ? AND numero < ? "
                      "ORDER BY numero DESC LIMIT 1", (obra["id"], cap["numero"]))
    proximo = ler_um("SELECT id FROM capitulo WHERE obra_id = ? AND numero > ? "
                     "ORDER BY numero LIMIT 1", (obra["id"], cap["numero"]))

    #registra a leitura (conta a visualização e salva o "continuar lendo")
    usuario_id = g.usuario["id"] if g.usuario else None
    gravar("INSERT INTO leitura (usuario_id, obra_id, capitulo_id) VALUES (?, ?, ?)",
           (usuario_id, obra["id"], cap_id))

    return render_template("ler.html", obra=obra, cap=cap, paginas=paginas,
                           capitulos=capitulos, anterior=anterior, proximo=proximo)


#contas (cadastro, entrar, sair...) 
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if g.usuario:
        return redirect("/")
    primeira_conta = ler_um("SELECT COUNT(*) AS total FROM usuario")["total"] == 0
    nome, email = "", ""

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        confirmar = request.form.get("confirmar", "")

        erro = None
        if not re.fullmatch(r"[A-Za-z0-9_.]{3,20}", nome):
            erro = "O nome de usuário precisa ter de 3 a 20 letras, números, ponto ou _ (sem espaço)."
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            erro = "Digite um e-mail válido, como nome@exemplo.com."
        elif len(senha) < 6:
            erro = "A senha precisa ter pelo menos 6 caracteres."
        elif senha != confirmar:
            erro = "As duas senhas estão diferentes."
        elif ler_um("SELECT id FROM usuario WHERE nome = ? OR email = ?", (nome, email)):
            erro = "Esse nome de usuário ou e-mail já tem conta."

        if erro:
            flash(erro, "erro")
        else:
            novo_id = gravar(
                "INSERT INTO usuario (nome, email, senha_hash, admin) VALUES (?, ?, ?, ?)",
                (nome, email, generate_password_hash(senha), 1 if primeira_conta else 0))
            session.clear()
            session["usuario_id"] = novo_id   #já deixa logado na conta nova
            if primeira_conta:
                flash("Conta criada. Por ser a primeira, ela é a conta de administrador.")
                return redirect("/admin")
            flash(f"Conta criada. Boas leituras, {nome}!")
            return redirect("/")

    return render_template("cadastro.html", nome=nome, email=email, primeira_conta=primeira_conta)


@app.route("/entrar", methods=["GET", "POST"])
def entrar():
    voltar = request.args.get("voltar", "/")
    if not voltar.startswith("/") or voltar.startswith("//") or "\\" in voltar:
        voltar = "/"   #só volta pra página do próprio site (segurança)

    if request.method == "POST":
        login = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")
        usuario = ler_um("SELECT * FROM usuario WHERE nome = ? OR email = ?",
                         (login, login.lower()))
        if usuario and check_password_hash(usuario["senha_hash"], senha):
            session.clear()
            session["usuario_id"] = usuario["id"]
            flash(f"Que bom te ver, {usuario['nome']}!")
            return redirect(voltar)
        flash("Usuário ou senha incorretos.", "erro")

    return render_template("entrar.html", voltar=voltar)


@app.route("/sair")
def sair():
    session.clear()
    flash("Você saiu da conta.")
    return redirect("/")


@app.route("/biblioteca")
@login_obrigatorio
def biblioteca():
    uid = g.usuario["id"]
    favoritos = ler("""SELECT o.* FROM obra_info o JOIN favorito f ON f.obra_id = o.id
                       WHERE f.usuario_id = ? ORDER BY f.criado_em DESC""", (uid,))
    return render_template("biblioteca.html", continuar=continuar_lendo(uid), favoritos=favoritos)


@app.route("/conta", methods=["GET", "POST"])
@login_obrigatorio
def conta():
    uid = g.usuario["id"]
    if request.method == "POST":   #trocar a senha
        atual = request.form.get("atual", "")
        nova = request.form.get("nova", "")
        if not check_password_hash(g.usuario["senha_hash"], atual):
            flash("A senha atual não confere.", "erro")
        elif len(nova) < 6:
            flash("A nova senha precisa ter pelo menos 6 caracteres.", "erro")
        elif nova != request.form.get("confirmar", ""):
            flash("As duas senhas novas estão diferentes.", "erro")
        else:
            gravar("UPDATE usuario SET senha_hash = ? WHERE id = ?",
                   (generate_password_hash(nova), uid))
            flash("Senha alterada.")
        return redirect("/conta")

    resumo = ler_um("""SELECT
        (SELECT COUNT(DISTINCT capitulo_id) FROM leitura WHERE usuario_id = ?) AS capitulos,
        (SELECT COUNT(*) FROM favorito WHERE usuario_id = ?) AS favoritos,
        (SELECT COUNT(*) FROM avaliacao WHERE usuario_id = ?) AS notas""", (uid, uid, uid))
    return render_template("conta.html", resumo=resumo)


#área do admin 
@app.route("/admin")
@admin_obrigatorio
def admin():
    numeros = ler_um("""SELECT
        (SELECT COUNT(*) FROM obra) AS obras,
        (SELECT COUNT(*) FROM capitulo) AS capitulos,
        (SELECT COUNT(*) FROM usuario) AS usuarios,
        (SELECT COUNT(*) FROM leitura
            WHERE lido_em >= datetime('now', 'localtime', '-7 days')) AS leituras""")
    obras = ler("SELECT * FROM obra_info ORDER BY id DESC")
    return render_template("admin/painel.html", numeros=numeros, obras=obras)


def ler_formulario_obra():
    #pega os campos do formulário da obra (serve pra criar e pra editar)
    tipo = request.form.get("tipo")
    status = request.form.get("status")
    return {
        "titulo": request.form.get("titulo", "").strip(),
        "autor": request.form.get("autor", "").strip(),
        "tipo": tipo if tipo in TIPOS else TIPOS[0],
        "status": status if status in SITUACOES else SITUACOES[0],
        "generos": request.form.get("generos", "").strip(),
        "descricao": request.form.get("descricao", "").strip(),
        "destaque": 1 if request.form.get("destaque") else 0,
    }


def erro_no_formulario_obra(dados):
    #confere o formulário. devolve a mensagem de erro, ou None se tá tudo certo
    capa = request.files.get("capa")
    if not dados["titulo"]:
        return "Dê um título para a obra."
    if capa and capa.filename and extensao(capa.filename) not in EXTENSOES:
        return "A capa precisa ser uma imagem JPG, PNG, WEBP ou GIF."
    return None


@app.route("/admin/obra/nova", methods=["GET", "POST"])
@admin_obrigatorio
def nova_obra():
    dados = {}
    if request.method == "POST":
        dados = ler_formulario_obra()
        erro = erro_no_formulario_obra(dados)
        if erro:
            flash(erro, "erro")
        else:
            #os :nomes no sql são trocados pelos valores do dicionário "dados"
            obra_id = gravar("""INSERT INTO obra (titulo, autor, tipo, status, generos, descricao, destaque)
                                VALUES (:titulo, :autor, :tipo, :status, :generos, :descricao, :destaque)""",
                             dados)
            capa = request.files.get("capa")
            if capa and capa.filename:
                gravar("UPDATE obra SET capa = ? WHERE id = ?", (salvar_capa(obra_id, capa), obra_id))
            flash("Obra criada. Agora publique o primeiro capítulo.")
            return redirect(f"/admin/obra/{obra_id}")
    return render_template("admin/obra_form.html", obra=dados, editando=False,
                           tipos=TIPOS, situacoes=SITUACOES)


@app.route("/admin/obra/<int:obra_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def editar_obra(obra_id):
    obra = obra_ou_404(obra_id)
    if request.method == "POST":
        dados = ler_formulario_obra()
        erro = erro_no_formulario_obra(dados)
        if erro:
            flash(erro, "erro")
            obra = {**dict(obra), **dados}   #mantém o que a pessoa digitou
        else:
            dados["id"] = obra_id
            gravar("""UPDATE obra SET titulo = :titulo, autor = :autor, tipo = :tipo,
                      status = :status, generos = :generos, descricao = :descricao,
                      destaque = :destaque WHERE id = :id""", dados)
            capa = request.files.get("capa")
            if capa and capa.filename:
                apagar_arquivo(obra["capa"])   #apaga a capa antiga
                gravar("UPDATE obra SET capa = ? WHERE id = ?", (salvar_capa(obra_id, capa), obra_id))
            flash("Obra salva.")
            return redirect(f"/admin/obra/{obra_id}")
    return render_template("admin/obra_form.html", obra=obra, editando=True,
                           tipos=TIPOS, situacoes=SITUACOES)


@app.route("/admin/obra/<int:obra_id>", methods=["GET", "POST"])
@admin_obrigatorio
def admin_obra(obra_id):
    obra = obra_ou_404(obra_id)
    if request.method == "POST":   #enviou o formulário de publicar capítulo
        publicar_capitulo(obra_id)
        return redirect(f"/admin/obra/{obra_id}")
    capitulos = ler("""SELECT c.*, (SELECT COUNT(*) FROM pagina p WHERE p.capitulo_id = c.id) AS paginas
                       FROM capitulo c WHERE c.obra_id = ? ORDER BY c.numero DESC""", (obra_id,))
    proximo_numero = int(obra["ultimo_cap"] or 0) + 1
    return render_template("admin/obra.html", obra=obra, capitulos=capitulos,
                           proximo_numero=proximo_numero)


def publicar_capitulo(obra_id):
    #salva um capítulo novo com todas as imagens enviadas
    try:
        numero = float(request.form.get("numero", "").replace(",", "."))
        if not 0 <= numero <= 99999:
            raise ValueError
    except ValueError:
        flash("Digite o número do capítulo, por exemplo 12 ou 12,5.", "erro")
        return
    if ler_um("SELECT id FROM capitulo WHERE obra_id = ? AND numero = ?", (obra_id, numero)):
        flash(f"O capítulo {numero_capitulo(numero)} já existe nesta obra.", "erro")
        return

    enviados = [arq for arq in request.files.getlist("paginas") if arq.filename]
    imagens = [arq for arq in enviados if extensao(arq.filename) in EXTENSOES]
    if not imagens:
        flash("Escolha as imagens das páginas (JPG, PNG, WEBP ou GIF).", "erro")
        return
    imagens.sort(key=lambda arq: ordem_natural(arq.filename))   #1, 2, 3 ... 10, 11

    cap_id = gravar("INSERT INTO capitulo (obra_id, numero, titulo) VALUES (?, ?, ?)",
                    (obra_id, numero, request.form.get("titulo", "").strip()))
    pasta = os.path.join(UPLOADS, f"obra_{obra_id}", f"cap_{cap_id}")
    os.makedirs(pasta, exist_ok=True)
    for i, imagem in enumerate(imagens, start=1):
        nome = f"{i:03d}.{extensao(imagem.filename)}"   #001.jpg, 002.jpg ...
        imagem.save(os.path.join(pasta, nome))
        gravar("INSERT INTO pagina (capitulo_id, numero, arquivo) VALUES (?, ?, ?)",
               (cap_id, i, f"uploads/obra_{obra_id}/cap_{cap_id}/{nome}"))

    mensagem = f"Capítulo {numero_capitulo(numero)} publicado com {len(imagens)} páginas."
    ignorados = len(enviados) - len(imagens)
    if ignorados:
        mensagem += f" {ignorados} arquivo(s) ignorado(s) por não serem imagem."
    flash(mensagem)


@app.route("/admin/capitulo/<int:cap_id>/excluir", methods=["POST"])
@admin_obrigatorio
def excluir_capitulo(cap_id):
    cap = ler_um("SELECT * FROM capitulo WHERE id = ?", (cap_id,))
    if cap is None:
        abort(404)
    gravar("DELETE FROM pagina WHERE capitulo_id = ?", (cap_id,))
    gravar("DELETE FROM leitura WHERE capitulo_id = ?", (cap_id,))
    gravar("DELETE FROM capitulo WHERE id = ?", (cap_id,))
    shutil.rmtree(os.path.join(UPLOADS, f"obra_{cap['obra_id']}", f"cap_{cap_id}"), ignore_errors=True)
    flash(f"Capítulo {numero_capitulo(cap['numero'])} excluído.")
    return redirect(f"/admin/obra/{cap['obra_id']}")


@app.route("/admin/obra/<int:obra_id>/excluir", methods=["POST"])
@admin_obrigatorio
def excluir_obra(obra_id):
    obra = obra_ou_404(obra_id)
    gravar("DELETE FROM pagina WHERE capitulo_id IN (SELECT id FROM capitulo WHERE obra_id = ?)", (obra_id,))
    gravar("DELETE FROM capitulo WHERE obra_id = ?", (obra_id,))
    gravar("DELETE FROM favorito WHERE obra_id = ?", (obra_id,))
    gravar("DELETE FROM avaliacao WHERE obra_id = ?", (obra_id,))
    gravar("DELETE FROM leitura WHERE obra_id = ?", (obra_id,))
    gravar("DELETE FROM obra WHERE id = ?", (obra_id,))
    shutil.rmtree(os.path.join(UPLOADS, f"obra_{obra_id}"), ignore_errors=True)   #apaga a capa e as páginas
    flash(f"{obra['titulo']} foi excluída.")
    return redirect("/admin")


@app.route("/admin/usuarios")
@admin_obrigatorio
def admin_usuarios():
    usuarios = ler("""SELECT u.*,
                      (SELECT COUNT(DISTINCT capitulo_id) FROM leitura l WHERE l.usuario_id = u.id) AS lidos
                      FROM usuario u ORDER BY u.admin DESC, u.nome""")
    return render_template("admin/usuarios.html", usuarios=usuarios)


@app.route("/admin/usuario/<int:usuario_id>/<acao>", methods=["POST"])
@admin_obrigatorio
def gerenciar_usuario(usuario_id, acao):
    if usuario_id == g.usuario["id"]:
        flash("Você não pode mudar a sua própria conta por aqui.", "erro")
        return redirect("/admin/usuarios")
    alvo = ler_um("SELECT * FROM usuario WHERE id = ?", (usuario_id,))
    if alvo is None:
        abort(404)

    if acao == "promover":
        gravar("UPDATE usuario SET admin = 1 WHERE id = ?", (usuario_id,))
        flash(f"{alvo['nome']} agora é administrador.")
    elif acao == "rebaixar":
        gravar("UPDATE usuario SET admin = 0 WHERE id = ?", (usuario_id,))
        flash(f"{alvo['nome']} não é mais administrador.")
    elif acao == "excluir":
        gravar("DELETE FROM favorito WHERE usuario_id = ?", (usuario_id,))
        gravar("DELETE FROM avaliacao WHERE usuario_id = ?", (usuario_id,))
        #as leituras ficam sem dono pra não perder a contagem de visualizações
        gravar("UPDATE leitura SET usuario_id = NULL WHERE usuario_id = ?", (usuario_id,))
        gravar("DELETE FROM usuario WHERE id = ?", (usuario_id,))
        flash(f"A conta de {alvo['nome']} foi excluída.")
    else:
        abort(404)
    return redirect("/admin/usuarios")


#páginas de erro 
@app.errorhandler(404)
def nao_encontrado(erro):
    return render_template("erro.html", titulo="Página não encontrada",
                           mensagem="O endereço pode estar errado ou a obra foi removida."), 404


@app.errorhandler(403)
def proibido(erro):
    return render_template("erro.html", titulo="Só para administradores",
                           mensagem="Entre com uma conta de administrador para abrir esta página."), 403


@app.errorhandler(413)
def grande_demais(erro):
    flash("O envio passou de 200 MB. Mande o capítulo em partes menores.", "erro")
    return redirect(request.referrer or "/admin")


#iniciar
os.makedirs(UPLOADS, exist_ok=True)   #cria o static/uploads se não existir
criar_tabelas()

if __name__ == "__main__":
    app.run(debug=True)
