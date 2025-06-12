def broadcast_board_update(socketio, match_id, game):
    room_name = f"game_{match_id}"
    board_data = {
        'board': game.board.tolist(),
        'current_player': game.current_player,
        'move_history': game.move_history[-1] if game.move_history else None,
        'game_over': game.game_over,
        'result_message': game.result_message,
        'last_move': game.move_history[-1] if game.move_history else None
    }
    socketio.emit('board_update', board_data, room=room_name)
    print(f"Broadcasting board update to room {room_name}")

def broadcast_clock_update(socketio, match_id, current_player):
    room_name = f"game_{match_id}"
    socketio.emit('auto_clock_switch', {
        'current_player': current_player,
        'match_id': match_id
    }, to=room_name)
    print(f"Broadcasting clock switch to room {room_name}, next player: {current_player}")
