class Player {
  constructor(element, minutes = 1) {
    this.element = element;
    this.minutes = minutes;
    this.seconds = minutes * 60;
    this.interval = null;
  }

  startClock() {
    if (!this.interval) {
      this.interval = setInterval(() => this.tick(), 1000);
    }
  }

  stopClock() {
    clearInterval(this.interval);
    this.interval = null;
  }

  tick() {
    this.seconds--;
    this.updateClock();
    if (this.seconds <= 0) {
      this.stopClock();
    }
  }

  updateClock() {
    const minutes = Math.floor(this.seconds / 60);
    const seconds = this.seconds % 60;
    this.element.querySelector('.digit').textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
}

let currentPlayer = 2; // 1 = black, 2 = white
var match_id = null;
const blackPlayer = new Player(document.getElementById('black-clock'), 10);
const whitePlayer = new Player(document.getElementById('white-clock'), 10);

// Initialize clocks
blackPlayer.updateClock();
whitePlayer.updateClock();

socket.on('game_joined', function(data) {
  const parts = data.room.split('_');
  match_id = parseInt(parts[1], 10);
  console.log("Received match_id:", match_id);
})

// Listen for automatic clock switches triggered by moves
socket.on('auto_clock_switch', function(data) {
    console.log("Auto clock switch triggered for player:", data.next_player);
    const current_player = data.current_player;
    // Stop current player's clock and start next player's clock
    if (current_player === 1) {
        // Next player is black, so white just moved
        whitePlayer.stopClock();
        blackPlayer.startClock();
        currentPlayer = 1;
    } else {
        // Next player is white, so black just moved
        blackPlayer.stopClock();
        whitePlayer.startClock();
        currentPlayer = 2;
    }
    
    // Emit the clock state update
    const activePlayer = currentPlayer === 1 ? blackPlayer : whitePlayer;
    socket.emit("updateClock", {
        match_id: data.match_id,
        player: currentPlayer,
        minutes: Math.floor(activePlayer.seconds / 60),
        seconds: activePlayer.seconds % 60
    });
});

socket.on('clock_update', function(data) {
  console.log("Station Number1");
  if (data.player === 1) {
    blackPlayer.seconds = data.minutes * 60 + data.seconds;
    blackPlayer.updateClock();

  } else if (data.player === 2) {
    whitePlayer.seconds = data.minutes * 60 + data.seconds;
    whitePlayer.updateClock();
  }
});


document.getElementById('next-move-btn').addEventListener('click', function(){

  currentPlayer = currentPlayer === 1 ? 2 : 1;

  const activePlayer = currentPlayer === 1 ? blackPlayer : whitePlayer;

  socket.emit("updateClock", {
    match_id: match_id,
    player: currentPlayer,
    minutes: Math.floor(activePlayer.seconds / 60),
    seconds: activePlayer.seconds % 60
  });
});
