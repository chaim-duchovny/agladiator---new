import os
from . import db
from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO(cors_allowed_origins="*")

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'agladiator.sqlite'),
    )

    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize Socket.IO with app
    socketio.init_app(app)

    from .auth import bp1 as auth_bp1
    from .auth import bp2 as auth_bp2
    from .game_controller import bp_game
    from .tournament import bp_tournament
    from .game_events import initialize_socketio

    app.register_blueprint(auth_bp1)
    app.register_blueprint(auth_bp2)
    app.register_blueprint(bp_game)
    app.register_blueprint(bp_tournament)
    
    initialize_socketio(socketio)  # Pass socketio instance to initialize
    
    # Store for access via current_app.socketio
    app.socketio = socketio  

    return app
