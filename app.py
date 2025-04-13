from flask import Flask, redirect, url_for, session, render_template, request, flash
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
import os
import asyncio
import httpx

load_dotenv()

app = Flask(__name__)
app.secret_key = '78896'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///repos.db'
db = SQLAlchemy(app)

class Repo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    logo = db.Column(db.LargeBinary, nullable=True)  

oauth = OAuth(app)
github = oauth.register(
    name='github',
    client_id=os.getenv('GITHUB_CLIENT_ID'),
    client_secret=os.getenv('GITHUB_CLIENT_SECRET'),
    authorize_url='https://github.com/login/oauth/authorize',
    access_token_url='https://github.com/login/oauth/access_token',
    refresh_token_url='https://github.com/login/oauth/refresh_token',
    client_kwargs={'scope': 'repo'},
)

UPLOAD_FOLDER = 'static/logos'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    if 'token' in session:
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route('/login')
def login():
    return github.authorize_redirect(url_for('auth', _external=True))

@app.route('/auth')
def auth():
    cancel = request.args.get('cancel')
    if cancel:
        flash("Login was canceled.", "warning")
        return redirect(url_for('home'))

    try:
        token = github.authorize_access_token()
        if not token:
            flash("Login failed. Please try again.", "error")
            return redirect(url_for('home'))
        session['token'] = token
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f"An error occurred during authentication: {e}", "error")
        return redirect(url_for('home'))

# 🔥 Async function to fetch languages
async def fetch_languages_for_repos(repos_data, token):
    async with httpx.AsyncClient() as client:
        tasks = []
        headers = {"Authorization": f"Bearer {token}"}

        for repo in repos_data:
            url = f"https://api.github.com/repos/{repo['owner']['login']}/{repo['name']}/languages"
            tasks.append(client.get(url, headers=headers))

        responses = await asyncio.gather(*tasks)
        languages_data = {}

        for i, response in enumerate(responses):
            if response.status_code == 200:
                languages_data[repos_data[i]['name']] = list(response.json().keys())
            else:
                languages_data[repos_data[i]['name']] = []

        return languages_data

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'token' not in session:
        flash("You must be logged in to access the dashboard.", "warning")
        return redirect(url_for('home'))

    try:
        user_info = github.get('https://api.github.com/user', token=session['token']).json()
        if 'login' not in user_info:
            flash("Failed to retrieve user information. Please log in again.", "error")
            return redirect(url_for('home'))

        username = user_info['login']

        repos = github.get('https://api.github.com/user/repos', token=session['token'])
        repos_data = repos.json()
        repos_data = sorted(repos_data, key=lambda x: x['updated_at'], reverse=True)

        # ⚡️ Fetch languages asynchronously
        languages_data = asyncio.run(fetch_languages_for_repos(repos_data, session['token']))

        if request.method == 'POST':
            repo_name = request.form['repo_name']
            file = request.files['logo']
            logo_data = file.read() if file else None  

            existing_repo = Repo.query.filter_by(name=repo_name, username=username).first()
            if existing_repo:
                existing_repo.logo = logo_data
            else:
                new_repo = Repo(name=repo_name, username=username, logo=logo_data)
                db.session.add(new_repo)

            try:
                db.session.commit()
            except Exception as e:
                print(f"Error saving to DB: {e}")
                db.session.rollback()

            return redirect(url_for('dashboard'))

        repo_logos = {repo.name: repo.logo for repo in Repo.query.filter_by(username=username).all()}

        return render_template('dashboard.html', repos=repos_data, languages_data=languages_data, username=username, repo_logos=repo_logos)

    except Exception as e:
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('home'))

@app.route('/dashboard/update', methods=['POST'])
def update_repo():
    repo_name = request.form['repo_name']
    logo = request.files['logo']

    if logo and logo.filename != '':
        logo_filename = repo_name + '.jpg'
        # logo.save(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename)) # to store it locally
        
        repo = Repo.query.filter_by(name=repo_name, username=session['username']).first()
        repo.logo = logo_filename
        db.session.commit()
    else:
        flash('No new logo selected, keeping the existing logo.')

    return redirect(url_for('dashboard'))

@app.route('/logo/<repo_name>')
def get_logo(repo_name):
    repo = Repo.query.filter_by(name=repo_name).first()
    if repo and repo.logo:
        return app.response_class(repo.logo, mimetype='image/jpeg')
    else:
        return app.send_static_file('logos/default_logo.jpg')  

if __name__ == '__main__':
    app.run(debug=True)
