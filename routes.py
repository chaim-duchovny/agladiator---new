import os
import time
from flask import render_template, request, flash, redirect, url_for, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
from mysql.connector import IntegrityError, Error

from . import bp1
from . import bp2

def get_db():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='register'
    )

@bp1.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        agentFile = request.files['agentFile']
        error = None

        if not username:
            flash('Username is required.')
            return render_template('auth/register.html')
        elif not email:
            flash('Email is required.')
            return render_template('auth/register.html')
        elif not password:
            flash('Password is required.')
            return render_template('auth/register.html')
        elif not agentFile or agentFile.filename == '':
            flash('File is required.')
            return render_template('auth/register.html')
        else:
            _, ext = os.path.splitext(secure_filename(agentFile.filename))
            filename = f"{secure_filename(username)}_{int(time.time())}{ext}"
            UPLOAD_FOLDER = f"{username}"
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)
            agentFile.save(os.path.join(UPLOAD_FOLDER, filename))

        if error is None:
            db = get_db()
            cursor = db.cursor()
            try:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                account = cursor.fetchone()
                if account:
                    error = f"User {username} is already registered."
                else:
                    hashed_password = generate_password_hash(password)
                    cursor.execute(
                        "INSERT INTO users (username, email, password, agentFile) VALUES (%s, %s, %s, %s)",
                        (username, email, hashed_password, filename)
                    )
                    db.commit()
                    flash('Registration successful! Please log in.')
                    return redirect(url_for('auth.login'))
            except IntegrityError:
                flash(f"User {username} is already registered.")
                return render_template('auth/register.html')
            except Exception as e:
                flash(f"An error occurred: {str(e)}")
                return render_template('auth/register.html')
            finally:
                cursor.close()
                db.close()
        flash(error)
    return render_template('auth/register.html')

@bp1.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        error = None
        db = get_db()
        cursor = db.cursor(dictionary=True, buffered=True)
        try:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            username = cursor.fetchone()
            if username is None:
                error = 'Incorrect username.'
            elif not check_password_hash(username['password'], password):
                error = 'Incorrect password.'
            else:
                # Successful login
                session.clear()
                session['user_id'] = username['id']
                session['username'] = username['username']
                flash('Logged in successfully!', 'success')
                return redirect(url_for('templates.index')) # or wherever you want to go after login
            flash(error, 'danger')
        except Exception as e:
            flash(f"An error occurred: {str(e)}", 'danger')
        finally:
            cursor.close()
            db.close()
    return render_template('auth/login.html')

@bp1.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('auth.login'))

@bp2.route('/index')
def index():
    return render_template('index.html')

@bp2.route('/home')
def home():
    return render_template('home.html')

@bp2.route('/find_match', methods=['GET', 'POST'])
def find_match():
    """Handle matchmaking with Socket.IO notifications"""
    if 'user_id' not in session:
        flash('You must be logged in to find a match.')
        return redirect(url_for('auth.login'))

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)
    
    try:
        # Get current user's info
        cursor.execute("SELECT id, username, elo, agentFile FROM users WHERE id = %s",
                     (session['user_id'],))
        current_user = cursor.fetchone()

        if not current_user:
            flash('User profile not found.')
            return redirect(url_for('templates.index'))

        # Check existing matches
        cursor.execute("""
            SELECT * FROM matches 
            WHERE (player1_id = %s OR player2_id = %s)
            AND status IN ('waiting', 'active')
        """, (session['user_id'], session['user_id']))
        existing_match = cursor.fetchone()

        if existing_match:
            flash('You already have an active or pending match.')
            return redirect(url_for('templates.index'))

        # ELO match parameters
        elo_threshold = 200
        current_elo = current_user['elo']
        min_elo = current_elo - elo_threshold
        max_elo = current_elo + elo_threshold

        # Find suitable match
        cursor.execute("""
            SELECT m.id, m.player1_id, u.username, u.elo, u.agentFile
            FROM matches m
            JOIN users u ON m.player1_id = u.id
            WHERE m.status = 'waiting'
            AND u.id != %s
            AND u.elo BETWEEN %s AND %s
            ORDER BY ABS(u.elo - %s)
            LIMIT 1
        """, (session['user_id'], min_elo, max_elo, current_elo))
        waiting_match = cursor.fetchone()

        if waiting_match:
            # Update match and notify both players
            cursor.execute("""
                UPDATE matches
                SET player2_id = %s, status = 'active'
                WHERE id = %s
            """, (session['user_id'], waiting_match['id']))
            db.commit()

            flash(f"Match found! Your AI agent will play against {waiting_match['username']} (ELO: {waiting_match['elo']})")

            # Socket.IO notifications
            try:
                socketio = current_app.socketio
                # Notify first player
                socketio.emit(
                    'match_ready',
                    {'match_id': waiting_match['id']},
                    room=f"user_{waiting_match['player1_id']}"
                )
                # Notify second player
                socketio.emit(
                    'match_ready', 
                    {'match_id': waiting_match['id']},
                    room=f"user_{session['user_id']}"
                )
            except Exception as e:
                print(f"SocketIO error: {e}")

            return redirect(url_for('game.game_view', match_id=waiting_match['id']))
        else:
            # Create new waiting match
            cursor.execute("""
                INSERT INTO matches (player1_id, status)
                VALUES (%s, 'waiting')
            """, (session['user_id'],))
            db.commit()
            flash('Waiting for opponent with similar ELO...')
            return redirect(url_for('templates.index'))

    except Error as e:
        flash(f"Database error: {str(e)}")
        return redirect(url_for('templates.index'))
    finally:
        cursor.close()
        db.close()
