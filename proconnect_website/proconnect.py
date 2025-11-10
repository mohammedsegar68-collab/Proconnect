#!/usr/bin/env python3
"""
Professional mobile-friendly social media website built using only the Python standard library.
To run:
    python proconnect.py
Then open http://localhost:8000 on your phone or computer (works responsively).

Features:
- Mobile-first layout with responsive Bootstrap design.
- SQLite-based user accounts, sessions, and posts with images.
- No external packages required (no pip installs).
- Designed for clarity, minimalism, and professionalism.

Note: This is for local/demo use. For production, use a real framework with HTTPS, ORM, and hardened security.
"""

from wsgiref.simple_server import make_server
from urllib.parse import parse_qs
import sqlite3, os, io, cgi, hashlib, secrets, mimetypes, html, time

DB_FILE = 'proconnect.db'
STATIC_DIR = 'static'
UPLOAD_DIR = 'uploads'
HOST, PORT = 'localhost', 8000

# --- Prepare directories ---
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- Stylesheet ---
CSS_PATH = os.path.join(STATIC_DIR, 'style.css')
if not os.path.exists(CSS_PATH):
    with open(CSS_PATH, 'w') as f:
        f.write('''
body{font-family:system-ui,Roboto,sans-serif;background:#f3f5f8;margin:0;padding:0}
.navbar{background:#fff;box-shadow:0 2px 6px rgba(0,0,0,0.1);}
.container{max-width:700px;margin:0 auto;padding:1rem}
.card{background:#fff;border-radius:12px;padding:1rem;margin-bottom:1rem;box-shadow:0 4px 12px rgba(0,0,0,0.05)}
textarea{width:100%;min-height:60px;border:1px solid #ccc;border-radius:8px;padding:.5rem}
.btn{display:inline-block;background:#007bff;color:#fff;border:none;border-radius:8px;padding:.5rem 1rem;text-decoration:none}
input[type=text],input[type=password]{width:100%;padding:.5rem;border-radius:8px;border:1px solid #ccc;margin-bottom:.5rem}
img{max-width:100%;border-radius:10px;margin-top:.5rem}
''')

# --- Database setup ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE,password TEXT,created_at INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,expires INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY,user_id INTEGER,content TEXT,image TEXT,created_at INTEGER)')
    conn.commit(); conn.close()

init_db()

# --- Auth helpers ---
def hash_pw(pw):
    salt = secrets.token_hex(8)
    return salt + '$' + hashlib.sha256((salt+pw).encode()).hexdigest()

def check_pw(pw, stored):
    salt, h = stored.split('$',1)
    return hashlib.sha256((salt+pw).encode()).hexdigest() == h

def session_create(uid):
    token = secrets.token_urlsafe(32)
    exp = int(time.time()) + 604800
    conn = sqlite3.connect(DB_FILE)
    conn.execute('INSERT INTO sessions VALUES (?,?,?)',(token,uid,exp))
    conn.commit(); conn.close()
    return token

def session_get(tok):
    if not tok: return None
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT user_id,expires FROM sessions WHERE token=?',(tok,))
    row=c.fetchone()
    if not row: conn.close(); return None
    uid,exp=row
    if exp<int(time.time()):
        conn.execute('DELETE FROM sessions WHERE token=?',(tok,));conn.commit();conn.close();return None
    c.execute('SELECT id,username FROM users WHERE id=?',(uid,))
    u=c.fetchone();conn.close()
    return {'id':u[0],'username':u[1]} if u else None

