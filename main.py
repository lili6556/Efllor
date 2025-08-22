from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import sqlite3
from werkzeug.utils import secure_filename
import base64
from io import BytesIO
from PIL import Image

app = Flask(__name__)
app.secret_key = 'troque_esse_seguro_para_uma_chave_real'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Conexão com banco
def get_db():
    conn = sqlite3.connect('banco.db')
    conn.row_factory = sqlite3.Row
    return conn

# Garantir colunas adicionais
def ensure_columns(cursor):
    cursor.execute("PRAGMA table_info(produtos)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    if 'coluna_armazenada' not in existing_columns:
        cursor.execute("ALTER TABLE produtos ADD COLUMN coluna_armazenada INTEGER")
    if 'nivel_armazenado' not in existing_columns:
        cursor.execute("ALTER TABLE produtos ADD COLUMN nivel_armazenado INTEGER")
    if 'imagem_base64' not in existing_columns:
        cursor.execute("ALTER TABLE produtos ADD COLUMN imagem_base64 TEXT")
    if 'posicao_bloqueada' not in existing_columns:
        cursor.execute("ALTER TABLE produtos ADD COLUMN posicao_bloqueada TEXT")

# Criação de tabelas
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            quantidade INTEGER NOT NULL,
            preco REAL NOT NULL,
            localizacao TEXT NOT NULL
        )
    ''')
    ensure_columns(cursor)
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].lower()
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password)).fetchone()
        conn.close()
        if user:
            session['user'] = email
            return redirect(url_for('inicio'))
        else:
            flash('Email ou senha inválidos')
            return redirect(url_for('login'))
    return render_template('pagina2.html')

@app.route('/register', methods=['POST'])
def register():
    email = request.form['email'].lower()
    password = request.form['password']
    conn = get_db()
    try:
        conn.execute('INSERT INTO users (email, password) VALUES (?, ?)', (email, password))
        conn.commit()
    except sqlite3.IntegrityError:
        flash('Email já cadastrado')
        conn.close()
        return redirect(url_for('login'))
    conn.close()
    flash('Cadastro realizado com sucesso! Faça login.')
    return redirect(url_for('login'))

@app.route('/inicio')
def inicio():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('inicio.html')

@app.route('/camera', methods=['GET', 'POST'])
def camera():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        file = request.files.get('image')
        if not file or file.filename == '':
            flash('Nenhuma imagem enviada')
            return redirect(url_for('camera'))
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        nome = os.path.splitext(filename)[0].strip().lower()
        conn = get_db()
        produto = conn.execute('SELECT * FROM produtos WHERE TRIM(LOWER(nome)) = ?', (nome,)).fetchone()
        conn.close()

        if produto:
            return render_template('scan_result.html', produto=produto)
        else:
            flash(f'Produto "{nome}" não cadastrado. Cadastre no estoque.')
            return redirect(url_for('estoque'))
    return render_template('atual.html')

@app.route('/buscar_produto', methods=['GET', 'POST'])
def buscar_produto():
    if 'user' not in session:
        return redirect(url_for('login'))

    produto = None
    busca_realizada = False

    if request.method == 'POST':
        nome = request.form['busca'].strip().lower()
        conn = get_db()
        produto = conn.execute("SELECT * FROM produtos WHERE TRIM(LOWER(nome)) = ?", (nome,)).fetchone()
        conn.close()
        busca_realizada = True

    return render_template('buscar_produto.html', produto=produto, busca_realizada=busca_realizada)

@app.route('/estoque_baixo')
def estoque_baixo():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nome, quantidade, preco, localizacao FROM produtos WHERE quantidade <= 2
    """)
    produtos_baixos = cursor.fetchall()
    conn.close()
    return render_template('estoque_baixo.html', produtos=produtos_baixos)

@app.route('/estoque')
def estoque():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nome, quantidade, preco, localizacao, coluna_armazenada, nivel_armazenado, imagem_base64, posicao_bloqueada 
        FROM produtos
    """)
    produtos = [
        {
            "id": row['id'],
            "nome": row['nome'],
            "quantidade": row['quantidade'],
            "preco": row['preco'],
            "localizacao": row['localizacao'],
            "coluna_armazenada": row['coluna_armazenada'],
            "nivel_armazenado": row['nivel_armazenado'],
            "imagem": row['imagem_base64'],
            "posicao_bloqueada": row['posicao_bloqueada']
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return render_template('estoque.html', produtos=produtos)

@app.route('/adicionar_produto', methods=['POST'])
def adicionar_produto():
    nome = request.form['nome']
    quantidade = request.form['quantidade']
    preco = request.form['preco']
    coluna = request.form['coluna']
    linha = request.form['linha']
    posicao = request.form['posicao']
    imagem = request.files.get('imagem')

    coluna_armazenada = coluna
    nivel_armazenado = linha
    posicao_bloqueada = posicao

    localizacao = f"Coluna {coluna}, Linha {linha}, {posicao}"

    if imagem:
        img = Image.open(imagem)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        imagem_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    else:
        imagem_base64 = ''

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO produtos (nome, quantidade, preco, localizacao, coluna_armazenada, nivel_armazenado, imagem_base64, posicao_bloqueada)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (nome, quantidade, preco, localizacao, coluna_armazenada, nivel_armazenado, imagem_base64, posicao_bloqueada)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('estoque'))

@app.route('/deletar_produto/<int:produto_id>', methods=['POST'])
def deletar_produto(produto_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
    conn.commit()
    conn.close()
    flash('Produto deletado com sucesso.')
    return redirect(url_for('estoque'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Você saiu da sessão.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
