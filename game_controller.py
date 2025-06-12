from flask_socketio import emit, join_room, leave_room
from flask import session
from flask import Flask
from flask_socketio import SocketIO
import mysql.connector

app = Flask(__name__)
socketio = SocketIO(app)

def get_db():
    """Get database connection"""
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='register'
    )

def initialize_socketio(socketio):
    """Initialize Socket.IO event handlers"""

    @socketio.on('connect')
    def handle_connect():
        user_id = session.get('user_id')
        if user_id:
            join_room(f"user_{user_id}")
    
    @socketio.on('join_game')
    def handle_join_game(data):
        """Handle player joining a game room"""
        match_id = data['match_id']
        player_id = session.get('user_id')
        username = session.get('username')
        
        if not player_id:
            emit('error', {'message': 'Not authenticated'})
            return
        
        # Join the game room
        room_name = f"game_{match_id}"
        join_room(room_name)
        
        print(f"Player {username} joined game room {room_name}")
        
        # Notify other players in the room
        emit('player_joined', {
            'username': username,
            'player_id': player_id,
            'message': f'{username} joined the game'
        }, room=room_name, include_self=False)
        
        # Send confirmation to the joining player
        emit('game_joined', {
            'room': room_name,
            'message': 'Successfully joined the game'
        })
    
    @socketio.on('leave_game')
    def handle_leave_game(data):
        """Handle player leaving a game room"""
        match_id = data['match_id']
        username = session.get('username')
        room_name = f"game_{match_id}"
        
        leave_room(room_name)
        
        # Notify other players
        emit('player_left', {
            'username': username,
            'message': f'{username} left the game'
        }, room=room_name)
    
    @socketio.on('request_board_state')
    def handle_board_state_request(data):
        """Send current board state to requesting player"""
        match_id = data['match_id']
        room_name = f"game_{match_id}"
        
        # Import here to avoid circular imports
        from .game_state import active_games
        
        if match_id in active_games:
            game = active_games[match_id]
            board_data = {
                'board': game.board.tolist(),
                'current_player': game.current_player,
                'move_history': game.move_history,
                'game_over': game.game_over,
                'result_message': game.result_message
            }
            emit('board_update', board_data)
        else:
            emit('error', {'message': 'Game not found'})

    def broadcast_clock_update(match_id: int, current_player):
        """Broadcast clock update when a move is made"""
        room_name = f"game_{match_id}"
        print("Hello Chaim!!!")
        from . import socketio
        # Emit clock switch signal
        socketio.emit('auto_clock_switch', {
            'current_player': current_player,
            'match_id': match_id
        }, to=room_name)
        
        print(f"Broadcasting clock switch to room {room_name}, next player: {current_player}")

    @socketio.on('updateClock')
    def handle_clock(data):
        match_id = data['match_id']
        player = data['player']
        minutes = data['minutes']
        seconds = data['seconds']
        print(match_id)
        print(player)

        # Import here to avoid circular imports
        from .game_state import active_games
        
        # Update match state
        match_id = int(data['match_id'])
        game = active_games.get(match_id)
        print(game)
        if game:
            if player == 1:
                game.player1_time = (minutes, seconds)
            else:
                game.player2_time = (minutes, seconds)
            
            # Broadcast to all players
            emit('clock_update', {
                'player': player,
                'minutes': minutes,
                'seconds': seconds
            }, room=f"game_{match_id}")
        else:
            print("Station no 2")

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnect"""
        username = session.get('username', 'Unknown')
        print(f'Client {username} disconnected')

def broadcast_match_ready(socketio, match_id):
    socketio.emit('match_ready', 
                 {'match_id': match_id},
                 room=f"user_{session['user_id']}")

def broadcast_board_update(socketio, match_id, game):
    """Broadcast board update to all players in the game"""
    room_name = f"game_{match_id}"
    
    board_data = {
        'board': game.board.tolist(),
        'current_player': game.current_player,
        'move_history': game.move_history[-1] if game.move_history else None,
        'game_over': game.game_over,
        'result_message': game.result_message,
        'last_move': game.move_history[-1] if game.move_history else None
    }
    
    socketio.emit('board_update', board_data, room=f"game_{match_id}")
    print(f"Broadcasting board update to room {room_name}")
