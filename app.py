from flask import Flask, redirect, url_for, session, render_template, request, flash
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = '78896'

# Initialize OAuth
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

repo_data = {}

UPLOAD_FOLDER = 'static/logos'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def home():
    return 'Welcome to your GitHub Repo Dashboard! <a href="/login">Login with GitHub</a>'

@app.route('/login')
def login():
    return github.authorize_redirect(url_for('auth', _external=True))

@app.route('/auth')
def auth():
    token = github.authorize_access_token()
    session['token'] = token
    return redirect(url_for('dashboard'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'token' not in session:
        return redirect(url_for('home'))

    user_info = github.get('https://api.github.com/user', token=session['token']).json()
    username = user_info['login']

    repos = github.get('https://api.github.com/user/repos', token=session['token'])
    repos_data = repos.json()

    languages_data = {}
    for repo in repos_data:
        languages = github.get(f'https://api.github.com/repos/{repo["owner"]["login"]}/{repo["name"]}/languages', token=session['token'])
        languages_data[repo['name']] = list(languages.json().keys())

    if request.method == 'POST':
        repo_name = request.form['repo_name']
        
        # Process image upload
        file = request.files['logo']
        logo_filename = 'logo.png' 
        if file:
            logo_filename = repo_name + '.jpg'
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename))
        
        repo_data[repo_name] = {
            'logo': logo_filename,
        }
        return redirect(url_for('dashboard'))

    return render_template('dashboard.html', repos=repos_data, repo_data=repo_data, languages_data=languages_data, username=username)

@app.route('/dashboard/update', methods=['POST'])
def update_repo():
    repo_name = request.form['repo_name']
    logo = request.files['logo']

    if logo and logo.filename != '':
        logo.save(os.path.join(app.config['UPLOAD_FOLDER'], logo.filename))
        repo_data[repo_name]['logo'] = logo.filename
    else:
        flash('No new logo selected, keeping the existing logo.')

    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
