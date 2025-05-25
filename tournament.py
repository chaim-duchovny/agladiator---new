from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import mysql.connector
import math
from datetime import datetime
from functools import wraps

bp_tournament = Blueprint('tournament', __name__, url_prefix='/tournament')

def get_db():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='register'
    )

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_id') != 1:  # Hardcoded admin ID
            flash("This action requires administrator privileges")
            return redirect(url_for('tournament.list_tournaments'))
        return f(*args, **kwargs)
    return decorated_function

@bp_tournament.route('/')
def list_tournaments():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT t.*, COUNT(tp.id) AS participant_count 
        FROM tournaments t
        LEFT JOIN tournament_participants tp ON t.id = tp.tournament_id
        GROUP BY t.id
        ORDER BY t.created_at DESC
    """)
    tournaments = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('tournament/list.html', tournaments=tournaments)

@bp_tournament.route('/create', methods=['GET', 'POST'])
@admin_required
def create_tournament():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        start_date = request.form['start_date']
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO tournaments 
            (name, description, start_date, max_participants) 
            VALUES (%s, %s, %s, 2048)
        """, (name, description, start_date))
        db.commit()
        tournament_id = cursor.lastrowid
        cursor.close()
        db.close()
        flash('Tournament created successfully!')
        return redirect(url_for('tournament.view_tournament', tournament_id=tournament_id))
    return render_template('tournament/create.html')

@bp_tournament.route('/<int:tournament_id>')
def view_tournament(tournament_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM tournaments WHERE id = %s", (tournament_id,))
    tournament = cursor.fetchone()
    
    cursor.execute("""
        SELECT tp.*, u.username, u.elo
        FROM tournament_participants tp
        JOIN users u ON tp.user_id = u.id
        WHERE tp.tournament_id = %s
    """, (tournament_id,))
    participants = cursor.fetchall()
    
    cursor.execute("""
        SELECT COUNT(*) as registered FROM tournament_participants
        WHERE tournament_id = %s
    """, (tournament_id,))
    registered = cursor.fetchone()['registered']
    
    cursor.close()
    db.close()
    
    progress = min((registered / 2048) * 100, 100)
    return render_template('tournament/view.html', 
                         tournament=tournament,
                         participants=participants,
                         registered=registered,
                         progress=progress)

@bp_tournament.route('/<int:tournament_id>/register', methods=['POST'])
def register_for_tournament(tournament_id):
    if 'user_id' not in session:
        flash('You must be logged in to register.')
        return redirect(url_for('auth.login'))
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM tournaments WHERE id = %s", (tournament_id,))
        tournament = cursor.fetchone()
        
        cursor.execute("""
            SELECT * FROM tournament_participants
            WHERE tournament_id = %s AND user_id = %s
        """, (tournament_id, session['user_id']))
        if cursor.fetchone():
            flash('Already registered!')
            return redirect(url_for('tournament.view_tournament', tournament_id=tournament_id))
        
        cursor.execute("""
            INSERT INTO tournament_participants (tournament_id, user_id)
            VALUES (%s, %s)
        """, (tournament_id, session['user_id']))
        
        cursor.execute("""
            UPDATE tournaments
            SET current_participants = current_participants + 1
            WHERE id = %s
        """, (tournament_id,))
        
        db.commit()
        flash('Registration successful!')
        
        if tournament['current_participants'] + 1 >= 2048:
            flash('Tournament is full! Starting soon...')
        
    except Exception as e:
        flash(f"Error: {str(e)}")
    finally:
        cursor.close()
        db.close()
    
    return redirect(url_for('tournament.view_tournament', tournament_id=tournament_id))

def start_tournament(db, cursor, tournament_id):
    """Initialize the tournament bracket with 2048 participants"""
    try:
        # Get tournament details
        cursor.execute("""
            SELECT * FROM tournaments 
            WHERE id = %s AND status = 'upcoming'
        """, (tournament_id,))
        tournament = cursor.fetchone()
        
        if not tournament:
            return False

        # Get participants ordered by ELO for proper seeding
        cursor.execute("""
            SELECT tp.id, tp.user_id, u.username, u.elo
            FROM tournament_participants tp
            JOIN users u ON tp.user_id = u.id
            WHERE tp.tournament_id = %s
            ORDER BY u.elo DESC
        """, (tournament_id,))
        participants = cursor.fetchall()

        num_participants = len(participants)
        if num_participants != 2048:
            return False

        # Assign seeds based on ELO ranking
        for seed, participant in enumerate(participants, 1):
            cursor.execute("""
                UPDATE tournament_participants
                SET seed = %s
                WHERE id = %s
            """, (seed, participant['id']))
            participant['seed'] = seed

        db.commit()

        # Tournament structure calculations
        total_rounds = 11  # log2(2048) = 11 rounds
        matches_per_round = 1024  # Starting with 1024 matches in first round

        # Create first round matches (1v2048, 2v2047, etc.)
        for i in range(0, 2048, 2):
            # Calculate positions using standard tournament seeding
            p1 = participants[i]
            p2 = participants[i + 1]

            # Create match record
            cursor.execute("""
                INSERT INTO matches 
                (player1_id, player2_id, status)
                VALUES (%s, %s, 'active')
            """, (p1['user_id'], p2['user_id']))
            match_id = cursor.lastrowid

            # Track tournament match
            cursor.execute("""
                INSERT INTO tournament_matches
                (tournament_id, match_id, round, position)
                VALUES (%s, %s, %s, %s)
            """, (tournament_id, match_id, 1, i//2))

        # Create empty matches for subsequent rounds
        current_round = 2
        while current_round <= total_rounds:
            matches_in_round = 2048 // (2 ** current_round)
            for pos in range(matches_in_round):
                # Create empty match slot
                cursor.execute("""
                    INSERT INTO matches (status)
                    VALUES ('waiting')
                """)
                match_id = cursor.lastrowid
                
                # Link to tournament structure
                cursor.execute("""
                    INSERT INTO tournament_matches
                    (tournament_id, match_id, round, position)
                    VALUES (%s, %s, %s, %s)
                """, (tournament_id, match_id, current_round, pos))
            
            current_round += 1

        # Update tournament status
        cursor.execute("""
            UPDATE tournaments
            SET status = 'active', start_date = NOW()
            WHERE id = %s
        """, (tournament_id,))
        
        db.commit()
        return True

    except Exception as e:
        print(f"Error starting tournament: {str(e)}")
        db.rollback()
        return False
    finally:
        # Don't close connection here - handled by caller
        pass