# --- HTML template ---
BASE='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css"><link rel="stylesheet" href="/static/style.css"></head><body>
<nav class="navbar navbar-light"><div class="container d-flex justify-content-between"><a href="/" class="navbar-brand fw-bold">ProConnect</a><div>{nav}</div></div></nav>
<div class="container">{body}</div></body></html>'''

def page(body,title='ProConnect',user=None):
    if user:
        nav = f'<a href="/profile" class="me-3">{html.escape(user["username"])}</a> <a href="/logout">Logout</a>'

    else:
        nav='<a href="/login" class="me-3">Login</a><a href="/signup">Sign Up</a>'
    return BASE.format(title=html.escape(title),body=body,nav=nav)

# --- Helpers ---
def cookie_get(env,name):
    cookie=env.get('HTTP_COOKIE','')
    for part in cookie.split(';'):
        if '=' in part:
            k,v=part.strip().split('=',1)
            if k==name:return v
    return None

def redirect(loc,extra=None):
    headers=[('Location',loc)]
    if extra:headers+=extra
    return '302 FOUND',headers,b''

# --- Routes ---
def index(env):
    u=session_get(cookie_get(env,'session'))
    conn=sqlite3.connect(DB_FILE);c=conn.cursor()
    c.execute('SELECT posts.content,posts.image,posts.created_at,users.username FROM posts JOIN users ON users.id=posts.user_id ORDER BY posts.created_at DESC LIMIT 50')
    posts=c.fetchall();conn.close()
    html_feed=''
    if u:
        html_feed+='<div class="card"><form method="post" action="/post" enctype="multipart/form-data"><textarea name="content" placeholder="Share something..." required></textarea><input type="file" name="image" class="form-control form-control-sm mb-2" accept="image/*"><button class="btn btn-primary">Post</button></form></div>'
    else:
        html_feed+='<div class="card text-center"><a href="/login">Login</a> to post updates.</div>'
    for content,img,created,uname in posts:
        t=time.strftime('%Y-%m-%d %H:%M',time.localtime(created))
        pic=f'<img src="/uploads/{img}" alt=""/>' if img else ''
        html_feed+=f'<div class="card"><strong>{html.escape(uname)}</strong><br><small>{t}</small><div class="mt-2">{html.escape(content)}</div>{pic}</div>'
    return '200 OK',[('Content-Type','text/html')],page(html_feed,'Home',u).encode()

def signup(env):
    if env['REQUEST_METHOD']=='POST':
        fs=cgi.FieldStorage(fp=env['wsgi.input'],environ=env)
        user,pw=fs.getfirst('username','').strip(),fs.getfirst('password','')
        if not user or not pw:
            return '200 OK',[('Content-Type','text/html')],page('<div class="card">All fields required.</div>','Sign Up').encode()
        conn=sqlite3.connect(DB_FILE)
        try:
            conn.execute('INSERT INTO users(username,password,created_at) VALUES (?,?,?)',(user,hash_pw(pw),int(time.time())))
            conn.commit();uid=conn.execute('SELECT id FROM users WHERE username=?',(user,)).fetchone()[0];conn.close()
            tok=session_create(uid)
            return redirect('/',[('Set-Cookie',f'session={tok}; Path=/; HttpOnly')])
        except sqlite3.IntegrityError:
            conn.close();return '200 OK',[('Content-Type','text/html')],page('<div class="card">Username taken.</div>','Sign Up').encode()
    form='<div class="card"><h4>Create account</h4><form method="post"><input name="username" placeholder="Username" required><input name="password" type="password" placeholder="Password" required><button class="btn btn-primary">Sign Up</button></form></div>'
    return '200 OK',[('Content-Type','text/html')],page(form,'Sign Up').encode()

def login(env):
    if env['REQUEST_METHOD']=='POST':
        size=int(env.get('CONTENT_LENGTH') or 0)
        body=env['wsgi.input'].read(size).decode()
        d=parse_qs(body)
        user,pw=d.get('username',[''])[0],d.get('password',[''])[0]
        conn=sqlite3.connect(DB_FILE);c=conn.cursor()
        c.execute('SELECT id,password FROM users WHERE username=?',(user,));r=c.fetchone();conn.close()
        if r and check_pw(pw,r[1]):
            tok=session_create(r[0])
            return redirect('/',[('Set-Cookie',f'session={tok}; Path=/; HttpOnly')])
        return '200 OK',[('Content-Type','text/html')],page('<div class="card">Invalid credentials.</div>','Login').encode()
    form='<div class="card"><h4>Login</h4><form method="post"><input name="username" placeholder="Username" required><input name="password" type="password" placeholder="Password" required><button class="btn btn-primary">Login</button></form></div>'
    return '200 OK',[('Content-Type','text/html')],page(form,'Login').encode()

def logout(env):
    tok=cookie_get(env,'session')
    if tok:
        conn=sqlite3.connect(DB_FILE);conn.execute('DELETE FROM sessions WHERE token=?',(tok,));conn.commit();conn.close()
    return redirect('/',[('Set-Cookie','session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT')])

def post(env):
    u=session_get(cookie_get(env,'session'))
    if not u:return redirect('/login')
    fs=cgi.FieldStorage(fp=env['wsgi.input'],environ=env)
    content=fs.getfirst('content','').strip();imgfile=fs['image'] if 'image' in fs and fs['image'].filename else None
    imgname=None
    if imgfile:
        ext=os.path.splitext(imgfile.filename)[1];imgname=secrets.token_hex(8)+ext
        with open(os.path.join(UPLOAD_DIR,imgname),'wb') as f:f.write(imgfile.file.read())
    conn=sqlite3.connect(DB_FILE);conn.execute('INSERT INTO posts(user_id,content,image,created_at) VALUES (?,?,?,?)',(u['id'],content,imgname,int(time.time())));conn.commit();conn.close()
    return redirect('/')

def profile(env):
    u=session_get(cookie_get(env,'session'))
    if not u:return redirect('/login')
    conn=sqlite3.connect(DB_FILE);c=conn.cursor();c.execute('SELECT content,image,created_at FROM posts WHERE user_id=? ORDER BY created_at DESC',(u['id'],));rows=c.fetchall();conn.close()
    out=f'<div class="card"><h4>{html.escape(u["username"])}\'s Profile</h4></div>'
    for content,img,created in rows:
        t=time.strftime('%Y-%m-%d %H:%M',time.localtime(created));pic=f'<img src="/uploads/{img}" alt="">' if img else ''
        out+=f'<div class="card"><small>{t}</small><div class="mt-2">{html.escape(content)}</div>{pic}</div>'
    return '200 OK',[('Content-Type','text/html')],page(out,'Profile',u).encode()

def static_file(p):
    fpath=os.path.join(STATIC_DIR,p)
    if not os.path.exists(fpath):return None
    ctype=mimetypes.guess_type(fpath)[0] or 'application/octet-stream'
    with open(fpath,'rb') as f:return '200 OK',[('Content-Type',ctype)],f.read()

def uploads(p):
    fpath=os.path.join(UPLOAD_DIR,p)
    if not os.path.exists(fpath):return None
    ctype=mimetypes.guess_type(fpath)[0] or 'application/octet-stream'
    with open(fpath,'rb') as f:return '200 OK',[('Content-Type',ctype)],f.read()

# --- App ---
def app(env,start):
    path=env.get('PATH_INFO','/')
    if path.startswith('/static/'):
        res=static_file(path[8:])
        if not res: start('404 NOT FOUND',[]);return [b'not found']
        s,h,b=res;start(s,h);return [b]
    if path.startswith('/uploads/'):
        res=uploads(path[9:])
        if not res: start('404 NOT FOUND',[]);return [b'not found']
        s,h,b=res;start(s,h);return [b]
    routes={'/':index,'/signup':signup,'/login':login,'/logout':logout,'/post':post,'/profile':profile}
    if path in routes:
        s,h,b=routes[path](env);start(s,h);return [b]
    start('404 NOT FOUND',[('Content-Type','text/html')]);return [b'<h3>404 - Page not found</h3>']

if __name__=='__main__':
    print(f"ProConnect running on http://{HOST}:{PORT}")
    with make_server(HOST,PORT,app) as srv:
        try:srv.serve_forever()
        except KeyboardInterrupt:print('\nStopped.')
