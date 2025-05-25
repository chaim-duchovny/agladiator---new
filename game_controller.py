import os
import importlib.util
import sys
from flask import Blueprint, jsonify, render_template, session, redirect, url_for, flash, request
from flask import current_app
import mysql.connector
import numpy as np

# Create game blueprint
bp_game = Blueprint('game', __name__, url_prefix='/game')

# Store active games in memory
active_games = {}

class GoGame:
    """Class to manage a Go game between two AI agents"""
    
    def __init__(self, match_id, player1_id, player2_id, player1_agent_path, player2_agent_path):
        self.match_id = match_id
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.player1_agent_path = player1_agent_path
        self.player2_agent_path = player2_agent_path

        self.previous_board_state = None  # For ko rule
        self.last_captured = None  # Track captures for ko
        
        # Initialize game state
        self.board = np.zeros((19, 19), dtype=int)  # 0: empty, 1: black, 2: white
        self.current_player = 1  # Black plays first
        self.starting_player_validated = False
        self.move_history = []
        self.game_over = False
        self.result_message = ""
        
        # Load AI agents
        self.player1_agent = self._load_agent(player1_agent_path)
        self.player2_agent = self._load_agent(player2_agent_path)
    
    def _load_agent(self, agent_path):
        """Load an AI agent from a Python file"""
        try:
            module_name = os.path.basename(agent_path).split('.')[0]
            spec = importlib.util.spec_from_file_location(module_name, agent_path)
            if spec is None:
                raise ImportError(f"Could not find module at {agent_path}")
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            if not hasattr(module, 'get_move'):
                raise AttributeError("Agent must have a get_move function")
                
            return module
        except Exception as e:
            print(f"Error loading agent {agent_path}: {str(e)}")
            return None
        
    def get_group(self, x, y, player, visited=None):
        """Find all connected stones and their liberties"""
        if visited is None:
            visited = set()
        if (x, y) in visited or self.board[y][x] != player:
            return set(), set()
        
        visited.add((x, y))
        group = {(x, y)}
        liberties = set()
        
        # Check all adjacent points
        for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < 19 and 0 <= ny < 19:
                if self.board[ny][nx] == 0:
                    liberties.add((nx, ny))
                elif self.board[ny][nx] == player:
                    subgroup, subliberties = self.get_group(nx, ny, player, visited)
                    group.update(subgroup)
                    liberties.update(subliberties)
        return group, liberties
    
    def is_valid_move(self, x, y, player):
        """Check if a move is valid according to Go rules"""
        # Basic validity checks
        if x < 0 or x >= 19 or y < 0 or y >= 19:
            return False
        
        if self.board[y][x] != 0:
            return False
        
        # Temporary placement
        self.board[y][x] = player
        captured = []
        
        # Check adjacent enemy groups
        for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < 19 and 0 <= ny < 19:
                if self.board[ny][nx] == 3 - player:
                    group, liberties = self.get_group(nx, ny, 3 - player)
                    if len(liberties) == 0:
                        captured.extend(group)

        # Check suicide rule
        own_group, own_liberties = self.get_group(x, y, player)
        valid_move = len(captured) > 0 or len(own_liberties) > 0

        # Check ko rule
        temp_board = self.board.copy()
        if captured:
            for (cx, cy) in captured:
                temp_board[cy][cx] = 0
        if np.array_equal(temp_board, self.previous_board_state):
            valid_move = False

        # Undo temporary placement
        self.board[y][x] = 0
        return valid_move
        
        return True
    
    def validate_turn_order(self, player):
        """Ensure proper turn alternation with black starting first"""
        if len(self.move_history) == 0:
            return player == 1  # First move must be black
        
        last_player = self.move_history[-1]['player']
        return player != last_player  # Must alternate players

    
    def make_move(self, x, y, player):
        if not self.is_valid_move(x, y, player):
            return False

        # Place stone
        self.board[y][x] = player
        captured = []

        # Capture opponent stones
        for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < 19 and 0 <= ny < 19:
                if self.board[ny][nx] == 3 - player:
                    group, liberties = self.get_group(nx, ny, 3 - player)
                    if len(liberties) == 0:
                        for (cx, cy) in group:
                            self.board[cy][cx] = 0
                        captured.extend(group)

        # Update ko tracking
        self.last_captured = len(captured)
        self.previous_board_state = self.board.copy()

        # Record move
        move_data = {
            'x': x, 'y': y,
            'player': player,
            'captured': captured,
            'move_number': len(self.move_history) + 1
        }
        self.move_history.append(move_data)
        
        self.current_player = 3 - player

        # Broadcast the move to all players in the game
        try:
            from .game_events import broadcast_board_update
            if hasattr(current_app, 'socketio'):
                broadcast_board_update(current_app.socketio, self.match_id, self)
        except Exception as e:
            print(f"Error broadcasting move: {e}")

        return True
    
    def get_next_move(self):
        """Get and execute next move from current player's AI"""
        try:
            if self.game_over:
                return None
            
            # Get current agent
            agent = self.player1_agent if self.current_player == 1 else self.player2_agent
            
            if agent is None:
                self.game_over = True
                self.result_message = f"Player {self.current_player} agent failed to load"
                return None
            
            # Get move from agent
            board_copy = self.board.copy()
            move = agent.get_move(board_copy, self.current_player)
            
            # Validate move format
            if not move or not isinstance(move, tuple) or len(move) != 2:
                self.game_over = True
                self.result_message = f"Player {self.current_player} returned invalid move format"
                return None
                
            x, y = move
            
            # Make move
            retry_count = 0
            max_retries = 3
            while retry_count < max_retries:
                move = agent.get_move(board_copy, self.current_player)
                if not move or not isinstance(move, tuple) or len(move) != 2:
                    self.result_message = f"Player {self.current_player} returned invalid move format"
                    self.game_over = True
                    return None
                x, y = move
                if self.make_move(x, y, self.current_player):
                    break
                retry_count += 1
                self.result_message = f"Player {self.current_player} attempted illegal move, retrying..."
            else:
                self.game_over = True
                self.result_message = f"Player {self.current_player} exceeded illegal move retries"
                return None

            
            # Check for game end conditions
            if len(self.move_history) >= 361:  # Board is full
                self.game_over = True
                self.result_message = "Game over - board is full"
            
            # Return move info for the frontend
            return {
                'x': x,
                'y': y,
                'color': 'B' if self.current_player == 1 else 'W'
            }
            
        except Exception as e:
            self.game_over = True
            self.result_message = f"Error: {str(e)}"
            return None
        
    def get_winner(self):
        # Count stones for each player
        black_count = (self.board == 1).sum()
        white_count = (self.board == 2).sum()
        if black_count > white_count:
            return 1  # Black wins
        elif white_count > black_count:
            return 2  # White wins
        else:
            return 0  # Draw


