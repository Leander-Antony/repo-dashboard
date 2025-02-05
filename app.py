from flask import Flask, redirect, url_for, session, render_template, request, flash
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = '78896'

# Initialize Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///repos.db'
db = SQLAlchemy(app)

# Define the Repo Model
class Repo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    logo = db.Column(db.LargeBinary, nullable=True)  # To store the logo as binary data


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

UPLOAD_FOLDER = 'static/logos'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize the database
with app.app_context():
    db.create_all()

@app.route('/')
def home():
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


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'token' not in session:
        flash("You must be logged in to access the dashboard.", "warning")
        return redirect(url_for('home'))  # Redirect to home or login page

    try:
        user_info = github.get('https://api.github.com/user', token=session['token']).json()
        
        # Check if the 'login' field is in the user_info
        if 'login' not in user_info:
            flash("Failed to retrieve user information. Please log in again.", "error")
            return redirect(url_for('home'))

        username = user_info['login']

        repos = github.get('https://api.github.com/user/repos', token=session['token'])
        repos_data = repos.json()

        languages_data = {}
        for repo in repos_data:
            languages = github.get(f'https://api.github.com/repos/{repo["owner"]["login"]}/{repo["name"]}/languages', token=session['token'])
            languages_data[repo['name']] = list(languages.json().keys())

        if request.method == 'POST':
            repo_name = request.form['repo_name']
            file = request.files['logo']
            
            # Process image upload and store it in the database
            logo_data = file.read() if file else None  # Read the file as binary data
            
            # Log the uploaded logo size
            if logo_data:
                print(f"Logo data size: {len(logo_data)} bytes")
            else:
                print("No logo data uploaded")

            # Check if repo exists, otherwise add it
            existing_repo = Repo.query.filter_by(name=repo_name, username=username).first()
            if existing_repo:
                existing_repo.logo = logo_data
            else:
                new_repo = Repo(name=repo_name, username=username, logo=logo_data)
                db.session.add(new_repo)

            try:
                db.session.commit()
                print(f"Data for {repo_name} saved successfully.")
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
        
        # Update the database entry
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
        return app.send_static_file('logos/default_logo.jpg')  # Serve the default logo if no custom one exists

if __name__ == '__main__':
    app.run(debug=True)