def get_db():
    """Get database connection"""
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='register'
    )

@bp_game.route('/<int:match_id>')
def game_view(match_id):
    # Ensure user is logged in
    if 'user_id' not in session:
        flash('You must be logged in to view a match.')
        return redirect(url_for('auth.login'))

    # --- FETCH MATCH FROM DATABASE ---
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT m.*,
                u1.username as player1_name, u1.elo as player1_elo, u1.agentFile as player1_agent,
                u2.username as player2_name, u2.elo as player2_elo, u2.agentFile as player2_agent
            FROM matches m
            JOIN users u1 ON m.player1_id = u1.id
            JOIN users u2 ON m.player2_id = u2.id
            WHERE m.id = %s
        """, (match_id,))
        match = cursor.fetchone()
        if not match:
            flash('Match not found.')
            return redirect(url_for('templates.index'))
        
        if match_id not in active_games:
            game = GoGame(
                match_id=match_id,
                player1_id=match['player1_id'],
                player2_id=match['player2_id'],
                player1_agent_path=os.path.join(match['player1_name'], match['player1_agent']),
                player2_agent_path=os.path.join(match['player2_name'], match['player2_agent'])
            )
            active_games[match_id] = game
        else:
            game = active_games[match_id]

        # --- GAME LOGIC ---
        game = active_games.get(match_id)
        winner = None
        if game and game.game_over:
            winner = game.get_winner()

        return render_template(
            'game.html',
            match_id=match_id,
            player1_name=match['player1_name'],
            player1_elo=match['player1_elo'],
            player2_name=match['player2_name'],
            player2_elo=match['player2_elo'],
            winner=winner
        )
    except Exception as e:
        flash(f"Error: {str(e)}")
        return redirect(url_for('templates.index'))
    finally:
        cursor.close()
        db.close()

@bp_game.route('/next_move')
def next_move():
    match_id = request.args.get('match_id')
    if not match_id:
        return jsonify({'error': 'match_id is required'})
    
    # Convert to int for consistency with your existing code
    try:
        match_id = int(match_id)
    except ValueError:
        return jsonify({'error': 'Invalid match_id format'})
    
    # Your existing logic here
    if match_id not in active_games:
        return jsonify({'error': 'Game not found'})
    
    game = active_games[match_id]
    move = game.get_next_move()
    
    if move:
        return jsonify({
            'move': move,
            'game_over': game.game_over,
            'result': game.result_message if game.game_over else ''
        })
    else:
        return jsonify({
            'error': game.result_message,
            'game_over': game.game_over
        })


@bp_game.route('/<int:match_id>/end', methods=['POST'])
def end_game(match_id):
    """End a game and update ELO ratings"""
    if match_id not in active_games:
        return jsonify({'error': 'Game not found'})
    
    game = active_games[match_id]
    
    # Update match status and ELO ratings
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            UPDATE matches
            SET status = 'completed'
            WHERE id = %s
        """, (match_id,))
        
        db.commit()
        
        # Remove from active games
        del active_games[match_id]
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        cursor.close()
        db.close()
